
import subprocess
import uuid
import yaml
import time
from datetime import datetime


from django.core.exceptions import ObjectDoesNotExist

from celery import shared_task
from django.db import transaction

from django.utils import timezone
from django.apps import apps
from studio.celery import app
from studio.utils import get_logger

from .models import BaseAppInstance, FilemanagerInstance

logger = get_logger(__name__)




@app.task
def delete_old_objects():
    """
    This function retrieves the old apps based on the given threshold, category, and model class.
    It then iterates through the subclasses of BaseAppInstance and deletes the old apps
    for both the "Develop" and "Manage Files" categories.

    """

    def get_threshold(threshold):
        return timezone.now() - timezone.timedelta(days=threshold)
 

    # Handle deletion of apps in the "Develop" category
    for subclass in BaseAppInstance.__subclasses__():
        old_develop_apps = subclass.objects.filter(created_on__lt=get_threshold(7), app__category__name="Develop")
        
        for app_ in old_develop_apps:
            delete_resource.delay(app_.pk)

    # Handle deletion of non persistent file managers
    old_file_managers = FilemanagerInstance.objects.filter(
        created_on__lt=timezone.now() - timezone.timedelta(days=1), persistent=False
        )
    for app_ in old_file_managers:
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
    command = f"helm upgrade --force --install {release_name} {chart} --namespace {namespace}"
    
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
    
    print("######"*10, serialized_instance)
    
    instance = deserialize(serialized_instance)
    print("#########", instance)
    logger.info("Deploying resource for instance %s", instance)
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
    
    instance.app_status.save()
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
    # Check if the input is a dictionary
    if not isinstance(serialized_instance, dict):
        raise ValueError(f"The input must be a dictionary and not {type(serialized_instance)}")

    try:
        model = serialized_instance['model']
        pk = serialized_instance['pk']
        app_label, model_name = model.split('.')
        
        model_class = apps.get_model(app_label, model_name)
        instance = model_class.objects.get(pk=pk)
        
        return instance
    except (KeyError, ValueError) as e:
        raise ValueError(f"Invalid serialized data format: {e}")
    except ObjectDoesNotExist:
        raise ValueError(f"No instance found for model {model} with pk {pk}")

