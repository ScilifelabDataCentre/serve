import subprocess
import uuid
from datetime import datetime

import yaml
from celery import shared_task
from django.apps import apps
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.utils import timezone

from apps.app_registry import APP_REGISTRY
from studio.celery import app
from studio.utils import get_logger

from .models import FilemanagerInstance

logger = get_logger(__name__)


@app.task
def delete_old_objects():
    """
    This function retrieves the old apps based on the given threshold, category, and model class.
    It then iterates through the subclasses of BaseAppInstance and deletes the old apps
    for both the "Develop" and "Manage Files" categories.
    TODO: Make app categories and their corresponding thresholds variables in settings.py.
    """

    def get_threshold(threshold):
        return timezone.now() - timezone.timedelta(days=threshold)

    # Handle deletion of apps in the "Develop" category
    for orm_model in APP_REGISTRY.iter_orm_models():
        old_develop_apps = orm_model.objects.filter(
            created_on__lt=get_threshold(7), app__category__name="Develop"
        ).exclude(app_status__status="Deleted")

        for app_ in old_develop_apps:
            delete_resource.delay(app_.serialize())

    # Handle deletion of non persistent file managers
    old_file_managers = FilemanagerInstance.objects.filter(
        created_on__lt=timezone.now() - timezone.timedelta(days=1), persistent=False
    ).exclude(app_status__status="Deleted")
    for app_ in old_file_managers:
        delete_resource.delay(app_.serialize())


@app.task
def clean_up_apps_in_database():
    """
    This task retrieves apps that have been deleted (i.e. got status 'deleted') over a \
    specified amount of days ago and removes them from the database.
    TODO: Make apps_clean_up_threshold_days a variable in settings.py.

    """

    apps_clean_up_threshold_days = 425
    logger.info(
        f"Running task clean_up_apps_in_database to remove all apps that have been deleted more than \
                {apps_clean_up_threshold_days} days ago."
    )

    for orm_model in APP_REGISTRY.iter_orm_models():
        apps_to_be_cleaned_up = orm_model.objects.filter(
            deleted_on__lt=timezone.now() - timezone.timedelta(days=apps_clean_up_threshold_days),
            app_status__status="Deleted",
        )

        if apps_to_be_cleaned_up:
            logger.info(
                f"Removing {len(apps_to_be_cleaned_up)} {apps_to_be_cleaned_up[0].app.name} app(s) from the database."
            )
            for app_ in apps_to_be_cleaned_up:
                app_.delete()


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


@shared_task
def helm_delete(release_name: str, namespace: str = "default") -> tuple[str | None, str | None]:
    """
    Executes a Helm delete command.
    """
    command = f"helm uninstall {release_name} --namespace {namespace} --wait"
    # Execute the command
    try:
        result = subprocess.run(command.split(" "), check=True, text=True, capture_output=True)
        return result.stdout, None
    except subprocess.CalledProcessError as e:
        return e.stdout, e.stderr


@shared_task
def helm_template(chart: str, values_file: str, namespace: str) -> tuple[str | None, str | None]:
    """
    Executes a Helm template command.
    """
    command = f"helm template tmp-release-name {chart} -f {values_file} --namespace {namespace}"
    # Execute the command
    try:
        result = subprocess.run(command.split(" "), check=True, text=True, capture_output=True)
        return result.stdout, None
    except subprocess.CalledProcessError as e:
        return e.stdout, e.stderr


@shared_task
def helm_lint(chart: str, values_file: str, namespace: str) -> tuple[str | None, str | None]:
    """
    Executes a Helm lint command.
    """
    command = f"helm lint {chart} -f {values_file} --namespace {namespace}"
    # Execute the command
    try:
        result = subprocess.run(command.split(" "), check=True, text=True, capture_output=True)
        return result.stdout, None
    except subprocess.CalledProcessError as e:
        return e.stdout, e.stderr


@shared_task
def kubectl_apply_dry(deployment_file: str, target_strategy: str = "client") -> tuple[str | None, str | None]:
    """
    Executes a kubectl apply --dry-run command.
    NOTE: This does not appear to be working. To be replaced.
    """
    command = f"kubectl apply --dry-run={target_strategy} -f {deployment_file}"
    # Execute the command
    try:
        result = subprocess.check_output(command, shell=True)
        # result = subprocess.run(command.split(" "), check=True, text=True, capture_output=True)
        return result.stdout, None
    except subprocess.CalledProcessError as e:
        return e.stdout, e.stderr


def get_manifest_yaml(release_name: str, namespace: str = "default") -> tuple[str | None, str | None]:
    command = f"helm get manifest {release_name} --namespace {namespace}"
    # command = f"kubectl get configmap cm -n default -o yaml | yq eval '.data[\"application.yml\"]'"
    # Execute the command
    logger.debug(f"Executing command: {command}")
    try:
        result = subprocess.run(command.split(" "), check=True, text=True, capture_output=True)
        return result.stdout, None
    except subprocess.CalledProcessError as e:
        return e.stdout, e.stderr


def validate_manifest_file(manifest_file: str) -> tuple[str | None, str | None]:
    """Validates a k8s deployment manifest file."""
    command = f"kubectl apply --dry-run=client -f {manifest_file}"
    # command = f"kubernetes-validate {manifest_file}"
    # Execute the command
    logger.debug(f"Executing command: {command}")
    try:
        result = subprocess.run(command.split(" "), check=True, text=True, capture_output=True)
        return result.stdout, None
    except subprocess.CalledProcessError as e:
        return e.stdout, e.stderr


@shared_task
@transaction.atomic
def deploy_resource(serialized_instance):
    instance = deserialize(serialized_instance)
    logger.info("Deploying resource for instance %s", instance)
    values = instance.k8s_values
    if "ghcr" in instance.chart:
        version = instance.chart.split(":")[-1]
        chart = "oci://" + instance.chart.split(":")[0]
    else:
        version = None
        chart = instance.chart

    # Use a KubernetesDeploymentManifest to manage the manifest validation and files
    from types import KubernetesDeploymentManifest

    kdm = KubernetesDeploymentManifest()

    # Save helm values file for internal reference
    values_file = kdm.get_filepaths()["values_file"]
    with open(values_file, "w") as f:
        f.write(yaml.dump(values))

    # In development, also generate and validate the k8s deployment manifest
    if settings.DEBUG:
        # TODO: make this into a nested function
        output, error = kdm.generate_manifest_yaml_from_template(chart, values_file, values["namespace"])

        # TODO: validate the yaml
        # TODO: delete the file if valid

    # Install the ap using Helm install
    release = values["subdomain"]
    output, error = helm_install(release, chart, values["namespace"], values_file, version)
    success = not error

    helm_info = {"success": success, "info": {"stdout": output, "stderr": error}}

    instance.info = dict(helm=helm_info)
    instance.app_status.status = "Created" if success else "Failed"

    instance.app_status.save()
    instance.save()

    # In development, also generate and validate the k8s deployment manifest
    if settings.DEBUG:
        logger.debug(f"Generating and validating k8s deployment yaml for release {release}")
        # Get the deployment manifest yaml
        output, error = get_manifest_yaml(release)
        if error:
            logger.warning(f"Unable to get the deployment manifest for release {release}. Error: {error}")
        # Save the manifest yaml to this file:
        deployment_file = kdm.get_filepaths()["deployment_file"]
        with open(deployment_file, "w") as f:
            f.write(output)
        if not error:
            # Validate the manifest yaml if there was no error
            logger.debug(f"Validating the deployment manifest yaml for release {release}")

            # TODO: Remove when done testing:
            deployment_file = "./charts/values/app_deployment_invalid.yaml"

            output, error = validate_manifest_file(deployment_file)
            # TODO: Remove this when done testing:
            logger.debug(f"Validation result={output}")

            if error:
                logger.warning(f"Unable to validate the deployment manifest for release {release}. Error: {error}")
            else:
                # Parse the output for any errors:
                if output is not None and "error:" in output:
                    logger.warning(f"The manifest file for release {release} contains errors: {output}")
                else:
                    logger.debug(f"The manifest file for release {release} is valid: {deployment_file}")
                    # Delete the file is there was no error and if it is valid
                    subprocess.run(["rm", "-f", deployment_file])

    # TODO: Uncomment
    # subprocess.run(["rm", "-f", values_file])


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

    helm_info = {"success": success, "info": {"stdout": output, "stderr": error}}

    instance.info = dict(helm=helm_info)
    instance.app_status.save()
    instance.save()


def deserialize(serialized_instance):
    # Check if the input is a dictionary
    if not isinstance(serialized_instance, dict):
        raise ValueError(f"The input must be a dictionary and not {type(serialized_instance)}")

    try:
        model = serialized_instance["model"]
        pk = serialized_instance["pk"]
        app_label, model_name = model.split(".")

        model_class = apps.get_model(app_label, model_name)
        instance = model_class.objects.get(pk=pk)

        return instance
    except (KeyError, ValueError) as e:
        raise ValueError(f"Invalid serialized data format: {e}")
    except ObjectDoesNotExist:
        raise ValueError(f"No instance found for model {model} with pk {pk}")
