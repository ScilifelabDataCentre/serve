import json
import subprocess
import time

import requests
from celery import shared_task
from celery.signals import worker_ready
from django.apps import apps
from django.conf import settings
from django.core.exceptions import EmptyResultSet
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from kubernetes import client, config, watch

from models.models import Model, ObjectType
from projects.models import S3, BasicAuth, Environment, MLFlow
from studio.celery import app

from . import controller
from .models import AppInstance, Apps, AppStatus, ResourceData

K8S_STATUS_MAP = {
    "CrashLoopBackOff": "Error",
    "Completed": "Retrying...",
    "ContainerCreating": "Created",
    "PodInitializing": "Pending",
}

ReleaseName = apps.get_model(app_label=settings.RELEASENAME_MODEL)


def get_URI(parameters):
    URI = "https://" + parameters["release"] + "." + parameters["global"]["domain"]

    URI = URI.strip("/")
    return URI


def process_helm_result(results):
    stdout = results.stdout.decode("utf-8")
    stderr = results.stderr.decode("utf-8")
    return stdout, stderr


def post_create_hooks(instance):
    print("TASK - POST CREATE HOOK...")
    # hard coded hooks for now, we can make this dynamic
    # and loaded from the app specs
    if instance.app.slug == "minio":
        # Create project S3 object
        # TODO: If the instance is being updated,
        # update the existing S3 object.
        access_key = instance.parameters["credentials"]["access_key"]
        secret_key = instance.parameters["credentials"]["secret_key"]

        # OBS!! TEMP WORKAROUND to be able to connect to minio
        minio_svc = "{}-minio".format(instance.parameters["release"])
        cmd = f"kubectl -n {settings.NAMESPACE} get svc {minio_svc} -o jsonpath='{{.spec.clusterIP}}'"
        minio_host_url = ""
        try:
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                timeout=settings.KUBE_API_REQUEST_TIMEOUT,
            )
            minio_host_url = result.stdout.decode("utf-8")
            minio_host_url += ":9000"
        except subprocess.CalledProcessError:
            print("Oops, something went wrong running the command: {}".format(cmd))

        try:
            s3obj = instance.s3obj
            s3obj.access_key = access_key
            s3obj.secret_key = secret_key
            s3obj.host = minio_host_url
        except:  # noqa E722 TODO: Add exception
            s3obj = S3(
                name=instance.name,
                project=instance.project,
                host=minio_host_url,
                access_key=access_key,
                secret_key=secret_key,
                app=instance,
                owner=instance.owner,
            )
        s3obj.save()

    if instance.app.slug == "environment":
        params = instance.parameters
        image = params["container"]["name"]
        # We can assume one registry here
        for reg_key in params["apps"]["docker_registry"].keys():
            reg_release = params["apps"]["docker_registry"][reg_key]["release"]
            reg_domain = params["apps"]["docker_registry"][reg_key]["global"]["domain"]
        repository = reg_release + "." + reg_domain
        registry = AppInstance.objects.get(parameters__contains={"release": reg_release})

        target_environment = Environment.objects.get(pk=params["environment"]["pk"])
        target_app = target_environment.app

        env_obj = Environment(
            name=instance.name,
            project=instance.project,
            repository=repository,
            image=image,
            registry=registry,
            app=target_app,
            appenv=instance,
        )
        env_obj.save()

    if instance.app.slug == "mlflow":
        params = instance.parameters

        # OBS!! TEMP WORKAROUND to be able to connect to mlflow (internal dns
        # between docker and k8s does not work currently)
        # Sure one could use FQDN but lets avoid going via the internet
        mlflow_svc = instance.parameters["service"]["name"]
        cmd = f"kubectl -n {settings.NAMESPACE} get svc {mlflow_svc} -o jsonpath='{{.spec.clusterIP}}'"
        mlflow_host_ip = ""
        try:
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                timeout=settings.KUBE_API_REQUEST_TIMEOUT,
            )
            mlflow_host_ip = result.stdout.decode("utf-8")
            mlflow_host_ip += ":{}".format(instance.parameters["service"]["port"])
        except subprocess.CalledProcessError:
            print("Oops, something went wrong running the command: {}".format(cmd))

        s3 = S3.objects.get(pk=instance.parameters["s3"]["pk"])
        basic_auth = BasicAuth(
            owner=instance.owner,
            name=instance.name,
            project=instance.project,
            username=instance.parameters["credentials"]["username"],
            password=instance.parameters["credentials"]["password"],
        )
        basic_auth.save()
        obj = MLFlow(
            name=instance.name,
            project=instance.project,
            mlflow_url="https://{}.{}".format(
                instance.parameters["release"],
                instance.parameters["global"]["domain"],
            ),
            s3=s3,
            host=mlflow_host_ip,
            basic_auth=basic_auth,
            app=instance,
            owner=instance.owner,
        )
        obj.save()


def release_name(instance):
    # Free up release name (if reserved)
    rel_names = instance.releasename_set.all()

    for rel_name in rel_names:
        rel_name.status = "active"
        rel_name.app = None
        rel_name.save()


def post_delete_hooks(instance):
    print("TASK - POST DELETE HOOK...")
    release_name(instance)
    project = instance.project
    if project.s3storage and project.s3storage.app == instance:
        project.s3storage.delete()
    elif project.mlflow and project.mlflow.app == instance:
        project.mlflow.delete()


@shared_task
@transaction.atomic
def delete_and_deploy_resource(instance_pk, new_release_name):
    appinstance = AppInstance.objects.select_for_update().get(pk=instance_pk)

    if appinstance:
        # The instance does exist.
        parameters = appinstance.parameters
        results = controller.delete(parameters)

        if results.returncode == 0:
            post_delete_hooks(appinstance)
            deploy_resource(appinstance.pk)
            try:
                rel_name_obj = ReleaseName.objects.get(
                    name=new_release_name, project=appinstance.project, status="active"
                )
                rel_name_obj.status = "in-use"
                rel_name_obj.app = appinstance
                rel_name_obj.save()
            except Exception as e:
                print("Error: Submitted release name not owned by project.")
                print(e)


@shared_task
@transaction.atomic
def deploy_resource(instance_pk, action="create"):
    print("TASK - DEPLOY RESOURCE...")
    appinstance = AppInstance.objects.select_for_update().get(pk=instance_pk)

    results = controller.deploy(appinstance.parameters)
    stdout, stderr = process_helm_result(results)

    if results.returncode == 0:
        print("Helm install succeeded")

        helm_info = {
            "success": True,
            "info": {"stdout": stdout, "stderr": stderr},
        }
    else:
        print("Helm install failed")
        helm_info = {
            "success": False,
            "info": {"stdout": stdout, "stderr": stderr},
        }

    appinstance.info["helm"] = helm_info
    appinstance.save()

    if results.returncode != 0:
        print(appinstance.info["helm"])
    else:
        post_create_hooks(appinstance)


@shared_task
@transaction.atomic
def delete_resource(pk):
    appinstance = AppInstance.objects.select_for_update().get(pk=pk)

    if appinstance and appinstance.state != "Deleted":
        # The instance does exist.
        parameters = appinstance.parameters
        # TODO: Check that the user has the permission required to delete it.

        # TODO: Fix for multicluster setup
        # TODO: We are assuming this URI here, but we should allow
        # for other forms.
        # The instance should store information about this.

        # Invoke chart controller
        results = controller.delete(parameters)

        if results.returncode == 0 or "release: not found" in results.stderr.decode("utf-8"):
            status = AppStatus(appinstance=appinstance)
            status.status_type = "Deleting..."
            appinstance.state = "Deleting..."
            status.save()
            print("CALLING POST DELETE HOOKS")
            post_delete_hooks(appinstance)
        else:
            status = AppStatus(appinstance=appinstance)
            status.status_type = "FailedToDelete"
            status.save()
            appinstance.state = "FailedToDelete"
        appinstance.save(update_fields=["state"])


@shared_task
@transaction.atomic
def delete_resource_permanently(appinstance):
    parameters = appinstance.parameters

    # Invoke chart controller
    results = controller.delete(parameters)

    if not (results.returncode == 0 or "release: not found" in results.stderr.decode("utf-8")):
        status = AppStatus(appinstance=appinstance)
        status.status_type = "FailedToDelete"
        status.save()
        appinstance.state = "FailedToDelete"

    release_name(appinstance)

    appinstance.delete()


@app.task
def get_resource_usage():
    timestamp = time.time()

    args = ["kubectl", "get", "--raw", "/apis/metrics.k8s.io/v1beta1/pods"]
    results = subprocess.run(args, capture_output=True)

    pods = []
    try:
        res_json = json.loads(results.stdout.decode("utf-8"))
        pods = res_json["items"]
    except:  # noqa E722 TODO: Add exception
        pass

    resources = dict()

    args_pod = ["kubectl", "-n", f"{settings.NAMESPACE}" "get", "po", "-o", "json"]
    results_pod = subprocess.run(args_pod, capture_output=True)
    results_pod_json = json.loads(results_pod.stdout.decode("utf-8"))
    try:
        for pod in results_pod_json["items"]:
            if (
                "metadata" in pod
                and "labels" in pod["metadata"]
                and "release" in pod["metadata"]["labels"]
                and "project" in pod["metadata"]["labels"]
            ):
                pod_name = pod["metadata"]["name"]
                resources[pod_name] = dict()
                resources[pod_name]["labels"] = pod["metadata"]["labels"]
                resources[pod_name]["cpu"] = 0.0
                resources[pod_name]["memory"] = 0.0
                resources[pod_name]["gpu"] = 0
    except:  # noqa E722 TODO: Add exception
        pass

    try:
        for pod in pods:
            podname = pod["metadata"]["name"]
            if podname in resources:
                containers = pod["containers"]
                cpu = 0
                mem = 0
                for container in containers:
                    cpun = container["usage"]["cpu"]
                    memki = container["usage"]["memory"]
                    try:
                        cpu += int(cpun.replace("n", "")) / 1e6
                    except:  # noqa E722 TODO: Add exception
                        print("Failed to parse CPU usage:")
                        print(cpun)
                    if "Ki" in memki:
                        mem += int(memki.replace("Ki", "")) / 1000
                    elif "Mi" in memki:
                        mem += int(memki.replace("Mi", ""))
                    elif "Gi" in memki:
                        mem += int(memki.replace("Mi", "")) * 1000

                resources[podname]["cpu"] = cpu
                resources[podname]["memory"] = mem
    except:  # noqa E722 TODO: Add exception
        pass
    # print(json.dumps(resources, indent=2))

    for key in resources.keys():
        entry = resources[key]
        # print(entry['labels']['release'])
        try:
            appinstance = AppInstance.objects.get(parameters__contains={"release": entry["labels"]["release"]})
            # print(timestamp)
            # print(appinstance)
            # print(entry)
            datapoint = ResourceData(
                appinstance=appinstance,
                cpu=entry["cpu"],
                mem=entry["memory"],
                gpu=entry["gpu"],
                time=timestamp,
            )
            datapoint.save()
        except:  # noqa E722 TODO: Add exception
            print("Didn't find corresponding AppInstance: {}".format(key))

    # print(timestamp)
    # print(json.dumps(resources, indent=2))


@app.task
def sync_mlflow_models():
    mlflow_apps = AppInstance.objects.filter(~Q(state="Deleted"), project__status="active", app__slug="mlflow")
    for mlflow_app in mlflow_apps:
        if mlflow_app.project is None or mlflow_app.project.mlflow is None:
            continue

        url = "http://{}/{}".format(
            mlflow_app.project.mlflow.host,
            "api/2.0/mlflow/model-versions/search",
        )
        res = False
        try:
            res = requests.get(url)
        except Exception as err:
            print("Call to MLFlow Server failed.")
            print(err, flush=True)

        if res:
            models = res.json()
            print(models)
            if len(models) > 0:
                for item in models["model_versions"]:
                    # print(item)
                    name = item["name"]
                    version = "v{}.0.0".format(item["version"])
                    release = "major"
                    source = item["source"].replace("s3://", "").split("/")
                    run_id = source[2]
                    path = "/".join(source[1:])
                    project = mlflow_app.project
                    uid = run_id
                    s3 = S3.objects.get(pk=mlflow_app.parameters["s3"]["pk"])
                    model_found = True
                    try:
                        stackn_model = Model.objects.get(uid=uid)
                    except:  # noqa E722 TODO: Add exception
                        model_found = False
                    if not model_found:
                        obj_type = ObjectType.objects.filter(slug="mlflow")
                        if obj_type.exists():
                            model = Model(
                                version=version,
                                project=project,
                                name=name,
                                uid=uid,
                                release_type=release,
                                s3=s3,
                                bucket="mlflow",
                                path=path,
                            )
                            model.save()
                            model.object_type.set(obj_type)
                        else:
                            raise EmptyResultSet
                    else:
                        if item["current_stage"] == "Archived" and stackn_model.status != "AR":
                            stackn_model.status = "AR"
                            stackn_model.save()
                        if item["current_stage"] != "Archived" and stackn_model.status == "AR":
                            stackn_model.status = "CR"
                            stackn_model.save()
        else:
            print("WARNING: Failed to fetch info from MLflow Server: {}".format(url))


@app.task
def clean_resource_usage():
    curr_timestamp = time.time()
    ResourceData.objects.filter(time__lte=curr_timestamp - 48 * 3600).delete()


@app.task
def remove_deleted_app_instances():
    apps = AppInstance.objects.filter(state="Deleted")
    print("NUMBER OF APPS TO DELETE: {}".format(len(apps)))
    for instance in apps:
        try:
            name = instance.name
            print("Deleting app instance: {}".format(name))
            instance.delete()
            print("Deleted app instance: {}".format(name))
        except Exception as err:
            print("Failed to delete app instances.")
            print(err)


@app.task
def clear_table_field():
    all_apps = AppInstance.objects.all()
    for instance in all_apps:
        instance.table_field = "{}"
        instance.save()

    all_apps = Apps.objects.all()
    for instance in all_apps:
        instance.table_field = "{}"
        instance.save()


@app.task
def purge_tasks():
    """
    Remove tasks from queue to avoid overflow
    """
    app.control.purge()


@app.task
def delete_old_objects():
    """
    Deletes apps of category Develop (e.g., jupyter-lab, vscode etc)

    Setting the threshold to 7 days. If any app is older than this, it will be deleted.
    The deleted resource will still exist in the database, but with status "Deleted"

    TODO: Make this a variable in settings.py and use the same number in templates
    """

    def get_old_apps(threshold, category):
        threshold_time = timezone.now() - timezone.timedelta(days=threshold)
        return AppInstance.objects.filter(created_on__lt=threshold_time, app__category__name=category)

    old_develop_apps = get_old_apps(threshold=7, category="Develop")
    old_minio_apps = get_old_apps(threshold=1, category="Manage Files")
    for app_ in old_develop_apps:
        delete_resource.delay(app_.pk)

    for app_ in old_minio_apps:
        delete_resource.delay(app_.pk)


@shared_task(bind=True, max_retries=None)
def init_event_listener(self, namespace, label_selector):
    """
    The event listener takes the latest event and checks if a corresponding appinstance
    should be updated. It uses the creation timestamp to always use the status of the youngest pod
    in a helm release.
    """
    k8s_api = setup_client()
    k8s_watch = watch.Watch()
    try:
        status_data = {}
        for event in k8s_watch.stream(k8s_api.list_namespaced_pod, namespace=namespace, label_selector=label_selector):
            pod = event["object"]

            status = get_status(pod)
            status = status[:15]
            release = pod.metadata.labels["release"]
            creation_timestamp = pod.metadata.creation_timestamp
            deletion_timestamp = pod.metadata.deletion_timestamp

            appinstance = AppInstance.objects.filter(parameters__contains={"release": release}).last()

            if appinstance:
                # Case 1 - Set unseen release
                if release not in status_data:
                    status_data[release] = {
                        "creation_timestamp": creation_timestamp,
                        "deletion_timestamp": deletion_timestamp,
                        "status": status,
                    }

                # If older pod, skip
                if (
                    creation_timestamp < status_data[release]["creation_timestamp"]
                    or status == status_data[release]["status"]
                ):
                    continue

                # If pod is same and deleted, set deleted stamp
                elif creation_timestamp == status_data[release]["creation_timestamp"] and deletion_timestamp:
                    status = "Deleted"
                    appinstance.deleted_on = timezone.now()

                # If pod is newer, update
                status_data[release] = {
                    "creation_timestamp": creation_timestamp,
                    "deletion_timestamp": deletion_timestamp,
                    "status": status,
                }
                status_object = AppStatus(appinstance=appinstance)
                update_status(appinstance, status_object, status)
    except Exception as exc:
        print("Event listner exception occured", exc)
        # Catch other exceptions to trigger a retry
        raise self.retry(exc=exc, countdown=10)


@worker_ready.connect
def on_worker_ready(**kwargs):
    """
    This function starts the event listener in a given namespace.
    When the Celery worker is ready, the task is started.
    """
    label_selector = "type=app"
    NAMESPACE = settings.NAMESPACE
    sync_all_statuses(namespace=NAMESPACE, label_selector=label_selector)
    init_event_listener.apply_async(args=(NAMESPACE, label_selector), countdown=1)


def setup_client():
    """
    Sets up the kubernetes python client and event streamer
    """
    try:
        config.load_incluster_config()
    except config.ConfigException:
        try:
            config.load_kube_config(settings.KUBECONFIG)
        except config.ConfigException as e:
            raise config.ConfigException(
                "Could not set the cluster config. Try to use the cluster.conf file or set incluster config"
            ) from e

    k8s_api = client.CoreV1Api()

    return k8s_api


def get_status(pod):
    """
    Returns the status of a pod by looping through each container
    and checking the status.
    """
    container_statuses = pod.status.container_statuses

    if container_statuses is not None:
        for container_status in container_statuses:
            state = container_status.state

            if state is not None:
                terminated = state.terminated

                if terminated is not None:
                    reason = terminated.reason
                    return mapped_status(reason)

                waiting = state.waiting

                if waiting is not None:
                    reason = waiting.reason
                    return mapped_status(reason)
        else:
            running = state.running
            ready = container_status.ready
            if running and ready:
                return "Running"
            else:
                return "Pending"

    return pod.status.phase


def mapped_status(reason: str) -> str:
    return K8S_STATUS_MAP.get(reason, reason)


def sync_all_statuses(namespace, label_selector):
    """
    Syncs the status of all apps with a pod that is on the cluster
    """
    k8s_api = setup_client()
    for pod in k8s_api.list_namespaced_pod(namespace=namespace, label_selector=label_selector).items:
        status = pod.status.phase
        release = pod.metadata.labels["release"]
        appinstance = AppInstance.objects.filter(parameters__contains={"release": release}).last()
        if appinstance:
            status_object = AppStatus(appinstance=appinstance)
            update_status(appinstance, status_object, status)


@transaction.atomic
def update_status(appinstance, status_object, status):
    """
    Helper function to update the status of an appinstance and a status object.
    """
    status_object.status_type = status
    status_object.save()
    appinstance.state = status
    appinstance.save(update_fields=["state"])
