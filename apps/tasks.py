import re
import subprocess

import yaml
from celery import shared_task
from django.apps import apps
from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone

from api.services.loki import query_unique_ip_count
from apps.app_registry import APP_REGISTRY
from apps.constants import AppActionOrigin
from apps.helpers import generate_helm_install_command, get_merged_k8s_values
from common.tasks import send_email_task
from studio.celery import app
from studio.utils import get_logger

from .models import BaseAppInstance, FilemanagerInstance

logger = get_logger(__name__)

CHART_REGEX = re.compile(r"^(?P<chart>.+):(?P<version>.+)$")
DEPLOY_RESOURCE_MAX_RETRIES = 3
DEPLOY_RESOURCE_RETRY_BASE_SECONDS = 10
DEPLOY_RESOURCE_RETRY_MAX_SECONDS = 30


class MissingSerializedInstanceError(ValueError):
    """Raised when a serialized model/pk cannot be resolved from the database."""

    def __init__(self, model: str, pk: int, base_instance_exists: bool):
        self.model = model
        self.pk = pk
        self.base_instance_exists = base_instance_exists
        super().__init__(
            f"No instance found for model {model} with pk {pk} (base_instance_exists={base_instance_exists})"
        )


def _retry_countdown(current_retries: int) -> int:
    return min(DEPLOY_RESOURCE_RETRY_BASE_SECONDS * (2**current_retries), DEPLOY_RESOURCE_RETRY_MAX_SECONDS)


@app.task
def delete_old_objects():
    """
    Execution of this function is considered a System-initiated action, hence action=SystemDeleting
    and initiated_by=SYSTEM.

    This function retrieves the old apps based on the given threshold, category, and model class.
    It then iterates through the subclasses of BaseAppInstance and deletes the old apps
    for both the "Develop" and "Manage files" categories.
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

        for app_ in old_develop_apps:
            delete_resource.delay(app_.serialize(), AppActionOrigin.SYSTEM.value)

    # Handle deletion of non persistent file managers
    old_file_managers = FilemanagerInstance.objects.filter(
        created_on__lt=timezone.now() - timezone.timedelta(days=1), persistent=False
    ).exclude(latest_user_action="SystemDeleting")

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
    values_file (str, optional): Path to values file.
    version (str, optional): Chart version.

    Returns:
    tuple: Output message and any errors from the Helm command.
    """
    # Generate command using shared helper function
    command = generate_helm_install_command(
        release_name=release_name,
        chart=chart,
        namespace=namespace,
        values_file=values_file,
        version=version,
    )

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


@shared_task(bind=True, max_retries=DEPLOY_RESOURCE_MAX_RETRIES)
@transaction.atomic
def deploy_resource(self, serialized_instance):
    model = serialized_instance.get("model") if isinstance(serialized_instance, dict) else None
    pk = serialized_instance.get("pk") if isinstance(serialized_instance, dict) else None
    task_id = getattr(self.request, "id", None)

    logger.info(
        "deploy_resource.start task_id=%s model=%s pk=%s retry=%s",
        task_id,
        model,
        pk,
        self.request.retries,
    )

    try:
        instance: BaseAppInstance = deserialize(serialized_instance)
    except MissingSerializedInstanceError as exc:
        retries = self.request.retries
        if retries < self.max_retries:
            countdown = _retry_countdown(retries)
            logger.warning(
                "deploy_resource.missing_instance_retry task_id=%s model=%s pk=%s retry=%s/%s "
                "countdown=%ss base_instance_exists=%s",
                task_id,
                exc.model,
                exc.pk,
                retries + 1,
                self.max_retries,
                countdown,
                exc.base_instance_exists,
            )
            raise self.retry(exc=exc, countdown=countdown)

        logger.error(
            "deploy_resource.missing_instance_exhausted task_id=%s model=%s pk=%s retries=%s "
            "base_instance_exists=%s",
            task_id,
            exc.model,
            exc.pk,
            retries,
            exc.base_instance_exists,
        )
        raise

    logger.info(
        "deploy_resource.instance_resolved task_id=%s model=%s pk=%s instance_id=%s app_slug=%s",
        task_id,
        model,
        pk,
        instance.pk,
        instance.app.slug,
    )

    deleted_on = getattr(instance, "deleted_on", None)
    if instance.latest_user_action in {"Deleting", "SystemDeleting"} or deleted_on is not None:
        logger.info(
            "deploy_resource.skip_deleting task_id=%s instance_id=%s latest_user_action=%s deleted_on=%s",
            task_id,
            instance.pk,
            instance.latest_user_action,
            deleted_on,
        )
        return

    values = get_merged_k8s_values(instance, ensure_up_to_date=True)
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

    logger.info(
        "deploy_resource.helm_install_start task_id=%s instance_id=%s release=%s namespace=%s chart=%s version=%s",
        task_id,
        instance.pk,
        release,
        values["namespace"],
        chart,
        version,
    )

    # Install the app using Helm install
    output, error = helm_install(release, chart, values["namespace"], values_file, version)
    success = not error

    if not success:
        retries = self.request.retries
        logger.warning(
            "deploy_resource.helm_install_failed task_id=%s instance_id=%s retry=%s/%s release=%s stderr=%s",
            task_id,
            instance.pk,
            retries,
            self.max_retries,
            release,
            error,
        )
        if retries < self.max_retries:
            countdown = _retry_countdown(retries)
            logger.info(
                "deploy_resource.helm_install_retry task_id=%s instance_id=%s retry=%s/%s countdown=%ss",
                task_id,
                instance.pk,
                retries + 1,
                self.max_retries,
                countdown,
            )
            raise self.retry(exc=RuntimeError(error or "Helm install failed"), countdown=countdown)

    logger.info(
        "deploy_resource.helm_install_done task_id=%s instance_id=%s success=%s release=%s",
        task_id,
        instance.pk,
        success,
        release,
    )

    helm_info = {"success": success, "info": {"stdout": output, "stderr": error}}

    instance.info = dict(helm=helm_info)
    # instance.app_status.status = "Created" if success else "Failed"

    # Only update the info field to avoid overriding other modified fields elsewhere
    instance.save(update_fields=["info"])
    logger.info("deploy_resource.info_saved task_id=%s instance_id=%s success=%s", task_id, instance.pk, success)

    # In development, also generate and validate the k8s deployment manifest
    if settings.DEBUG:
        # Previously, we generated and validated the deployment after creation
        # output, error = get_manifest_yaml(release)
        pass

    if not settings.DEBUG and valid_deployment:
        # If valid, then delete both the values and deployment files (if exists)
        subprocess.run(["rm", "-f", values_file])
        if deployment_file:
            subprocess.run(["rm", "-f", deployment_file])

    logger.info(
        "deploy_resource.finish task_id=%s instance_id=%s success=%s valid_deployment=%s",
        task_id,
        instance.pk,
        success,
        valid_deployment,
    )


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
    logger.info(
        "delete_resource.start model=%s pk=%s initiated_by=%s payload_type=%s",
        serialized_instance.get("model") if isinstance(serialized_instance, dict) else None,
        serialized_instance.get("pk") if isinstance(serialized_instance, dict) else None,
        initiated_by_str,
        type(serialized_instance),
    )

    initiated_by = AppActionOrigin(initiated_by_str)
    assert initiated_by == AppActionOrigin.USER or initiated_by == AppActionOrigin.SYSTEM

    instance = deserialize(serialized_instance)

    # Use merged values for consistency, but don't update since we're deleting
    values = get_merged_k8s_values(instance, ensure_up_to_date=False)

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
        logger.info("deserialize.resolved model=%s pk=%s concrete_model=%s", model, pk, model_class.__name__)

        return instance
    except (KeyError, ValueError) as e:
        raise ValueError(f"Invalid serialized data format: {e}")
    except ObjectDoesNotExist:
        base_instance_exists = BaseAppInstance.objects.filter(pk=pk).exists()
        raise MissingSerializedInstanceError(model=model, pk=pk, base_instance_exists=base_instance_exists)


@app.task
def update_cached_app_ip_counts():
    """Update cached IP counts of every app subdomain."""

    logger.info("Starting IP count update task")

    apps = BaseAppInstance.objects.filter(subdomain__isnull=False).select_related("subdomain")

    for serve_app in apps:
        try:
            subdomain = serve_app.subdomain.subdomain
            count = query_unique_ip_count(app_subdomain=subdomain)
            cache.set(f"ip_{subdomain}", count, None)  # Cache indefinitely
        except Exception as e:
            logger.warning(f"Failed to update {subdomain}: {e}")

    logger.info(f"Updated cached IP counts for {apps.count()} apps.")


@app.task
def update_monthly_app_ip_counts():
    """Update monthly cached IP counts of every app subdomain."""

    logger.info("Starting monthly IP count update task")

    apps = BaseAppInstance.objects.filter(subdomain__isnull=False).select_related("subdomain")

    # Get current year and month for the cache key
    current_date = timezone.now()
    year_month = current_date.strftime("%Y%m")

    for serve_app in apps:
        try:
            subdomain = serve_app.subdomain.subdomain
            # Query IP count for the current month
            count = query_unique_ip_count(app_subdomain=subdomain)

            # Store monthly count with year-month in the key
            cache_key = f"monthly_ip_{subdomain}_{year_month}"
            cache.set(cache_key, count, None)  # Cache indefinitely

            logger.debug(f"Updated monthly IP count for {subdomain}: {count}")
        except Exception as e:
            logger.warning(f"Failed to update monthly count for {subdomain}: {e}")

    logger.info(f"Updated monthly cached IP counts for {apps.count()} apps for {year_month}.")


@app.task
def remind_about_link_only_apps():
    """
    This task goes through the link-only apps (those for which Permission level is set to Link)
    and sends email reminders to their owners when it's time to do that. The day when a reminder needs to be sent
    is set in a database variable associated with this app - first set when the app is first saved
    as a link-only app, then the next date is set by this task at the end.
    TODO: Make the time period until the next reminder a variable in settings.py.
    """

    # Define how to send a reminder
    def send_linkonly_reminder_email(app) -> None:
        html_message = render_to_string(
            "apps/reminder_linkonly.html",
            {
                "app_owner_firstname": app.owner.first_name,
                "app_name": app.name,
                "app_url": app.url,
                "project_url_slug": app.project.slug,
            },
        )
        logger.info("Sending reminder email %s", app.owner.email)
        send_email_task(
            subject="Permission level for your app on SciLifeLab Serve",
            message=(
                f"Dear {app.owner.first_name},\n\n"
                f"Your app {app.name} ({app.url}) is published on SciLifeLab Serve with access only to "
                "those with whom you share the URL of the app (permission level Link).\n\n"
                "This is a reminder that we only allow using the Link permission level "
                "temporarily and in certain cases, such as when your app is under development or your "
                "related journal article is under peer review. Is this still the case?\n\n"
                "Please consider changing the permission level for this app to either Public "
                "(information about the app will become publicly findable) or Project "
                "(only members of your project on SciLifeLab Serve will be able to access the app).\n\n"
                "If you have any questions, feel free to get in touch with us - serve@scilifelab.se."
                "\n\n"
                "Kind regards,\n"
                "SciLifeLab Serve team"
            ),
            html_message=html_message,
            recipient_list=[app.owner.email],
            reply_to=[settings.REPLY_TO_EMAIL],
        )

    # Define how to set the next reminder day
    def set_next_linkonly_reminder_date(app, days_to_next_reminder: int) -> None:
        today = timezone.localdate()
        app.reminder_date_linkonly_privacy = today + timezone.timedelta(days=days_to_next_reminder)
        app.save(update_fields=["reminder_date_linkonly_privacy"])

    # Select the apps for which to send a reminder
    send_reminder_apps = []
    seen_ids: set[int] = set()
    for orm_model in APP_REGISTRY.iter_orm_models():
        # only keep models that have the field reminder_date_linkonly_privacy,
        # this field is added only in the model of the app types for which this is relevant
        field_names = {f.name for f in orm_model._meta.get_fields()}
        if "reminder_date_linkonly_privacy" not in field_names:
            continue
        selected = orm_model.objects.filter(
            access="link",
            reminder_date_linkonly_privacy__lte=timezone.now(),
        ).exclude(latest_user_action__in=["SystemDeleting", "Deleting"])
        for obj in selected:
            if obj.pk in seen_ids:  # need to do this because Shiny apps appear twice
                continue
            seen_ids.add(obj.pk)
            send_reminder_apps.append(obj)

    # Send the reminders, set the next reminder date
    days_to_next_reminder = 90
    for app_ in send_reminder_apps:
        send_linkonly_reminder_email(app_)
        set_next_linkonly_reminder_date(app_, days_to_next_reminder)
