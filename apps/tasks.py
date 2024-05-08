
import subprocess
import uuid
import yaml
from datetime import datetime

from celery import shared_task
from django.db import transaction
from django.core import serializers 
from django.utils import timezone

from studio.celery import app
from studio.utils import get_logger

from .models import AbstractAppInstance

logger = get_logger(__name__)




@app.task
def delete_old_objects():
    """
    This function retrieves the old apps based on the given threshold, category, and model class.
    It then iterates through the subclasses of AbstractAppInstance and deletes the old apps
    for both the "Develop" and "Manage Files" categories.

    """

    def get_old_apps(threshold, category, model_class):
        threshold_time = timezone.now() - timezone.timedelta(days=threshold)
        return model_class.objects.filter(created_on__lt=threshold_time, app__category__name=category)

    for subclass in AbstractAppInstance.__subclasses__():
        old_develop_apps = get_old_apps(threshold=7, category="Develop", model_class=subclass)
        old_file_manager_apps = get_old_apps(threshold=1, category="Manage Files", model_class=subclass)
        for app_ in old_develop_apps:
            delete_resource.delay(app_.pk)

        for app_ in old_file_manager_apps:
            delete_resource.delay(app_.pk)


def helm_install(release_name, chart, namespace="default", values_file=None, version=None):
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
    


def helm_delete(release_name, namespace="default"):
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
def deploy_resource(serialized_instance):
    
    instance = deserialize(serialized_instance)
    
    values = instance.k8s_values
    if "ghcr" in instance.chart:
        version = instance.chart.split(":")[-1]
        chart = "oci://" + instance.chart.split(":")[0]
    # Save helm values file for internal reference
    values_file = f"charts/values/{str(uuid.uuid4())}.yaml"
    with open(values_file, "w") as f:
        f.write(yaml.dump(values))

    output, error = helm_install(values["subdomain"], chart, values["namespace"], values_file, version)
    success = not error

    helm_info = {
        "success": success,
        "info": {"stdout": output, "stderr": error}
    }

    instance.info = dict(helm = helm_info)
    instance.app_status.status = "Created" if success else "Failed"
    instance.save()


@shared_task
@transaction.atomic
def delete_resource(serialized_instance):
    
    instance = deserialize(serialized_instance)
    
    values = instance.k8s_values
    output, error = helm_delete(values["subdomain"], values["namespace"])
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