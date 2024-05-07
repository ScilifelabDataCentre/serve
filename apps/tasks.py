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

from .models import AppInstance, Apps, AppStatus, AbstractAppInstance

logger = get_logger(__name__)


ReleaseName = apps.get_model(app_label=settings.RELEASENAME_MODEL)


def get_URI(parameters):
    URI = "https://" + parameters["release"] + "." + parameters["global"]["domain"]

    URI = URI.strip("/")
    return URI




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
def delete_resource(serialized_instance):
    
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