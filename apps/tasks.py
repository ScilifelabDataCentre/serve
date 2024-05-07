import json
import subprocess
import time
import uuid
import yaml
from datetime import datetime, timedelta
import requests
from celery import shared_task
from celery.signals import worker_ready
from django.apps import apps
from django.conf import settings
from django.core.exceptions import EmptyResultSet
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from models.models import Model, ObjectType
from projects.models import S3, BasicAuth, Environment, MLFlow
from studio.celery import app
from studio.utils import get_logger

from . import controller
from .models import AppInstance, Apps, AppStatus, AbstractAppInstance

logger = get_logger(__name__)


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
    logger.info("TASK - POST CREATE HOOK...")
    # hard coded hooks for now, we can make this dynamic
    # and loaded from the app specs

    if instance.app.slug == "minio-admin":
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
            logger.error("Oops, something went wrong running the command: %s", cmd)

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
            logger.error("Oops, something went wrong running the command: %s", cmd)

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
    elif instance.app.slug in ("volumeK8s", "netpolicy"):
        # Handle volumeK8s and netpolicy creation/recreation
        instance.state = "Created"
        instance.deleted_on = None
        status = AppStatus(appinstance=instance)
        status.status_type = "Created"
        instance.save()
        status.save()


def release_name(instance):
    # Free up release name (if reserved)
    rel_names = instance.releasename_set.all()

    for rel_name in rel_names:
        rel_name.status = "active"
        rel_name.app = None
        rel_name.save()


def post_delete_hooks(appinstance):
    logger.info("TASK - POST DELETE HOOK...")
    release_name(appinstance)
    project = appinstance.project
    if project.s3storage and project.s3storage.app == appinstance:
        project.s3storage.delete()
    elif project.mlflow and project.mlflow.app == appinstance:
        project.mlflow.delete()
    elif appinstance.app.slug in ("volumeK8s", "netpolicy"):
        # Handle volumeK8s and netpolicy deletion
        appinstance.state = "Deleted"
        appinstance.deleted_on = timezone.now()
        status = AppStatus(appinstance=appinstance)
        status.status_type = "Deleted"
        appinstance.save()
        status.save()


@shared_task
@transaction.atomic
def delete_and_deploy_resource(instance_pk, new_release_name):
    appinstance = AppInstance.objects.select_for_update().get(pk=instance_pk)

    if appinstance:
        delete_resource(appinstance.pk)

        parameters = appinstance.parameters
        parameters["release"] = new_release_name
        appinstance.parameters.update(parameters)
        appinstance.save(update_fields=["parameters", "table_field"])

        try:
            rel_name_obj = ReleaseName.objects.get(name=new_release_name, project=appinstance.project, status="active")
            rel_name_obj.status = "in-use"
            rel_name_obj.app = appinstance
            rel_name_obj.save()
        except Exception:
            logger.error("Error: Submitted release name not owned by project.", exc_info=True)

        deploy_resource(appinstance.pk)


@shared_task
@transaction.atomic
def deploy_resource(instance_pk, action="create"):
    logger.info("TASK - DEPLOY RESOURCE...")
    appinstance = AppInstance.objects.select_for_update().get(pk=instance_pk)

    results = controller.deploy(appinstance.parameters)
    if type(results) is str:
        results = json.loads(results)
        stdout = results["status"]
        stderr = results["reason"]
        logger.info("Helm install failed")
        helm_info = {
            "success": False,
            "info": {"stdout": stdout, "stderr": stderr},
        }
        appinstance.info["helm"] = helm_info
        appinstance.save()
    else:
        stdout, stderr = process_helm_result(results)

        if results.returncode == 0:
            logger.info("Helm install succeeded")

            helm_info = {
                "success": True,
                "info": {"stdout": stdout, "stderr": stderr},
            }
        else:
            logger.error("Helm install failed")
            helm_info = {
                "success": False,
                "info": {"stdout": stdout, "stderr": stderr},
            }
        appinstance.info["helm"] = helm_info
        appinstance.save()
        if results.returncode != 0:
            logger.info(appinstance.info["helm"])
        else:
            post_create_hooks(appinstance)
    return results


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
            logger.info("CALLING POST DELETE HOOKS")
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
        except Exception:
            logger.error("Call to MLFlow Server failed.", exc_info=True)

        if res:
            models = res.json()
            logger.info(models)
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
            logger.warning("WARNING: Failed to fetch info from MLflow Server: %s", url)



@app.task
def remove_deleted_app_instances():
    apps = AppInstance.objects.filter(state="Deleted")
    logger.info("NUMBER OF APPS TO DELETE: %s", len(apps))
    for instance in apps:
        try:
            name = instance.name
            logger.info("Deleting app instance: %s", name)
            instance.delete()
            logger.info("Deleted app instance: %s", name)
        except Exception:
            logger.error("Failed to delete app instances.", exc_info=True)


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

######################################################
from django.core import serializers 



@shared_task
@transaction.atomic
def celery_wrapper(serialized_instance, method_name, *args, **kwargs):
    # Deserialize the input to check if the iterable has exactly one element
    logger.info("TASK - CELERY WRAPPER...")
    deserialized_objects = list(serializers.deserialize("json", serialized_instance))
    
    # Check if the length of the deserialized objects is exactly 1
    if len(deserialized_objects) != 1:
        raise ValueError("Expected exactly one serialized object, but got {}".format(len(deserialized_objects)))
    
    # Get the actual instance from the list
    instance = deserialized_objects[0].object
    logger.info("Instance: %s", instance)     
    # Dynamically call the method on the instance with the given args and kwargs
    method = getattr(instance, method_name, None)
    if method is None:
        raise AttributeError(f"The method {method_name} does not exist on the instance of type {type(instance).__name__}")
    
    # Execute the method
    method(*args, **kwargs)
    
    # Save the instance if changes to the database are made
    instance.save()


def helm_install(instance, release_name, chart, namespace="default", values_file=None, version=None):
    """
    Run a Helm install command.
    
    Args:
    release_name (str): Name of the Helm release.
    chart (str): Helm chart to install.
    namespace (str): Kubernetes namespace to deploy to.
    options (list, optional): Additional options for Helm command in list format.
    
    Returns:
    tuple: Output message and any errors from the Helm command.
    """
    # Base command
    command = f"helm upgrade --install {release_name} {chart} --namespace {namespace}"
    
    if values_file:
        command += f" -f {values_file}"
    
    # Append version if deploying via ghcr
    if version:
        command += f" --version {version} --repository-cache /app/charts/.cache/helm/repository"
    
    logger.debug(f"Running Helm command: {command}")
    # Execute the command
    try:
        result = subprocess.run(command.split(" "), check=True, text=True, capture_output=True)
        return result.stdout, None
    except subprocess.CalledProcessError as e:
        return e.stdout, e.stderr
    


def helm_delete(self, release_name, namespace="default"):
    # Base command
    command = f"helm uninstall {release_name} --namespace {namespace}"
    # Execute the command
    try:
        result = subprocess.run(command.split(" "), check=True, text=True, capture_output=True)
        return result.stdout, None
    except subprocess.CalledProcessError as e:
        return e.stdout, e.stderr
        


@shared_task
@transaction.atomic 
def deploy_resource_new(serialized_instance):
    
    instance = deserialize(serialized_instance)
    
    values = instance.k8s_values
    if "ghcr" in instance.chart:
        version = instance.chart.split(":")[-1]
        chart = "oci://" + instance.chart.split(":")[0]
    # Save helm values file for internal reference
    values_file = "charts/values/{}-{}.yaml".format(str(uuid.uuid4()), str(values["name"]))
    with open(values_file, "w") as f:
        f.write(yaml.dump(values))

    output, error = helm_install(instance, values["subdomain"], chart, values["namespace"], values_file, version)
    success = not error

    helm_info = {
        "success": success,
        "info": {"stdout": output, "stderr": error}
    }

    instance.info = dict(helm = helm_info)
    instance.save()


@shared_task
@transaction.atomic
def delete_resource_new(serialized_instance):
    
    instance = deserialize(serialized_instance)
    
    values = instance.k8s_values
    output, error = helm_delete(instance, values["subdomain"], values["namespace"])
    success = not error
    
    if success:
        if instance.app.slug in ("volumeK8s", "netpolicy"):
            instance.app_status.status = "Deleted"
            instance.deleted_on = datetime.now()
        else: 
            instance.app_status.status = "Deleting..."
    else:
        instance.app_status.status = "FailedToDelete"
        
    helm_info = {
        "success": success,
        "info": {"stdout": output, "stderr": error}
    }

    instance.info = dict(helm = helm_info)
    instance.app_status.save()
    instance.save()


def deserialize(serialized_instance):
    deserialized_objects = list(serializers.deserialize("json", serialized_instance))
    
    # Check if the length of the deserialized objects is exactly 1
    if len(deserialized_objects) != 1:
        raise ValueError("Expected exactly one serialized object, but got {}".format(len(deserialized_objects)))
    
    # Get the actual instance from the list
    return deserialized_objects[0].object