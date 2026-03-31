import re
import subprocess
import uuid
from typing import Any

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
from apps.background_tasks.utils import select_latest_task_records
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


def _build_background_task_error_result(
    error: Exception,
    *,
    stage: str,
    traceback_text: str | None = None,
    retry_count: int | None = None,
    max_retries: int | None = None,
    should_retry: bool | None = None,
) -> dict[str, Any]:
    result = {
        "success": False,
        "error": {
            "type": type(error).__name__,
            "module": type(error).__module__,
            "message": str(error),
            "stage": stage,
        },
    }

    if traceback_text:
        result["error"]["traceback"] = traceback_text
    if retry_count is not None:
        result["error"]["retry_count"] = retry_count
    if max_retries is not None:
        result["error"]["max_retries"] = max_retries
    if should_retry is not None:
        result["error"]["should_retry"] = should_retry

    ui_error = getattr(error, "ui_error", None)
    if ui_error:
        result["ui_error"] = ui_error
        result["error"]["ui_error"] = ui_error

    return result


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
def deploy_resource(self, serialized_instance, run_id: str | None = None):
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

    helm_info = {"success": success, "info": {"stdout": output, "stderr": error}, "run_id": run_id}

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


def resolve_task_app_instance(task_record):
    """
    Resolve the concrete app instance model for a background task when possible.

    BackgroundTask points to BaseAppInstance, but many task implementations expect
    fields that live on the concrete child model (for example CustomAppInstance).
    Fall back to the base instance if a concrete model cannot be resolved.
    """
    base_instance = task_record.app_instance
    app = getattr(base_instance, "app", None)
    app_slug = getattr(app, "slug", None)
    if not app_slug:
        return base_instance

    model_class = APP_REGISTRY.get_orm_model(app_slug)
    if not model_class:
        return base_instance

    try:
        concrete_instance = model_class.objects.get(pk=task_record.app_instance_id)
        logger.debug(
            "background_task.instance_resolved task=%s app_id=%s concrete_model=%s",
            task_record.task_name,
            task_record.app_instance_id,
            model_class.__name__,
        )
        return concrete_instance
    except ObjectDoesNotExist:
        logger.debug(
            "background_task.instance_fallback task=%s app_id=%s base_model=%s",
            task_record.task_name,
            task_record.app_instance_id,
            type(base_instance).__name__,
        )
        return base_instance


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


# Background Task Orchestration


@shared_task(bind=True)
def execute_single_background_task(
    self,
    *args,
    task_db_id: int | None = None,
    task_kwargs_by_task_name: dict[str, dict[str, Any]] | None = None,
):
    """
    Execute a single background task.

    When used in a chain, Celery passes the previous task's result as the first
    positional argument; we accept that and use the last positional (or task_db_id
    kwarg) as the actual task record id.

    Args:
        *args: When first in chain, (task_db_id,). When chained, (previous_result, task_db_id).
        task_db_id: ID of the BackgroundTask model instance (optional if passed via args).
        task_kwargs_by_task_name: Optional mapping of task_name -> kwargs dict passed to
            validate_inputs/execute for that specific task.
    """
    from apps.background_tasks.registry import TASK_REGISTRY
    from apps.models import BackgroundTask

    if task_db_id is not None:
        pass
    elif len(args) == 1:
        task_db_id = args[0]
    elif len(args) >= 2:
        task_db_id = args[-1]
    else:
        logger.error("execute_single_background_task called without task_db_id")
        return {"success": False, "error": "task_db_id required"}

    try:
        task_record = BackgroundTask.objects.get(id=task_db_id)
    except BackgroundTask.DoesNotExist:
        logger.error(f"BackgroundTask {task_db_id} not found")
        return {"success": False, "error": "Task record not found"}

    # Idempotency / duplicate delivery guard: don't re-run terminal or in-flight rows.
    if task_record.status in ("running", "success", "failed"):
        logger.info(
            "Skipping execution for BackgroundTask %s (%s) with status=%s",
            task_record.id,
            task_record.task_name,
            task_record.status,
        )
        return {
            "success": task_record.status == "success",
            "skipped": True,
            "status": task_record.status,
            "task_id": task_record.id,
            "task_name": task_record.task_name,
        }

    # Mark as running
    task_record.mark_as_running(celery_task_id=self.request.id)

    # Get the task class
    task_class = TASK_REGISTRY.get_task_class(task_record.task_name)
    if not task_class:
        error_msg = f"Task '{task_record.task_name}' not found in registry"
        logger.error(error_msg)
        task_record.mark_as_failed(
            error_msg,
            result_data={
                "success": False,
                "error": {
                    "type": "TaskNotRegistered",
                    "message": error_msg,
                },
            },
        )
        return {"success": False, "error": error_msg}

    task_instance = task_class()
    app_instance = resolve_task_app_instance(task_record)
    task_kwargs_by_task_name = task_kwargs_by_task_name or {}
    task_kwargs = {}
    if isinstance(task_kwargs_by_task_name, dict):
        task_kwargs = task_kwargs_by_task_name.get(task_record.task_name) or {}
    task_kwargs = {**task_kwargs, "_task_run_id": str(task_record.run_id) if task_record.run_id else None}

    # Validate inputs
    try:
        if task_kwargs:
            task_instance.validate_inputs(app_instance, **task_kwargs)
        else:
            task_instance.validate_inputs(app_instance)
    except Exception as e:
        import traceback

        error_msg = f"Input validation failed: {str(e)}"
        logger.error(error_msg)
        task_record.mark_as_failed(
            error_msg,
            result_data=_build_background_task_error_result(
                e,
                stage="validate_inputs",
                traceback_text=traceback.format_exc()[-10000:],
            ),
        )
        return {"success": False, "error": error_msg}

    # Execute the task
    try:
        if task_kwargs:
            result = task_instance.execute(app_instance, **task_kwargs)
        else:
            result = task_instance.execute(app_instance)
        task_record.mark_as_success(result_data=result)
        try:
            task_instance.on_success(app_instance, result)
        except Exception as hook_err:
            # Hooks should not be able to flip a successful task into a failed one.
            logger.warning(
                "Background task %s on_success hook failed for app %s: %s",
                task_record.task_name,
                task_record.app_instance_id,
                hook_err,
                exc_info=True,
            )

        logger.info(
            f"Background task {task_record.task_name} completed successfully for app {task_record.app_instance_id}"
        )
        return {"success": True, "result": result}

    except Exception as e:
        import traceback

        error_msg = str(e)
        logger.error(f"Background task {task_record.task_name} failed: {error_msg}", exc_info=True)

        # Check if should retry
        should_retry = task_instance.should_retry(e, task_record.retry_count)

        if should_retry and task_record.can_retry():
            # Schedule retry with exponential backoff
            # NOTE: compute delay before incrementing retry_count so the first retry is the smallest delay.
            retry_delay = task_instance.get_retry_delay(task_record.retry_count)
            logger.info(f"Retrying task {task_record.task_name} in {retry_delay} seconds")

            task_record.mark_as_retrying()
            try:
                task_instance.on_failure(app_instance, e)
            except Exception as hook_err:
                # Still retry even if the failure hook itself errors.
                logger.warning(
                    "Background task %s on_failure hook failed for app %s: %s",
                    task_record.task_name,
                    task_record.app_instance_id,
                    hook_err,
                    exc_info=True,
                )

            # Celery retries here are purely scheduling; DB retry_count/max_retries is the source of truth.
            raise self.retry(exc=e, countdown=retry_delay, max_retries=None)
        else:
            task_record.mark_as_failed(
                error_msg,
                result_data=_build_background_task_error_result(
                    e,
                    stage="execute",
                    traceback_text=traceback.format_exc()[-10000:],
                    retry_count=task_record.retry_count,
                    max_retries=task_record.max_retries,
                    should_retry=bool(should_retry),
                ),
            )
            try:
                task_instance.on_failure(app_instance, e)
            except Exception as hook_err:
                logger.warning(
                    "Background task %s on_failure hook failed for app %s: %s",
                    task_record.task_name,
                    task_record.app_instance_id,
                    hook_err,
                    exc_info=True,
                )

            return {"success": False, "error": error_msg, "is_critical": task_record.is_critical}


@shared_task
@transaction.atomic
def run_background_tasks(
    serialized_instance,
    app_slug,
    task_kwargs_by_task_name: dict[str, dict[str, Any]] | None = None,
    run_id: str | None = None,
):
    """
    Orchestrates background tasks before deployment.

    Creates BackgroundTask records and executes them in order.
    Tasks with same execution_order run in parallel using Celery groups.

    Args:
        serialized_instance: Serialized app instance
        app_slug: App type slug
        task_kwargs_by_task_name: Optional mapping of task_name -> kwargs dict passed to
            validate_inputs/execute for that specific task.
        run_id: Stable identifier for this logical deployment/background-task run.

    Returns:
        Dict with success status and task results
    """
    from celery import chain, group

    from apps.background_tasks.registry import TASK_REGISTRY
    from apps.models import BackgroundTask

    instance = deserialize(serialized_instance)
    logger.info(f"Running background tasks for app {instance.id} ({app_slug})")

    task_kwargs_by_task_name = task_kwargs_by_task_name or {}
    run_uuid = uuid.UUID(run_id) if run_id else uuid.uuid4()

    # Get tasks grouped by execution order
    tasks_by_order = TASK_REGISTRY.get_tasks_by_order(app_slug)

    if not tasks_by_order:
        logger.info(f"No background tasks registered for app type {app_slug}")
        # Proceed directly to deployment, but only after this transaction commits.
        transaction.on_commit(lambda: deploy_resource.delay(serialized_instance, str(run_uuid)))
        return {"success": True, "message": "No tasks to run, proceeding to deployment", "run_id": str(run_uuid)}

    # Create BackgroundTask records for all tasks
    task_records = []
    task_timeout_by_id: dict[int, int] = {}
    for order, tasks in sorted(tasks_by_order.items()):
        for task_class in tasks:
            task_record = BackgroundTask.objects.create(
                app_instance=instance,
                task_name=task_class.task_name,
                task_type=task_class.task_type,
                is_critical=task_class.is_critical,
                execution_order=order,
                max_retries=task_class.max_retries,
                status="pending",
                run_id=run_uuid,
            )
            task_records.append(task_record)
            timeout = getattr(task_class, "timeout_seconds", 300) or 300
            # Provide a small hard-kill buffer above the soft limit.
            task_timeout_by_id[task_record.id] = int(timeout)
            logger.debug("Created task record %s for %s", task_record.id, task_class.task_name)

    # Execute tasks in order
    # Build a chain of groups for sequential execution of parallel tasks
    task_chain = []

    for order in sorted(tasks_by_order.keys()):
        # Get all task records for this order
        order_task_records = [tr for tr in task_records if tr.execution_order == order]

        if len(order_task_records) == 1:
            # Single task - add to chain directly
            tr = order_task_records[0]
            timeout = task_timeout_by_id.get(tr.id, 300)
            task_chain.append(
                execute_single_background_task.si(
                    task_db_id=tr.id, task_kwargs_by_task_name=task_kwargs_by_task_name
                ).set(
                    soft_time_limit=timeout,
                    time_limit=timeout + 30,
                )
            )
        else:
            # Multiple tasks - run in parallel using group
            parallel_tasks = group(
                [
                    execute_single_background_task.si(
                        task_db_id=tr.id,
                        task_kwargs_by_task_name=task_kwargs_by_task_name,
                    ).set(
                        soft_time_limit=task_timeout_by_id.get(tr.id, 300),
                        time_limit=task_timeout_by_id.get(tr.id, 300) + 30,
                    )
                    for tr in order_task_records
                ]
            )
            task_chain.append(parallel_tasks)

    # Add deployment as the final step in the chain
    task_chain.append(check_tasks_and_deploy.s(instance.id, serialized_instance, str(run_uuid)))

    # Execute the chain
    workflow = chain(*task_chain)
    # Ensure BackgroundTask rows are committed before workers try to read them.
    transaction.on_commit(lambda: workflow.apply_async())

    logger.info(f"Started background task workflow for app {instance.id}")
    return {"success": True, "message": f"Started {len(task_records)} background tasks", "run_id": str(run_uuid)}


@shared_task
@transaction.atomic
def check_tasks_and_deploy(previous_results, app_instance_id, serialized_instance, run_id: str | None = None):
    """
    Check if all critical tasks succeeded, then deploy if appropriate.

    This is called as the final step in the background task chain.

    Args:
        previous_results: Results from previous tasks in chain
        app_instance_id: App instance ID
        serialized_instance: Serialized app instance for deployment
    """
    from apps.models import BackgroundTask

    logger.info(f"Checking background tasks before deployment for app {app_instance_id}")

    # Get all tasks for this app instance
    task_qs = BackgroundTask.objects.filter(app_instance_id=app_instance_id).order_by("execution_order", "created_at")
    if run_id:
        task_qs = task_qs.filter(run_id=run_id)
    tasks = select_latest_task_records(list(task_qs))

    # Check if any critical tasks failed in the latest logical run.
    failed_critical_tasks = [task for task in tasks if task.is_critical and task.status == "failed"]

    if failed_critical_tasks:
        failed_names = [task.task_name for task in failed_critical_tasks]
        from apps.background_tasks.feature_flags import (
            background_tasks_nonblocking_deploy,
        )

        if background_tasks_nonblocking_deploy():
            warning_msg = (
                "Critical background tasks failed: "
                f"{', '.join(failed_names)}. Deployment NOT blocked (waffle switch enabled)."
            )
            logger.warning(warning_msg)
            transaction.on_commit(lambda: deploy_resource.delay(serialized_instance, run_id))
            return {
                "success": False,
                "deployed": True,
                "warning": warning_msg,
                "failed_tasks": failed_names,
                "blocked": False,
            }

        error_msg = f"Critical background tasks failed: {', '.join(failed_names)}. Deployment blocked."
        logger.error(error_msg)

        # Update app instance status
        instance = deserialize(serialized_instance)
        instance.latest_user_action = "Failed"
        instance.save(update_fields=["latest_user_action"])

        return {
            "success": False,
            "deployed": False,
            "error": error_msg,
            "failed_tasks": failed_names,
            "blocked": True,
        }

    # All critical tasks passed - proceed with deployment
    logger.info(f"All critical tasks passed for app {app_instance_id}. Proceeding with deployment.")
    transaction.on_commit(lambda: deploy_resource.delay(serialized_instance, run_id))

    return {
        "success": True,
        "deployed": True,
        "message": "All tasks completed, deployment started",
    }


@shared_task
def retry_background_task(task_id: int):
    """
    Manually retry a failed background task.

    Args:
        task_id: BackgroundTask ID

    Returns:
        Dict with success status
    """
    from apps.models import BackgroundTask

    try:
        task_record = BackgroundTask.objects.get(id=task_id)
    except BackgroundTask.DoesNotExist:
        logger.error(f"BackgroundTask {task_id} not found")
        return {"success": False, "error": "Task not found"}

    # Only allow retrying failed tasks here to avoid duplicate concurrent executions
    # when Celery already has a retry scheduled ("retrying").
    if task_record.status != "failed":
        return {
            "success": False,
            "error": f"Task status is '{task_record.status}', can only retry failed tasks",
        }

    # Reset task state
    task_record.status = "pending"
    task_record.error_message = ""
    task_record.retry_count = 0
    task_record.started_at = None
    task_record.completed_at = None
    task_record.result_data = None
    task_record.celery_task_id = ""
    task_record.save()

    # Execute the task
    execute_single_background_task.delay(task_id)

    logger.info(f"Manually retrying background task {task_id}")
    return {"success": True, "message": "Task retry initiated"}
