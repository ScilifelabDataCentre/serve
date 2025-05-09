import re
import subprocess

import yaml
from celery import shared_task
from django.apps import apps
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.utils import timezone

from apps.app_registry import APP_REGISTRY
from apps.constants import AppActionOrigin
from studio.celery import app
from studio.utils import get_logger

from .models import BaseAppInstance, FilemanagerInstance

logger = get_logger(__name__)

CHART_REGEX = re.compile(r"^(?P<chart>.+):(?P<version>.+)$")


@app.task
def delete_old_objects():
    """
    Execution of this function is considered a System-initiated action, hence action=SystemDeleting
    and initiated_by=SYSTEM.

    This function retrieves the old apps based on the given threshold, category, and model class.
    It then iterates through the subclasses of BaseAppInstance and deletes the old apps
    for both the "Develop" and "Manage Files" categories.
    It skips app instances with action set to SystemDeleting.
    TODO: Make app categories and their corresponding thresholds variables in settings.py.
    """

    def get_threshold(threshold):
        return timezone.now() - timezone.timedelta(days=threshold)

    # Handle deletion of apps in the "Develop" category
    for orm_model in APP_REGISTRY.iter_orm_models():
        old_develop_apps = (
            orm_model.objects.filter(created_on__lt=get_threshold(7), app__category__name="Develop")
            .exclude(latest_user_action="SystemDeleting")
            .exclude(app__slug="mlflow")
        )
        # old: .exclude(app_status__status="Deleted")

        for app_ in old_develop_apps:
            delete_resource.delay(app_.serialize(), AppActionOrigin.SYSTEM.value)

    # Handle deletion of non persistent file managers
    old_file_managers = FilemanagerInstance.objects.filter(
        created_on__lt=timezone.now() - timezone.timedelta(days=1), persistent=False
    ).exclude(latest_user_action="SystemDeleting")
    # old: .exclude(app_status__status="Deleted")

    for app_ in old_file_managers:
        delete_resource.delay(app_.serialize(), AppActionOrigin.SYSTEM.value)


@app.task
def clean_up_apps_in_database():
    """
    This task retrieves apps that have been deleted (i.e. got action 'Deleting') over a \
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
            latest_user_action__in=["Deleting", "SystemDeleting"],
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
def helm_template(
    chart: str, values_file: str, namespace: str = "default", version: str = None
) -> tuple[str | None, str | None]:
    """
    Executes a Helm template command.
    """
    command = f"helm template tmp-release-name {chart} -f {values_file} --namespace {namespace}"

    # Append version if deploying via ghcr
    if version:
        command += f" --version {version} --repository-cache /app/charts/.cache/helm/repository"

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
def _kubectl_apply_dry(deployment_file: str, target_strategy: str = "client") -> tuple[str | None, str | None]:
    """
    Executes a kubectl apply --dry-run command.
    NOTE: This does not appear to be working, but kept for continued testing.
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
    instance: BaseAppInstance = deserialize(serialized_instance)
    logger.info("Deploying resource for instance %s", instance)
    values = instance.k8s_values
    if instance.k8s_values_override:
        values.update(instance.k8s_values_override)
    release = values["subdomain"]
    chart: str = instance.chart
    if "ghcr" in instance.chart:
        version = instance.chart.split(":")[-1]
        chart = "oci://" + instance.chart.split(":")[0]
    elif chart.startswith("oci://"):
        match = CHART_REGEX.match(chart)
        if match:
            chart = match.group("chart")
            version = match.group("version")
    else:
        version = None
        chart = instance.chart

    # Use a KubernetesDeploymentManifest to manage the manifest validation and files
    from apps.types_.kubernetes_deployment_manifest import KubernetesDeploymentManifest

    kdm = KubernetesDeploymentManifest()

    # Save helm values file for internal reference

    values_file, _ = kdm.get_filepaths()
    with open(values_file, "w") as f:
        f.write(yaml.dump(values))

    valid_deployment = True
    deployment_file = None

    # In development, also generate and validate the k8s deployment manifest
    if settings.DEBUG:
        logger.debug(f"Generating and validating k8s deployment yaml for release {release} before deployment.")

        output, error = kdm.generate_manifest_yaml_from_template(
            chart, values_file, values["namespace"], version, save_to_file=True
        )

        _, deployment_file = kdm.get_filepaths()

        # Validate the manifest yaml documents
        is_valid, validation_output, _ = kdm.validate_manifest(output)

        if is_valid:
            logger.debug(f"The deployment manifest file is valid for release {release}")

            # Also validate the kubernetes-pod-patches section
            kpp_data = kdm.extract_kubernetes_pod_patches_from_manifest(output)

            if kpp_data:
                is_valid, message, _ = kdm.validate_kubernetes_pod_patches_yaml(kpp_data)

                if not is_valid:
                    logger.debug(f"The kubernetes-pod-patches section is invalid for release {release}. {message}")
                    valid_deployment = False
        else:
            valid_deployment = False

        if not valid_deployment:
            logger.warning(f"The deployment manifest file is INVALID for release {release}. {validation_output}")

    # Install the app using Helm install
    output, error = helm_install(release, chart, values["namespace"], values_file, version)
    success = not error

    helm_info = {"success": success, "info": {"stdout": output, "stderr": error}}

    instance.info = dict(helm=helm_info)
    # instance.app_status.status = "Created" if success else "Failed"

    # Only update the info field to avoid overriding other modified fields elsewhere
    instance.save(update_fields=["info"])

    # In development, also generate and validate the k8s deployment manifest
    if settings.DEBUG:
        # Previously, we generated and validated the deployment after creation
        # output, error = get_manifest_yaml(release)
        pass

    if valid_deployment:
        # If valid, then delete both the values and deployment files (if exists)
        subprocess.run(["rm", "-f", values_file])
        if deployment_file:
            subprocess.run(["rm", "-f", deployment_file])


@shared_task
@transaction.atomic
def delete_resource(serialized_instance, initiated_by_str: str):
    """
    Deletes a cluster resource object.
    For deletes that are initiated by the system itself (such as recurring tasks),
    the field latest_user_action is set to SystemDeleting. Deletes initiated by end users
    are instead handled by views.
    Note that initiated by is needed because this information cannot be determined
    from the latest_user_action as this is sometimes set after the deletion of the resource.

    Parameters:
    - serialized_instance: A serialized version of the app to be deleted.
    - initiated_by_str: A string of enum AppActionOrigin indicating the source of the deletion (user|system).
    """
    logger.debug(f"Type of serialized_instance is {type(serialized_instance)}")

    initiated_by = AppActionOrigin(initiated_by_str)
    assert initiated_by == AppActionOrigin.USER or initiated_by == AppActionOrigin.SYSTEM

    instance = deserialize(serialized_instance)

    values = instance.k8s_values

    success = False
    if values.get("subdomain") is not None:
        output, error = helm_delete(values["subdomain"], values["namespace"])
        success = not error
    else:
        error_text = f"Subdomain name does not exist. App: {values['name']}, Project: {values['project']['slug']}"
        output, error = error_text, error_text
        logger.error(error_text)

    if success:
        # User actions (Deleting) are now saved by views and helpers.
        # So we do not save any statuses here.
        logger.info(f"Successfully deleted resource type {instance.app.slug}, {values['subdomain']}")
    else:
        # There is no need to save a FailedToDelete status
        # We let the k8s event listener handle this event and together with
        # the instance info we have sufficient troubleshooting information.
        # Note: This can occur if for example the deployment has already been deleted.
        logger.info(f"Failed to delete resource type {instance.app.slug}, {values['subdomain']}, error={error}")

    helm_info = {"success": success, "info": {"stdout": output, "stderr": error}}

    instance.info = dict(helm=helm_info)

    # Note: when we save the app instance object here, we should not overwrite properties
    # with old values, therefore we carefully restrict the updated fields.
    # if instance.app.slug in ("volumeK8s", "netpolicy"):
    if initiated_by == AppActionOrigin.SYSTEM:
        # The delete resource action was initiated by the Serve system.
        # This is a common scenario for "apps" such as volumeK8s, netpolicy, notebooks and file managers.
        instance.latest_user_action = "SystemDeleting"
        instance.deleted_on = timezone.now()
        instance.save(update_fields=["latest_user_action", "deleted_on", "info"])
    else:
        instance.save(update_fields=["info"])


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
