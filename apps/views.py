import base64
import json
import subprocess
from datetime import datetime
from urllib.parse import urlencode
from uuid import UUID

import dateutil.parser
import requests
import waffle
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import Http404, HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import HttpResponseRedirect, render, reverse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.utils.http import content_disposition_header
from django.views import View
from guardian.decorators import permission_required_or_403
from rest_framework.exceptions import NotFound

from apps.constants import AppActionOrigin
from apps.types_.subdomain import SubdomainCandidateName
from projects.models import Project
from studio.utils import get_logger

from .app_registry import APP_REGISTRY
from .background_tasks.utils import select_latest_task_records
from .helpers import (
    create_instance_from_form,
    generate_schema_org_compliant_app_metadata,
    get_minio_usage,
    should_trigger_deployment_from_form,
)
from .models import BaseAppInstance
from .tasks import delete_resource

logger = get_logger(__name__)

User = get_user_model()


def _build_project_app_path(project_slug: str, suffix: str) -> str:
    return f"/projects/{project_slug}/apps/{suffix}"


def _build_task_display_fields(status, was_skipped=False):
    if was_skipped:
        return {
            "display_status": "skipped",
            "status_label": "Skipped",
            "status_class": "secondary",
        }

    status_display = {
        "pending": ("pending", "Pending", "secondary"),
        "running": ("running", "Running", "primary"),
        "retrying": ("retrying", "Retrying", "warning"),
        "success": ("success", "Success", "success"),
        "failed": ("failed", "Failed", "danger"),
    }
    display_status, status_label, status_class = status_display.get(status, ("pending", "Pending", "secondary"))
    return {
        "display_status": display_status,
        "status_label": status_label,
        "status_class": status_class,
    }


def _get_task_display_status(task_data):
    return task_data.get("display_status") or ("skipped" if task_data.get("was_skipped") else task_data["status"])


def _serialize_background_task(task):
    duration = task.get_duration()
    result_data = task.result_data if isinstance(task.result_data, dict) else {}
    was_skipped = bool(result_data.get("skipped"))
    has_validation_warning = task.has_validation_warning()
    error_detail = result_data.get("ui_error") or result_data.get("error", {}).get("ui_error")
    display_fields = _build_task_display_fields(task.status, was_skipped=was_skipped)
    if not was_skipped and task.status == "failed" and not task.is_critical:
        display_fields["status_class"] = "warning"
    if not was_skipped and has_validation_warning:
        display_fields["status_label"] = "Warning"
        display_fields["status_class"] = "warning"
    return {
        "id": task.id,
        "run_id": str(task.run_id) if task.run_id else None,
        "task_name": task.task_name,
        "display_name": _format_task_name_for_display(task.task_name),
        "task_type": task.task_type,
        "status": task.status,
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
        "was_skipped": was_skipped,
        "skip_reason": result_data.get("reason", "") if was_skipped else "",
        "error_detail": error_detail if isinstance(error_detail, dict) else None,
        **display_fields,
    }


def _get_project_app_instance(project_slug: str, app_slug: str, app_id: int):
    project_obj = Project.objects.get(slug=project_slug)
    model_class = APP_REGISTRY.get_orm_model(app_slug)
    if not model_class:
        raise PermissionDenied("Application model not found")

    try:
        instance = model_class.objects.get(pk=app_id, project=project_obj)
    except model_class.DoesNotExist as exc:
        raise Http404("An app with this id does not exist in this project.") from exc

    return project_obj, instance


def _build_task_summary(tasks_data):
    return {
        "total": len(tasks_data),
        "pending": sum(1 for t in tasks_data if _get_task_display_status(t) == "pending"),
        "running": sum(1 for t in tasks_data if _get_task_display_status(t) == "running"),
        "success": sum(1 for t in tasks_data if _get_task_display_status(t) == "success"),
        "skipped": sum(1 for t in tasks_data if _get_task_display_status(t) == "skipped"),
        "failed": sum(1 for t in tasks_data if _get_task_display_status(t) == "failed"),
        "retrying": sum(1 for t in tasks_data if _get_task_display_status(t) == "retrying"),
    }


def _build_workflow_state(tasks_data):
    has_failed_critical = any(t["is_critical"] and _get_task_display_status(t) == "failed" for t in tasks_data)
    has_in_progress = any(_get_task_display_status(t) in {"pending", "running", "retrying"} for t in tasks_data)
    ready_for_deploy = bool(tasks_data) and not has_failed_critical and not has_in_progress
    return {
        "blocked": has_failed_critical,
        "ready_for_deploy": ready_for_deploy,
        "has_failed_critical": has_failed_critical,
        "has_in_progress": has_in_progress,
    }


def _get_progress_mode_from_request(request):
    mode = request.GET.get("mode")
    if mode in {"deploy", "metadata_only", "details"}:
        return mode
    return None


def _get_progress_run_id_from_request(request):
    raw_run_id = request.GET.get("run_id")
    if not raw_run_id:
        return None

    try:
        return UUID(raw_run_id)
    except (TypeError, ValueError):
        return None


def _app_has_registered_background_tasks(app_slug: str) -> bool:
    from apps.background_tasks.registry import TASK_REGISTRY

    return bool(TASK_REGISTRY.get_tasks_by_order(app_slug))


def _filter_visible_background_tasks(app_slug: str, tasks):
    from apps.background_tasks.registry import TASK_REGISTRY

    visible_task_names = {task.task_name for task in TASK_REGISTRY.get_tasks_for_app(app_slug)}
    visible_task_names.add("checking_docker_image_availability")
    return [task for task in tasks if task.task_name in visible_task_names]


def _get_latest_visible_run_id(app_slug: str, task_records):
    visible_task_records = _filter_visible_background_tasks(app_slug, task_records)
    latest_task_in_run = max(
        (task for task in visible_task_records if task.run_id),
        key=lambda task: (task.created_at, task.pk),
        default=None,
    )
    return latest_task_in_run.run_id if latest_task_in_run else None


def _get_progress_tasks(instance, run_id=None):
    from apps.models import BackgroundTask

    task_records = list(BackgroundTask.objects.filter(app_instance=instance).order_by("execution_order", "created_at"))
    visible_task_records = _filter_visible_background_tasks(instance.app.slug, task_records)

    selected_run_id = run_id
    if selected_run_id is None:
        selected_run_id = _get_latest_visible_run_id(instance.app.slug, task_records)

    if selected_run_id:
        visible_task_records = [task for task in visible_task_records if task.run_id == selected_run_id]

    return select_latest_task_records(visible_task_records)


def _should_wait_for_current_run(instance, tasks_data, *, run_id=None):
    if run_id is not None:
        return False

    deployment_inputs = _get_deployment_inputs(instance)
    if deployment_inputs["latest_user_action"] not in {"Changing", "Redeploying"}:
        return False

    if not _app_has_registered_background_tasks(instance.app.slug):
        return False

    workflow = _build_workflow_state(tasks_data)
    return workflow["has_failed_critical"] and not workflow["has_in_progress"]


def _build_completed_steps_text(stats):
    return f"{stats['completed']} of {stats['total']} steps completed"


def _build_attention_steps_text(stats, prefix="needs attention"):
    if stats["failed"] == 1:
        return f"1 step {prefix}"
    return f"{stats['failed']} steps {prefix}"


def _resolve_header_field(value, deployment, stats):
    return value(deployment, stats) if callable(value) else value


PROGRESS_HEADER_DEFAULT = {
    "pill_class": "text-bg-secondary",
    "pill_text": "Waiting",
    "title": "Waiting for deployment checks",
    "message": "We have not recorded any deployment work yet.",
    "inline_text": lambda deployment, stats: _build_completed_steps_text(stats),
    "next_step_text": "Keep this page open while the deployment starts.",
}


PROGRESS_HEADER_VARIANTS = {
    "metadata_attention": {
        "pill_class": "text-bg-danger",
        "pill_text": "Saved",
        "title": "Your changes were saved, but deployment still needs attention",
        "message": lambda deployment, stats: deployment["message"],
        "inline_text": lambda deployment, stats: _build_attention_steps_text(stats, "still needs attention"),
        "next_step_text": "Open deployment summary or go back to form.",
    },
    "metadata_running": {
        "pill_class": "text-bg-info",
        "pill_text": "Saved",
        "title": "Your changes were saved",
        "message": lambda deployment, stats: deployment["message"],
        "inline_text": "No redeployment was needed",
        "next_step_text": "Keep this page open while the existing deployment finishes.",
    },
    "metadata_pending": {
        "pill_class": "text-bg-info",
        "pill_text": "Saved",
        "title": "Your changes were saved",
        "message": lambda deployment, stats: deployment["message"],
        "inline_text": "No redeployment was needed",
        "next_step_text": "Open deployment summary if you want more details.",
    },
    "metadata_saved": {
        "pill_class": "text-bg-success",
        "pill_text": "Saved",
        "title": "Your changes were saved",
        "message": "Deployment checks were skipped because only app metadata changed.",
        "inline_text": "No redeployment was needed",
        "next_step_text": "Redirecting to the app details page in about 5 seconds.",
    },
    "deploy_success": {
        "pill_class": "text-bg-success",
        "pill_text": "Ready",
        "title": "Your app is ready",
        "message": "All checks passed and the app finished deploying. Opening the app details page in a few seconds.",
        "inline_text": lambda deployment, stats: _build_completed_steps_text(stats),
        "next_step_text": "Redirecting to the app details page in about 5 seconds.",
    },
    "deploy_attention": {
        "pill_class": "text-bg-danger",
        "pill_text": "Attention needed",
        "title": "We could not finish preparing your app",
        "message": lambda deployment, stats: deployment["message"],
        "inline_text": lambda deployment, stats: _build_attention_steps_text(stats),
        "next_step_text": "Open deployment summary or go back to form.",
    },
    "deploy_running": {
        "pill_class": "text-bg-info",
        "pill_text": "Checking",
        "title": "We are preparing your app",
        "message": "Each deployment check will appear here as it finishes, and then we will deploy the app.",
        "inline_text": lambda deployment, stats: _build_completed_steps_text(stats),
        "next_step_text": "You will be redirected automatically once deployment finishes.",
    },
}


def _build_progress_header_stats(tasks_data, deployment, metadata_only=False):
    task_statuses = [_get_task_display_status(task) for task in tasks_data]
    deploy_step_status = deployment.get("step_status") or deployment["status"]
    all_step_statuses = task_statuses if metadata_only else task_statuses + [deploy_step_status]
    return {
        "total": len(all_step_statuses) or 1,
        "completed": sum(1 for status in all_step_statuses if status in {"success", "failed", "skipped"}),
        "failed": sum(1 for status in all_step_statuses if status == "failed"),
    }


def _resolve_progress_header_state(deployment, workflow, metadata_only=False):
    if metadata_only:
        if deployment["status"] in {"blocked", "failed"}:
            return "metadata_attention"
        if deployment["status"] == "running":
            return "metadata_running"
        if deployment["status"] == "pending":
            return "metadata_pending"
        return "metadata_saved"

    if deployment["status"] == "success":
        return "deploy_success"
    if workflow["blocked"] or deployment["status"] == "failed":
        return "deploy_attention"
    if deployment["status"] == "running" or workflow["has_in_progress"] or workflow["ready_for_deploy"]:
        return "deploy_running"
    return "deploy_waiting"


def _build_progress_header(tasks_data, deployment, workflow, metadata_only=False):
    stats = _build_progress_header_stats(tasks_data, deployment, metadata_only=metadata_only)
    state = _resolve_progress_header_state(deployment, workflow, metadata_only=metadata_only)
    variant = PROGRESS_HEADER_VARIANTS.get(state, {})

    return {
        "pill_class": _resolve_header_field(
            variant.get("pill_class", PROGRESS_HEADER_DEFAULT["pill_class"]), deployment, stats
        ),
        "pill_text": _resolve_header_field(
            variant.get("pill_text", PROGRESS_HEADER_DEFAULT["pill_text"]), deployment, stats
        ),
        "title": _resolve_header_field(variant.get("title", PROGRESS_HEADER_DEFAULT["title"]), deployment, stats),
        "message": _resolve_header_field(variant.get("message", PROGRESS_HEADER_DEFAULT["message"]), deployment, stats),
        "inline_text": _resolve_header_field(
            variant.get("inline_text", PROGRESS_HEADER_DEFAULT["inline_text"]), deployment, stats
        ),
        "next_step_text": _resolve_header_field(
            variant.get("next_step_text", PROGRESS_HEADER_DEFAULT["next_step_text"]), deployment, stats
        ),
    }


def _build_metadata_only_task():
    task_data = {
        "id": "metadata-only",
        "task_name": "metadata_only_update",
        "display_name": "Metadata Change",
        "task_type": "metadata",
        "status": "success",
        "is_critical": False,
        "execution_order": 1,
        "error_message": "",
        "retry_count": 0,
        "max_retries": 0,
        "created_at": None,
        "started_at": None,
        "completed_at": None,
        "duration_seconds": None,
        "can_retry": False,
        "was_skipped": True,
        "skip_reason": "because app only gets redeployed on changes to image, subdomain, permissions and volumes",
    }
    return {
        **task_data,
        **_build_task_display_fields(task_data["status"], was_skipped=task_data["was_skipped"]),
    }


def _get_helm_deploy_success(instance, run_id=None):
    info = getattr(instance, "info", None) or {}
    if not isinstance(info, dict):
        return None

    helm_info = info.get("helm")
    if not isinstance(helm_info, dict):
        return None

    if run_id is not None:
        helm_run_id = helm_info.get("run_id")
        if helm_run_id is not None and str(helm_run_id) != str(run_id):
            return None

    success = helm_info.get("success")
    if isinstance(success, bool):
        return success
    return None


def _get_deployment_inputs(instance, run_id=None):
    app_status = instance.get_app_status()
    latest_user_action = instance.latest_user_action
    helm_deploy_success = _get_helm_deploy_success(instance, run_id=run_id)
    return {
        "app_status": app_status,
        "latest_user_action": latest_user_action,
        "helm_deploy_success": helm_deploy_success,
        "is_transitioning": latest_user_action in {"Creating", "Changing", "Redeploying"},
    }


def _build_deployment_state(instance, workflow, tasks_data, expecting_fresh_tasks=False, run_id=None):
    inputs = _get_deployment_inputs(instance, run_id=run_id)
    app_status = inputs["app_status"]
    latest_user_action = inputs["latest_user_action"]
    helm_deploy_success = inputs["helm_deploy_success"]
    is_transitioning = inputs["is_transitioning"]
    status = "pending"
    label = "Pending"
    message = "Waiting to start deployment."

    if workflow["blocked"]:
        status = "blocked"
        label = "Blocked"
        message = "Deployment cannot continue until the failed required check is resolved."
    elif workflow["has_in_progress"]:
        status = "pending"
        label = "Pending"
        message = "Deployment will start after the checks pass."
    elif expecting_fresh_tasks and not tasks_data:
        status = "pending"
        label = "Pending"
        message = "Waiting for deployment checks to start."
    elif latest_user_action == "Failed" or app_status == "Error" or helm_deploy_success is False:
        status = "failed"
        label = "Failed"
        message = "Deployment hit an error after the checks completed."
    elif app_status == "Running":
        status = "success"
        label = "Done"
        message = "The app is running."
    elif is_transitioning and (tasks_data or helm_deploy_success is not None or workflow["ready_for_deploy"]):
        status = "pending"
        label = "Pending"
        message = "Waiting for app status."
    elif workflow["ready_for_deploy"]:
        status = "pending"
        label = "Pending"
        message = "Waiting for app status."
    elif tasks_data:
        status = "pending"
        label = "Pending"
        message = "Deployment will start after the checks pass."
    elif waffle.switch_is_active("background_tasks"):
        status = "pending"
        label = "Pending"
        message = "Waiting for deployment checks to start."

    return {
        "status": status,
        "label": label,
        "message": message,
        "app_status": app_status,
        "latest_user_action": latest_user_action,
    }


def _build_standard_deployment_step_status(deployment):
    if deployment["status"] == "success":
        return "success"
    if deployment["status"] in {"failed", "blocked"}:
        return "failed"
    if deployment["status"] == "running":
        return "running"
    return "pending"


def _apply_metadata_only_deployment_overrides(instance, workflow, deployment):
    if (
        deployment["status"] == "running"
        and not workflow["blocked"]
        and not workflow["has_in_progress"]
        and instance.get_app_status() == "Running"
        and _get_helm_deploy_success(instance) is not False
    ):
        deployment["status"] = "success"
        deployment["label"] = "Up to date"

    if deployment["status"] == "success":
        deployment["label"] = "Up to date"
        deployment["message"] = "Only app metadata changed, so redeployment was skipped."
        deployment["step_status"] = "skipped"
    elif deployment["status"] == "blocked":
        deployment["message"] = "Your changes were saved, but deployment is blocked by a failed check."
        deployment["step_status"] = "failed"
    elif deployment["status"] == "failed":
        deployment[
            "message"
        ] = "Your changes were saved, but the app still has unresolved deployment issues from the last run."
        deployment["step_status"] = "failed"
    elif deployment["status"] == "running":
        deployment[
            "message"
        ] = "Your changes were saved. No redeployment was needed, and the existing deployment is still in progress."
        deployment["step_status"] = "running"
    else:
        deployment["message"] = (
            "Your changes were saved. No redeployment was needed, and the existing "
            "deployment is still waiting to finish."
        )
        deployment["step_status"] = "pending"

    return deployment


def _build_progress_payload(
    instance,
    tasks_data,
    *,
    metadata_only=False,
    deployment_tasks_data=None,
    expecting_fresh_tasks=False,
    run_id=None,
):
    deployment_tasks = deployment_tasks_data if deployment_tasks_data is not None else tasks_data
    workflow = _build_workflow_state(deployment_tasks)
    deployment = _build_deployment_state(
        instance,
        workflow,
        deployment_tasks,
        expecting_fresh_tasks=expecting_fresh_tasks and not metadata_only,
        run_id=run_id,
    )

    if metadata_only:
        deployment = _apply_metadata_only_deployment_overrides(instance, workflow, deployment)
    else:
        deployment["step_status"] = _build_standard_deployment_step_status(deployment)

    return {
        "tasks": tasks_data,
        "summary": _build_task_summary(tasks_data),
        "workflow": workflow,
        "deployment": deployment,
        "header": _build_progress_header(tasks_data, deployment, workflow, metadata_only=metadata_only),
        "metadata_only": metadata_only,
    }


def _build_progress_state(instance, progress_mode=None, run_id=None):
    metadata_only = progress_mode == "metadata_only"
    if progress_mode == "details":
        tasks = _get_progress_tasks(instance)
        tasks_data = [_serialize_background_task(task) for task in tasks]
        progress_state = _build_progress_payload(instance, tasks_data)
    elif metadata_only:
        tasks = _get_progress_tasks(instance)
        historical_tasks_data = [_serialize_background_task(task) for task in tasks]
        progress_state = _build_progress_payload(
            instance,
            [_build_metadata_only_task()],
            metadata_only=True,
            deployment_tasks_data=historical_tasks_data,
        )
    else:
        has_registered_tasks = _app_has_registered_background_tasks(instance.app.slug)
        deployment_inputs = _get_deployment_inputs(instance)
        tasks = _get_progress_tasks(instance, run_id=run_id)
        tasks_data = [_serialize_background_task(task) for task in tasks]
        if _should_wait_for_current_run(instance, tasks_data, run_id=run_id):
            tasks_data = []
        progress_state = _build_progress_payload(
            instance,
            tasks_data,
            expecting_fresh_tasks=has_registered_tasks
            and (run_id is not None or deployment_inputs["is_transitioning"]),
            run_id=run_id,
        )

    return progress_state


def _build_progress_status_api_url(project_slug, app_slug, app_id, progress_mode=None, run_id=None):
    url = reverse(
        "apps:background_tasks_status",
        kwargs={"project": project_slug, "app_slug": app_slug, "app_id": app_id},
    )
    query_params = {}
    if progress_mode in {"metadata_only", "details"}:
        query_params["mode"] = progress_mode
    if run_id is not None:
        query_params["run_id"] = str(run_id)
    if query_params:
        return f"{url}?{urlencode(query_params)}"
    return url


def _format_task_name_for_display(task_name: str) -> str:
    explicit_labels = {
        "validate_image_public": "Check Image Access",
        "validate_docker_image": "Check Image Compatibility",
        "checking_docker_image_availability": "Check Image Compatibility",
        "doi_provisioning": "Mint DOI",
        "mint_doi": "Mint DOI",
    }

    if task_name in explicit_labels:
        return explicit_labels[task_name]

    return " ".join(part.capitalize() for part in task_name.replace("-", "_").split("_") if part) or "Deployment step"


@method_decorator(
    permission_required_or_403("can_view_project", (Project, "slug", "project")),
    name="dispatch",
)
class GetLogs(View):
    template = "apps/logs.html"

    def get_instance(self, app_slug, app_id, post=False):
        model_class = APP_REGISTRY.get_orm_model(app_slug)
        if model_class:
            return model_class.objects.get(pk=app_id)
        else:
            message = f"Could not find model for slug {app_slug}"
            if post:
                return JsonResponse({"error": message}, status=404)
            else:
                logger.error(message)
                raise PermissionDenied()

    def get_project(self, project_slug, post=False):
        try:
            project = Project.objects.get(slug=project_slug)
            return project
        except Project.DoesNotExist:
            message = "error: Project not found"
            if post:
                return JsonResponse({"error": message}, status=404)
            else:
                logger.error(message)
                raise PermissionDenied()

    def get(self, request, project, app_slug, app_id):
        project = self.get_project(project)
        instance = self.get_instance(app_slug, app_id)

        context = {"instance": instance, "project": project}
        return render(request, self.template, context)

    def post(self, request, project, app_slug, app_id):
        # Validate project and instance existence
        project = self.get_project(project, post=True)
        instance = self.get_instance(app_slug, app_id, post=True)

        # get container name from UI (subdomain or copy-to-pvc) if none exists then use subdomain name
        container = request.POST.get("container", "") or instance.subdomain.subdomain

        # Perform data validation
        if not SubdomainCandidateName(container, project.id).is_valid() and container != "":
            # Handle the validation error
            return JsonResponse({"error": "Invalid container value. It must be alphanumeric or empty."}, status=403)

        if not getattr(instance, "logs_enabled", False):
            return JsonResponse({"error": "Logs not enabled for this instance"}, status=403)

        if not settings.LOKI_SVC:
            return JsonResponse({"error": "LOKI_SVC not set"}, status=403)

        logs = []
        try:
            url = settings.LOKI_SVC + "/loki/api/v1/query_range"
            container = "serve" if instance.app.slug == "shinyproxyapp" else container
            log_query = '{{release="{release}", container="{container}"}}'.format(
                release=instance.subdomain.subdomain,
                container=container,
            )
            logger.info(f"Log query: {log_query}")

            query_params = {
                "query": log_query,
                "limit": 500,
                "since": "24h",
            }

            res = requests.get(url, params=query_params)
            res.raise_for_status()  # Raise an HTTPError for bad responses (4xx and 5xx)

            res_json = res.json().get("data", {}).get("result", [])

            for item in res_json:
                for log_line in reversed(item["values"]):
                    # Separate timestamp and log message
                    timestamp, log_message = log_line[0], log_line[1]
                    if len(log_message) < 2:
                        continue  # Skip log lines that do not have a message

                    # Parse and format the timestamp
                    try:
                        formatted_time = datetime.fromtimestamp(int(timestamp) / 1e9).strftime("%Y-%m-%d %H:%M:%S")
                        logs.append([formatted_time, log_message])
                    except ValueError as ve:
                        logger.warning(f"Timestamp parsing failed: {ve}")
                        logs.append(["-", log_message])
                        continue

        except requests.RequestException as e:
            logger.error(f"HTTP request failed: {e}", exc_info=True)
            return JsonResponse({"error": "Failed to retrieve logs from Loki"}, status=500)
        except KeyError as e:
            logger.error(f"Unexpected response format: {e}", exc_info=True)
            return JsonResponse({"error": "Unexpected response format from Loki"}, status=500)
        except Exception as e:
            logger.error(f"An unexpected error occurred: {e}", exc_info=True)
            return JsonResponse({"error": "An unexpected error occurred"}, status=500)

        return JsonResponse({"data": logs})


@method_decorator(
    permission_required_or_403("can_view_project", (Project, "slug", "project")),
    name="dispatch",
)
class GetStatusView(View):
    def post(self, request, project):
        body = request.POST.get("apps", "")

        result = {}

        if len(body) > 0:
            arr = body.split(",")

            for orm_model in APP_REGISTRY.iter_orm_models():
                instances = orm_model.objects.filter(pk__in=arr)

                for instance in instances:
                    status = instance.get_app_status()

                    # Also set the k8s app status
                    k8s_app_status_object = instance.k8s_user_app_status
                    if k8s_app_status_object:
                        k8s_app_status = k8s_app_status_object.status
                    else:
                        k8s_app_status = None

                    status_group = instance.get_status_group()

                    obj = {
                        "status": status,
                        "statusGroup": status_group,
                        "latestUserAction": instance.latest_user_action,
                        "k8sStatus": k8s_app_status,
                    }

                    result[f"{instance.app.slug}-{instance.pk}"] = obj

            return JsonResponse(result)

        return JsonResponse(result)


@permission_required_or_403("can_view_project", (Project, "slug", "project"))
def delete(request, project, app_slug, app_id):
    model_class = APP_REGISTRY.get_orm_model(app_slug)
    logger.info(f"Deleting app type {model_class} with id {app_id}")

    if model_class is None:
        raise PermissionDenied()

    instance = model_class.objects.get(pk=app_id) if app_id else None

    if instance is None:
        raise PermissionDenied()

    if not instance.app.user_can_delete:
        return HttpResponseForbidden()

    # Prevent deletion of public apps with published DOIs (unless user is admin)
    if (
        not request.user.is_superuser
        and hasattr(instance, "access")
        and instance.access == "public"
        and hasattr(instance, "app_doi")
        and instance.app_doi
    ):
        return HttpResponseForbidden("Cannot delete public apps with published DOIs.")

    serialized_instance = instance.serialize()

    delete_resource.delay(serialized_instance, AppActionOrigin.USER.value)

    # fix: in case appinstance is public switch to private
    instance.access = "private"
    # instance.save(update_fields=["access"])

    # Set latest_user_action to Deleting
    # This hides the app from the user UI
    instance.latest_user_action = "Deleting"
    instance.deleted_on = timezone.now()
    instance.save(update_fields=["latest_user_action", "deleted_on", "access"])

    return HttpResponseRedirect(
        reverse(
            "projects:details",
            kwargs={
                "project_slug": str(project),
            },
        )
    )


@method_decorator(
    permission_required_or_403("can_view_project", (Project, "slug", "project")),
    name="dispatch",
)
class CreateApp(View):
    template_name = "apps/create_view.html"

    def get(self, request, project, app_slug, app_id=None):
        # TODO This is a bit confusing. project is actually project_slug. So it would be better to rename it
        # Look in studio/urls.py There is <project>. It's being passed from here there
        # But need to make sure, that that's the only place where it's being passed
        project_slug = project
        project = Project.objects.get(slug=project_slug)

        if request.user.is_superuser and project.status == "deleted":
            return HttpResponse("This project has been deleted by the user.")

        try:
            form = self.get_form(request, project, app_slug, app_id)
        except PermissionDenied as e:
            # Check if this is a metadata fetch error by examining the message
            if "system error while fetching metadata" in str(e):
                messages.error(request, str(e))
                return HttpResponseRedirect(reverse("projects:details", kwargs={"project_slug": project_slug}))
            else:
                # Re-raise if it's a different permission error
                raise

        if form is None or not getattr(form, "is_valid", False):
            raise PermissionDenied()

        form_header = "Update" if app_id else "Create"

        return render(
            request,
            self.template_name,
            {
                "form": form,
                "project": project,
                "app_id": app_id,
                "app_slug": app_slug,
                "form_header": form_header,
                "user": request.user,
                "model_name": str(APP_REGISTRY.get_orm_model(app_slug).__name__).lower(),
            },
        )

    @transaction.atomic
    def post(self, request, project, app_slug, app_id=None):
        # App id is used when updating an existing app instance

        # TODO Same as in get method
        project_slug = project
        project = Project.objects.get(slug=project_slug)

        form = self.get_form(request, project, app_slug, app_id)
        if form is None:
            raise PermissionDenied()

        if not form.is_valid():
            form_header = "Update" if app_id else "Create"
            return render(
                request,
                self.template_name,
                {
                    "form": form,
                    "project": project,
                    "app_id": app_id,
                    "app_slug": app_slug,
                    "form_header": form_header,
                    "user": request.user,
                    "model_name": str(APP_REGISTRY.get_orm_model(app_slug).__name__).lower(),
                },
            )

        should_deploy = should_trigger_deployment_from_form(form, app_id=app_id)

        # Otherwise we can create the instance
        instance_id, progress_run_id = create_instance_from_form(
            form,
            project,
            app_slug,
            app_id,
            should_deploy=should_deploy,
            return_run_id=True,
        )
        progress_url = _build_project_app_path(str(project_slug), f"progress/{app_slug}/{instance_id}")
        if not should_deploy:
            progress_url = f"{progress_url}?mode=metadata_only"
        elif progress_run_id:
            progress_url = f"{progress_url}?{urlencode({'run_id': progress_run_id})}"
        return HttpResponseRedirect(progress_url)

    def get_form(self, request, project, app_slug, app_id):
        model_class, form_class = APP_REGISTRY.get(app_slug)

        logger.info(f"Creating app type {model_class}")
        if not model_class or not form_class:
            logger.error("Could not fetch model or form")
            return None

        # Check if user is allowed
        user_can_edit = False
        user_can_create = False

        if app_id:
            # Updating an existing app instance
            user_can_edit = model_class.objects.user_can_edit(request.user, project, app_slug)
            instance = model_class.objects.filter(pk=app_id, project=project).first()
        else:
            # Create a new app instance
            user_can_create = model_class.objects.user_can_create(request.user, project, app_slug)
            instance = None

        if app_id and instance is None:
            return None

        if user_can_edit or user_can_create:
            form = form_class(request.POST or None, project_pk=project.pk, instance=instance, request=request)

            # Disable access field for public apps to prevent changing access mode
            if app_id and instance and hasattr(instance, "access") and instance.access == "public":
                if hasattr(form, "fields") and "access" in form.fields:
                    form.fields["access"].disabled = True
                    form.fields["access"].help_text = "The apps that have already been made public cannot be hidden."

            return form
            # Maybe this makes typing hard.
        else:
            return None


@method_decorator(
    permission_required_or_403("can_view_project", (Project, "slug", "project")),
    name="dispatch",
)
class DeploymentProgressView(View):
    template = "apps/deployment_progress.html"

    def get(self, request, project, app_slug, app_id):
        project_obj, instance = _get_project_app_instance(project, app_slug, app_id)
        progress_mode = _get_progress_mode_from_request(request) or "deploy"
        progress_run_id = _get_progress_run_id_from_request(request)
        progress_state = _build_progress_state(instance, progress_mode=progress_mode, run_id=progress_run_id)

        context = {
            "instance": instance,
            "project": project_obj,
            "app_slug": app_slug,
            "summary": progress_state["summary"],
            "workflow": progress_state["workflow"],
            "deployment": progress_state["deployment"],
            "header": progress_state["header"],
            "metadata_only": progress_state["metadata_only"],
            "initial_tasks_json": json.dumps(progress_state["tasks"]),
            "status_api_url": _build_progress_status_api_url(
                project_obj.slug,
                app_slug,
                instance.pk,
                progress_mode=progress_mode,
                run_id=progress_run_id,
            ),
            "detail_url": _build_project_app_path(str(project_obj.slug), f"details/{app_slug}/{instance.pk}"),
            "form_url": _build_project_app_path(str(project_obj.slug), f"settings/{app_slug}/{instance.pk}"),
        }

        return render(request, self.template, context)


@method_decorator(
    permission_required_or_403("can_view_project", (Project, "slug", "project")),
    name="dispatch",
)
class AppDetailsView(View):
    template = "apps/details.html"

    def get(self, request, project, app_slug, app_id):
        project_obj, instance = _get_project_app_instance(project, app_slug, app_id)
        tasks = _get_progress_tasks(instance)
        tasks_data = [_serialize_background_task(task) for task in tasks]
        progress_state = _build_progress_payload(instance, tasks_data)

        description = getattr(instance, "description", "")
        source_code_url = getattr(instance, "source_code_url", "")
        image = getattr(instance, "image", "")
        tags = instance.tags.all() if hasattr(instance, "tags") else []
        access = getattr(instance, "access", "")
        details_rows = [
            ("Type", instance.app.name),
            ("Project", project_obj.name),
            ("Status", instance.get_app_status()),
            ("Permissions", access.title() if access else ""),
            ("Subdomain", instance.subdomain.subdomain if instance.subdomain else ""),
            ("URL", instance.url or ""),
            ("Source code", source_code_url),
            ("Docker image", image),
        ]

        context = {
            "instance": instance,
            "project": project_obj,
            "recent_tasks": tasks_data,
            "summary": progress_state["summary"],
            "deployment": progress_state["deployment"],
            "description": description,
            "details_rows": details_rows,
            "tags": tags,
            "project_url": reverse("projects:details", kwargs={"project_slug": project_obj.slug}),
            "public_details_url": reverse("app-metadata", kwargs={"app_id": instance.pk}) if access == "public" else "",
            "background_tasks_url": reverse(
                "apps:background_tasks",
                kwargs={"project": project_obj.slug, "app_slug": app_slug, "app_id": instance.pk},
            ),
            "status_api_url": _build_progress_status_api_url(
                project_obj.slug, app_slug, instance.pk, progress_mode="details"
            ),
        }
        return render(request, self.template, context)


@method_decorator(
    permission_required_or_403("can_view_project", (Project, "slug", "project")),
    name="dispatch",
)
class SecretsView(View):
    """This view is used to display the secrets only of an MLFlow instance for now"""

    template = "apps/secrets_view.html"

    def get(self, request, project, app_slug, app_id):
        instance: BaseAppInstance = APP_REGISTRY.get_orm_model(app_slug).objects.get(pk=app_id)

        username, password = None, None
        if instance.get_app_status() == "Running":
            subdomain = instance.subdomain
            # If release name contains chart name it will be used as a full name.
            # see here: https://github.com/bitnami/charts/blob/main/bitnami/common/templates/_names.tpl#L21-L37
            if "mlflow" in subdomain.subdomain.lower():
                secret_name = f"{subdomain.subdomain}-tracking"
            else:
                secret_name = f"{subdomain.subdomain}-mlflow-tracking"
            username = subprocess.run(
                (
                    "kubectl get secret "
                    f"--namespace {settings.NAMESPACE} {secret_name} "
                    '-o jsonpath="{.data.admin-user}"'
                ).split(),
                check=True,
                text=True,
                capture_output=True,
            ).stdout
            username = base64.b64decode(username).decode()
            password = subprocess.run(
                (
                    "kubectl get secret "
                    f"--namespace {settings.NAMESPACE} {secret_name} "
                    '-o jsonpath="{.data.admin-password}"'
                ).split(),
                check=True,
                text=True,
                capture_output=True,
            ).stdout
            password = base64.b64decode(password).decode()

        minio_used_gib = minio_total_gib = minio_remaining_gib = None
        if instance.get_app_status() == "Running":
            result = get_minio_usage(f"{subdomain.subdomain}-minio")
            if result is not None:
                minio_used_gib, minio_total_gib = result
                minio_remaining_gib = minio_total_gib - minio_used_gib

        context = {
            "mlflow_username": username,
            "mlflow_password": password,
            "mlflow_url": instance.url,
            "minio_used_gib": minio_used_gib,
            "minio_total_gib": minio_total_gib,
            "minio_remaining_gib": minio_remaining_gib,
        }

        return render(request, self.template, context)


def app_metadata(request, app_id):
    # First retrieve the app slug by id
    app = BaseAppInstance.objects.filter(pk=app_id).first()
    if app is None:
        raise NotFound("An app with this id does not exist.")
    app_slug = app.app.slug

    # Get app model instance
    model_class = APP_REGISTRY.get_orm_model(app_slug)
    if not model_class:
        logger.error(f"Missing model for slug: {app_slug}")
        raise PermissionDenied("Application model not found")

    app = model_class.objects.get(pk=app_id)

    if app.access != "public":
        logger.error(f"App with app id '{app_id}' is not 'Public', raising PermissionDenied error")
        raise PermissionDenied("You don't have permission to view this app's metadata")

    # Generate and parse schema
    schema_dict = json.loads(generate_schema_org_compliant_app_metadata(app))
    schema_dict["about"]["additionalProperty"][0]["value"] = dateutil.parser.parse(
        schema_dict["about"]["additionalProperty"][0]["value"]
    )

    # Handle JSON export
    if request.GET.get("format") == "json":
        filename = f"SciLifeLab_Serve_App_{app.name}_metadata.json"
        response = HttpResponse(
            generate_schema_org_compliant_app_metadata(app),
            content_type="application/json",
            headers={"Content-Disposition": content_disposition_header(True, filename)},
        )
        return response

    return render(request, "common/app_metadata.html", {"app": app, "schema_dict": schema_dict})


# Background Task Views


@method_decorator(
    permission_required_or_403("can_view_project", (Project, "slug", "project")),
    name="dispatch",
)
class BackgroundTasksView(View):
    """View to display background tasks for a specific app instance."""

    template = "apps/background_tasks.html"

    def get(self, request, project, app_slug, app_id):
        project_obj, instance = _get_project_app_instance(project, app_slug, app_id)
        tasks = _get_progress_tasks(instance)
        serialized_tasks = [_serialize_background_task(task) for task in tasks]
        serialized_by_id = {task_data["id"]: task_data for task_data in serialized_tasks}
        for task in tasks:
            task_data = serialized_by_id.get(task.id, {})
            task.display_name = task_data.get("display_name", task.task_name)
            task.was_skipped = task_data.get("was_skipped", False)
            task.display_status = task_data.get("display_status", task.status)
            task.status_label = task_data.get("status_label", task.status)
            task.status_class = task_data.get("status_class", "secondary")
            task.has_validation_warning_value = task_data.get("has_validation_warning", False)
        summary = _build_task_summary(serialized_tasks)

        context = {
            "instance": instance,
            "project": project_obj,
            "tasks": tasks,
            "summary": summary,
            "app_slug": app_slug,
            "detail_url": _build_project_app_path(str(project_obj.slug), f"details/{app_slug}/{instance.pk}"),
            "status_api_url": _build_progress_status_api_url(
                project_obj.slug, app_slug, instance.pk, progress_mode="details"
            ),
        }

        return render(request, self.template, context)


@method_decorator(
    permission_required_or_403("can_view_project", (Project, "slug", "project")),
    name="dispatch",
)
class BackgroundTaskStatusAPI(View):
    """API endpoint to get task status for an app instance."""

    def get(self, request, project, app_slug, app_id):
        try:
            _, instance = _get_project_app_instance(project, app_slug, app_id)
        except (Http404, PermissionDenied):
            return JsonResponse({"error": "App instance not found"}, status=404)
        progress_mode = _get_progress_mode_from_request(request) or "deploy"
        progress_run_id = _get_progress_run_id_from_request(request)
        progress_state = _build_progress_state(instance, progress_mode=progress_mode, run_id=progress_run_id)

        return JsonResponse(
            {
                "tasks": progress_state["tasks"],
                "summary": progress_state["summary"],
                "workflow": progress_state["workflow"],
                "deployment": progress_state["deployment"],
                "header": progress_state["header"],
                "metadata_only": progress_state["metadata_only"],
                "instance": {
                    "id": instance.pk,
                    "name": instance.name,
                    "app_status": instance.get_app_status(),
                    "latest_user_action": instance.latest_user_action,
                    "url": instance.url,
                },
            }
        )


@method_decorator(
    permission_required_or_403("can_view_project", (Project, "slug", "project")),
    name="dispatch",
)
class RetryBackgroundTaskView(View):
    """View to manually retry a failed background task."""

    def post(self, request, project, app_slug, app_id, task_id):
        from apps.models import BackgroundTask
        from apps.tasks import retry_background_task

        # Get app instance to verify permissions
        model_class = APP_REGISTRY.get_orm_model(app_slug)
        if not model_class:
            return JsonResponse({"error": "Application model not found"}, status=404)

        try:
            instance = model_class.objects.get(pk=app_id)
        except model_class.DoesNotExist:
            return JsonResponse({"error": "App instance not found"}, status=404)

        # Get the task
        try:
            task = BackgroundTask.objects.get(id=task_id, app_instance=instance)
        except BackgroundTask.DoesNotExist:
            return JsonResponse({"error": "Task not found"}, status=404)

        if task.status != "failed":
            return JsonResponse({"error": f"Cannot retry task with status '{task.status}'"}, status=400)

        # Trigger retry
        retry_background_task.delay(task_id)

        logger.info(f"User {request.user.username} initiated retry for task {task_id} " f"on app {app_id}")

        return JsonResponse({"success": True, "message": "Task retry initiated"})


class AdminBackgroundTasksView(View):
    """Admin view to see all background tasks across all apps."""

    template = "apps/admin_background_tasks.html"

    # NOTE: This view is mounted under /projects/<project>/apps/ so Django will pass `project` in kwargs.
    def get(self, request, project, *args, **kwargs):
        from apps.models import BackgroundTask

        # Only allow superusers
        if not request.user.is_superuser:
            raise PermissionDenied("Only administrators can access this page")

        # Get filter parameters
        status_filter = request.GET.get("status")
        app_type_filter = request.GET.get("app_type")
        is_critical_filter = request.GET.get("is_critical")

        # Start with all tasks
        tasks = BackgroundTask.objects.select_related(
            "app_instance", "app_instance__app", "app_instance__project"
        ).order_by("-created_at")

        # Apply filters
        if status_filter:
            tasks = tasks.filter(status=status_filter)

        if app_type_filter:
            tasks = tasks.filter(app_instance__app__slug=app_type_filter)

        if is_critical_filter:
            is_critical_bool = is_critical_filter.lower() == "true"
            tasks = tasks.filter(is_critical=is_critical_bool)

        # Pagination
        from django.core.paginator import Paginator

        paginator = Paginator(tasks, 50)  # Show 50 tasks per page
        page_number = request.GET.get("page")
        page_obj = paginator.get_page(page_number)

        # Get unique app types for filter dropdown
        from apps.models import Apps

        app_types = Apps.objects.all().order_by("name")

        context = {
            "page_obj": page_obj,
            "app_types": app_types,
            "status_filter": status_filter,
            "app_type_filter": app_type_filter,
            "is_critical_filter": is_critical_filter,
            "project": project,
        }

        return render(request, self.template, context)
