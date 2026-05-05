from datetime import datetime, timedelta
from urllib.parse import urlencode

import dateutil.parser
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import reverse
from django.utils import timezone

from projects.models import Project

from .app_registry import APP_REGISTRY
from .background_tasks.utils import select_latest_task_records

# Tolerance for clock skew between web and status-updater processes.
FRESH_STATUS_SKEW_TOLERANCE = timedelta(seconds=30)

TASK_STATUS_DISPLAY = {
    "pending": ("Pending", "secondary"),
    "running": ("Running", "primary"),
    "retrying": ("Retrying", "warning"),
    "success": ("Success", "success"),
    "failed": ("Failed", "danger"),
    "skipped": ("Skipped", "secondary"),
}

TASK_NAME_LABELS = {
    "validate_image_public": "Check Image Access",
    "validate_docker_image": "Check Image Compatibility",
    "doi_provisioning": "Create a Digital Object Identifier (DOI)",
    "validate_source_code_url": "Check Source Code URL",
}

STEP_STATUS_LABELS = {
    "pending": "Waiting",
    "running": "Running",
    "retrying": "Retrying",
    "warning": "Warning",
    "success": "Done",
    "skipped": "Skipped",
    "failed": "Failed",
}


def build_project_app_path(project_slug: str, suffix: str) -> str:
    return f"/projects/{project_slug}/apps/{suffix}"


def get_project_app_instance(project_slug: str, app_slug: str, app_id: int):
    project_obj = Project.objects.get(slug=project_slug)
    model_class = APP_REGISTRY.get_orm_model(app_slug)
    if not model_class:
        raise PermissionDenied("Application model not found")

    try:
        instance = model_class.objects.get(pk=app_id, project=project_obj)
    except model_class.DoesNotExist as exc:
        raise Http404("An app with this id does not exist in this project.") from exc

    return project_obj, instance


def get_progress_mode_from_request(request):
    return "details" if request.GET.get("mode") == "details" else None


def get_progress_started_at_from_request(request):
    raw_started_at = request.GET.get("started_at")
    if not raw_started_at:
        return None

    try:
        started_at = dateutil.parser.isoparse(raw_started_at)
    except (TypeError, ValueError):
        return None

    if timezone.is_naive(started_at):
        return timezone.make_aware(started_at, timezone.get_current_timezone())

    return started_at


def get_skip_deploy_from_request(request):
    return request.GET.get("skip_deploy", "").lower() == "true"


def get_progress_tasks(instance, started_at=None):
    from apps.background_tasks.registry import TASK_REGISTRY
    from apps.models import BackgroundTask

    task_records = list(BackgroundTask.objects.filter(app_instance=instance).order_by("execution_order", "created_at"))
    visible_task_names = {task.task_name for task in TASK_REGISTRY.get_tasks_for_app(instance.app.slug)}
    visible_task_records = [task for task in task_records if task.task_name in visible_task_names]
    if started_at is not None:
        visible_task_records = [task for task in visible_task_records if task.created_at >= started_at]

    return select_latest_task_records(visible_task_records)


def _format_task_name(task_name: str) -> str:
    if task_name in TASK_NAME_LABELS:
        return TASK_NAME_LABELS[task_name]

    return " ".join(part.capitalize() for part in task_name.replace("-", "_").split("_") if part) or "Deployment step"


def serialize_tasks(tasks):
    serialized_tasks = []
    for task in tasks:
        duration = task.get_duration()
        result_data = task.result_data if isinstance(task.result_data, dict) else {}
        was_skipped = bool(result_data.get("skipped"))
        has_validation_warning = task.has_validation_warning()
        display_status = "skipped" if was_skipped else task.status
        status_label, status_class = TASK_STATUS_DISPLAY.get(display_status, ("Pending", "secondary"))
        validation_warning = (
            result_data.get("validation_warning") if isinstance(result_data.get("validation_warning"), str) else ""
        )

        if display_status == "failed" and not task.is_critical:
            status_class = "warning"
        if display_status == "success" and has_validation_warning:
            status_label = "Warning"
            status_class = "warning"

        error_detail = result_data.get("ui_error") or result_data.get("error", {}).get("ui_error")
        serialized_tasks.append(
            {
                "id": task.id,
                "task_name": task.task_name,
                "display_name": _format_task_name(task.task_name),
                "task_type": task.task_type,
                "status": task.status,
                "display_status": display_status,
                "status_label": status_label,
                "status_class": status_class,
                "is_critical": task.is_critical,
                "execution_order": task.execution_order,
                "error_message": task.error_message,
                "retry_count": task.retry_count,
                "max_retries": task.max_retries,
                "created_at": task.created_at.isoformat() if task.created_at else None,
                "started_at": task.started_at.isoformat() if task.started_at else None,
                "completed_at": task.completed_at.isoformat() if task.completed_at else None,
                "duration_seconds": duration,
                "can_retry": task.status == "failed",
                "has_validation_warning": has_validation_warning,
                "validation_warning": validation_warning,
                "was_skipped": was_skipped,
                "skip_reason": result_data.get("reason", "") if was_skipped else "",
                "error_detail": error_detail if isinstance(error_detail, dict) else None,
            }
        )

    return serialized_tasks


def _build_placeholder_task_data(task_class):
    return {
        "id": None,
        "task_name": task_class.task_name,
        "display_name": _format_task_name(task_class.task_name),
        "task_type": task_class.task_type,
        "status": "pending",
        "display_status": "pending",
        "status_label": TASK_STATUS_DISPLAY["pending"][0],
        "status_class": TASK_STATUS_DISPLAY["pending"][1],
        "is_critical": task_class.is_critical,
        "execution_order": task_class.execution_order,
        "error_message": "",
        "retry_count": 0,
        "max_retries": task_class.max_retries,
        "created_at": None,
        "started_at": None,
        "completed_at": None,
        "duration_seconds": None,
        "can_retry": False,
        "has_validation_warning": False,
        "validation_warning": "",
        "was_skipped": False,
        "skip_reason": "",
        "error_detail": None,
    }


def build_progress_tasks_data(instance, started_at=None):
    from apps.background_tasks.registry import TASK_REGISTRY

    task_classes = TASK_REGISTRY.get_tasks_for_app(instance.app.slug)
    actual_tasks = serialize_tasks(get_progress_tasks(instance, started_at=started_at))
    actual_by_name = {task_data["task_name"]: task_data for task_data in actual_tasks}

    return [
        actual_by_name.get(task_class.task_name, _build_placeholder_task_data(task_class))
        for task_class in task_classes
    ]


def summarize_tasks(tasks_data):
    visible_statuses = [_get_task_visible_status(task_data) for task_data in tasks_data]

    return {
        "total": len(tasks_data),
        "pending": sum(1 for status in visible_statuses if status == "pending"),
        "running": sum(1 for status in visible_statuses if status == "running"),
        "success": sum(1 for status in visible_statuses if status == "success"),
        "warning": sum(1 for status in visible_statuses if status == "warning"),
        "skipped": sum(1 for status in visible_statuses if status == "skipped"),
        "failed": sum(1 for status in visible_statuses if status == "failed"),
        "retrying": sum(1 for status in visible_statuses if status == "retrying"),
    }


def _get_task_visible_status(task_data):
    status = task_data.get("display_status") or ("skipped" if task_data.get("was_skipped") else task_data.get("status"))
    if status == "success" and task_data.get("has_validation_warning") is True:
        return "warning"
    return status or "pending"


def _get_task_subtitle(task_data):
    if task_data.get("task_name") in {"validate_image_public", "validate_docker_image"}:
        return "Required image check" if task_data.get("is_critical") else "Optional image check"
    return "Required check" if task_data.get("is_critical") else "Optional check"


def _get_task_detail(task_data, visible_status):
    task_name = task_data.get("task_name")
    if visible_status == "failed" and task_name == "doi_provisioning":
        return "Could not mint DOI for app."
    if visible_status == "failed" and task_data.get("error_message"):
        return task_data["error_message"]
    if visible_status == "skipped":
        skip_reason = task_data.get("skip_reason", "")
        return f"Skipped: {skip_reason}." if skip_reason else "Skipped for this app."
    if visible_status == "warning":
        return task_data.get("validation_warning") or "Completed with warning."
    if visible_status == "success":
        return "Completed successfully."
    if visible_status == "retrying":
        return "Check did not succeed, retrying now..."
    if visible_status == "running":
        return "Currently running."
    return "Waiting for this step to start."


def _get_step_status_label(status):
    return STEP_STATUS_LABELS.get(status, STEP_STATUS_LABELS["pending"])


def _normalize_deploy_step_status(status):
    if status == "blocked":
        return "failed"
    if status in {"pending", "running", "retrying", "success", "failed"}:
        return status
    return "pending"


def _get_active_task_index(tasks_data):
    """
    Return the first non-terminal task index in execution order.

    The progress UI should show checks moving one-by-one, so only this task
    is rendered with an active visual status.
    """
    active_statuses = {"pending", "running", "retrying"}
    for index, task_data in enumerate(tasks_data):
        if _get_task_visible_status(task_data) in active_statuses:
            return index
    return None


def build_progress_steps(tasks_data, deployment):
    terminal_statuses = {"success", "warning", "failed", "skipped"}
    steps = []
    active_task_index = _get_active_task_index(tasks_data)

    for index, task_data in enumerate(tasks_data):
        visible_status = _get_task_visible_status(task_data)
        step_status = visible_status
        visual_status = visible_status

        # Keep the check timeline linear: only the first non-terminal check
        # should look active. Later checks stay in "Waiting" until their turn.
        if active_task_index is not None:
            if index == active_task_index and visible_status == "pending":
                step_status = "running"
                visual_status = "running"
            elif index > active_task_index and visible_status in terminal_statuses | {"running", "retrying"}:
                step_status = "pending"
                visual_status = "pending"
            elif index != active_task_index and visible_status in {"running", "retrying"}:
                step_status = "pending"
                visual_status = "pending"

        if task_data.get("status") == step_status and task_data.get("status_label"):
            status_label = task_data.get("status_label")
        else:
            status_label = _get_step_status_label(step_status)

        steps.append(
            {
                "key": f"task-{task_data.get('task_name') or task_data.get('id')}",
                "title": task_data.get("display_name") or "Deployment step",
                "subtitle": _get_task_subtitle(task_data),
                "status": step_status,
                "visualStatus": visual_status,
                "statusLabel": status_label,
                "detail": _get_task_detail(task_data, step_status),
                "errorDetail": task_data.get("error_detail"),
            }
        )

    deploy_status = _normalize_deploy_step_status(deployment.get("status", "pending"))
    deploy_detail = "Waiting for the earlier checks to finish."
    deploy_visual_status = deploy_status

    if deployment.get("blocked"):
        deploy_detail = (
            deployment.get("message") or "Deployment cannot continue until the failed required check is resolved."
        )
    elif deploy_status == "pending" and not deployment.get("tasks_in_progress"):
        deploy_detail = deployment.get("message") or (
            "Waiting for app status. Note that this may take up to five minutes or longer "
            "because the app is currently being deployed."
        )
        deploy_visual_status = "running"
    elif deploy_status != "pending":
        deploy_detail = deployment.get("message") or "Waiting to start deployment."

    steps.append(
        {
            "key": "deploy",
            "title": "Deploy app",
            "subtitle": "Final step",
            "status": deploy_status,
            "visualStatus": deploy_visual_status,
            "statusLabel": _get_step_status_label(deploy_status),
            "detail": deploy_detail,
            "errorDetail": None,
        }
    )

    return steps


def _get_helm_deploy_success(instance):
    info = getattr(instance, "info", None) or {}
    if not isinstance(info, dict):
        return None

    helm_info = info.get("helm")
    if not isinstance(helm_info, dict):
        return None

    success = helm_info.get("success")
    if isinstance(success, bool):
        return success
    return None


def _get_deployment_inputs(instance):
    """
    Collect the deploy signals that come from the app instance itself.

    Background tasks tell us whether checks are done or blocked, while these
    fields tell us what happened to the actual deployment afterwards.
    """
    app_status = instance.get_app_status()
    latest_user_action = instance.latest_user_action
    helm_deploy_success = _get_helm_deploy_success(instance)
    status_object = getattr(instance, "k8s_user_app_status", None)
    return {
        "app_status": app_status,
        "latest_user_action": latest_user_action,
        "helm_deploy_success": helm_deploy_success,
        "status_updated_at": getattr(status_object, "time", None),
        "is_transitioning": latest_user_action in {"Creating", "Changing", "Redeploying"},
    }


def _is_status_fresh(status_updated_at, progress_started_at):
    """True if the k8s status reflects the workflow started at progress_started_at."""
    if progress_started_at is None:
        return True
    if status_updated_at is None:
        return False
    if not isinstance(status_updated_at, datetime) or not isinstance(progress_started_at, datetime):
        return False
    if timezone.is_naive(status_updated_at) or timezone.is_naive(progress_started_at):
        return False
    return status_updated_at + FRESH_STATUS_SKEW_TOLERANCE >= progress_started_at


def _build_deployment_state(instance, tasks_data, deployment_inputs=None, progress_started_at=None, skip_deploy=False):
    """
    Build the "Deploy app" step shown after the background checks.

    This step is not a real BackgroundTask row. Instead, it combines:
    - workflow state from the visible task rows
    - deployment signals from the app instance / helm info

    The ordering below is intentional:
    1. blocked required checks
    2. explicit deployment failures once checks are no longer in progress
    3. a running app is terminal success
    4. otherwise we stay pending and explain what we are waiting for
    """
    inputs = deployment_inputs or _get_deployment_inputs(instance)
    app_status = inputs["app_status"]
    latest_user_action = inputs["latest_user_action"]
    helm_deploy_success = inputs["helm_deploy_success"]
    status_updated_at = inputs["status_updated_at"]
    is_transitioning = inputs["is_transitioning"]

    # Task flags. These tell us whether checks are blocking deploy,
    # still running, or already finished for the current visible task set.
    blocked = any(t["is_critical"] and t["display_status"] == "failed" for t in tasks_data)
    tasks_in_progress = any(t["display_status"] in {"pending", "running", "retrying"} for t in tasks_data)
    ready_for_deploy = bool(tasks_data) and not blocked and not tasks_in_progress

    # Once checks are done, the deploy step waits for a fresh app/event status.
    waiting_for_app_status = ready_for_deploy or (
        is_transitioning and (bool(tasks_data) or helm_deploy_success is not None)
    )

    # Deployment can fail independently of the checks, so we keep that
    # separate from the task-derived state above.
    deployment_failed = latest_user_action == "Failed" or app_status == "Error" or helm_deploy_success is False

    if blocked:
        status = "blocked"
        label = "Blocked"
        message = "Deployment cannot continue until the failed required check is resolved."
    elif tasks_in_progress or tasks_data:
        status = "pending"
        label = "Pending"
        message = "Deployment will start after the checks pass."
    else:
        status = "pending"
        label = "Pending"
        message = "Waiting to start deployment."

    has_fresh_running_status = app_status == "Running" and _is_status_fresh(status_updated_at, progress_started_at)

    # Metadata-only updates run the background-task workflow without redeploying helm
    # (skip_deploy=True). In that case there is no helm run to wait on, so once the
    # checks are done the synthetic "Deploy app" tile is finished by definition.
    deploy_skipped_complete = skip_deploy and not blocked and not tasks_in_progress

    if deploy_skipped_complete:
        # No helm run is happening, so prior deploy state (success/failure) is not
        # what this submission is reporting on. Treat the synthetic tile as done
        # as soon as the checks finish.
        status = "success"
        label = "Done"
        message = "Metadata updated. No redeploy was needed."
    elif deployment_failed and not blocked and not tasks_in_progress:
        status = "failed"
        label = "Failed"
        message = "Deployment hit an error after the checks completed."
    elif has_fresh_running_status and not blocked and not tasks_in_progress:
        status = "success"
        label = "Done"
        message = "The app is running."
    elif waiting_for_app_status and not blocked and not tasks_in_progress:
        status = "pending"
        label = "Pending"
        message = (
            "Waiting for app status. Note that this may take up to five minutes or longer "
            "because the app is currently being deployed."
        )

    return {
        "status": status,
        "label": label,
        "message": message,
        "app_status": app_status,
        "latest_user_action": latest_user_action,
        "blocked": blocked,
        "ready_for_deploy": ready_for_deploy,
        "tasks_in_progress": tasks_in_progress,
    }


def build_progress_state(instance, progress_mode=None, progress_started_at=None, skip_deploy=False):
    deployment_inputs = None
    if progress_mode == "details":
        # Details always show the latest visible task history for the app.
        tasks_data = serialize_tasks(get_progress_tasks(instance))
    else:
        # The progress page is scoped to the current submit via started_at so we do
        # not mix in task rows from older deployments. We still project the full
        # expected task list immediately, even before all task rows are created.
        tasks_data = build_progress_tasks_data(instance, started_at=progress_started_at)
        deployment_inputs = _get_deployment_inputs(instance)

    deployment = _build_deployment_state(
        instance,
        tasks_data,
        deployment_inputs=deployment_inputs,
        progress_started_at=progress_started_at,
        skip_deploy=skip_deploy,
    )

    return {
        "tasks": tasks_data,
        "steps": build_progress_steps(tasks_data, deployment),
        "summary": summarize_tasks(tasks_data),
        "deployment": deployment,
    }


def build_progress_status_api_url(
    project_slug, app_slug, app_id, progress_mode=None, progress_started_at=None, skip_deploy=False
):
    url = reverse(
        "apps:background_tasks_status",
        kwargs={"project": project_slug, "app_slug": app_slug, "app_id": app_id},
    )
    query_params = {}
    if progress_mode == "details":
        query_params["mode"] = progress_mode
    if progress_started_at is not None:
        query_params["started_at"] = progress_started_at.isoformat()
    if skip_deploy:
        query_params["skip_deploy"] = "true"
    if query_params:
        return f"{url}?{urlencode(query_params)}"
    return url
