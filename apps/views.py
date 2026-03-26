import base64
import json
import subprocess
from datetime import datetime

import dateutil.parser
import requests
import waffle
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import Http404, HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import HttpResponseRedirect, render, reverse
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from guardian.decorators import permission_required_or_403
from rest_framework.exceptions import NotFound

from apps.constants import AppActionOrigin
from apps.types_.subdomain import SubdomainCandidateName
from projects.models import Project
from studio.utils import get_logger

from .app_registry import APP_REGISTRY
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


def _is_ajax_request(request) -> bool:
    return request.headers.get("x-requested-with") == "XMLHttpRequest"


def _build_project_app_path(project_slug: str, suffix: str) -> str:
    return f"/projects/{project_slug}/apps/{suffix}"


def _serialize_background_task(task):
    duration = task.get_duration()
    result_data = task.result_data if isinstance(task.result_data, dict) else {}
    was_skipped = bool(result_data.get("skipped"))
    return {
        "id": task.id,
        "task_name": task.task_name,
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
        "was_skipped": was_skipped,
        "skip_reason": result_data.get("reason", "") if was_skipped else "",
    }


def _select_latest_task_records(tasks):
    latest_by_name = {}
    for task in sorted(tasks, key=lambda task: (task.created_at, task.pk)):
        latest_by_name[task.task_name] = task

    return sorted(
        latest_by_name.values(),
        key=lambda task: (task.execution_order, task.created_at, task.pk),
    )


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
        "pending": sum(1 for t in tasks_data if t["status"] == "pending"),
        "running": sum(1 for t in tasks_data if t["status"] == "running"),
        "success": sum(1 for t in tasks_data if t["status"] == "success"),
        "failed": sum(1 for t in tasks_data if t["status"] == "failed"),
        "retrying": sum(1 for t in tasks_data if t["status"] == "retrying"),
    }


def _build_workflow_state(tasks_data):
    has_failed_critical = any(t["is_critical"] and t["status"] == "failed" for t in tasks_data)
    has_in_progress = any(t["status"] in {"pending", "running", "retrying"} for t in tasks_data)
    ready_for_deploy = bool(tasks_data) and not has_failed_critical and not has_in_progress
    return {
        "blocked": has_failed_critical,
        "ready_for_deploy": ready_for_deploy,
        "has_failed_critical": has_failed_critical,
        "has_in_progress": has_in_progress,
    }


def _build_deployment_state(instance, workflow, tasks_data):
    app_status = instance.get_app_status()
    latest_user_action = instance.latest_user_action
    is_transitioning = latest_user_action in {"Creating", "Changing", "Redeploying"}
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
    elif app_status == "Running":
        status = "success"
        label = "Done"
        message = "The app is running."
    elif workflow["ready_for_deploy"] or is_transitioning:
        status = "running"
        label = "Deploying"
        message = "Deployment is in progress."
    elif latest_user_action == "Failed" or app_status in {"Error", "Error (NotFound)"}:
        status = "failed"
        label = "Failed"
        message = "Deployment hit an error after the checks completed."
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


def _build_details_task_rows(tasks):
    rows = []
    for task in tasks:
        result_data = task.result_data if isinstance(task.result_data, dict) else {}
        was_skipped = bool(result_data.get("skipped"))
        rows.append(
            {
                "task_name": task.task_name,
                "execution_order": task.execution_order,
                "is_critical": task.is_critical,
                "status_label": "Skipped" if was_skipped else task.get_status_display(),
                "status_class": "secondary" if was_skipped else task.get_status_display_class(),
            }
        )
    return rows


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
            log_query = f'{{release="{instance.subdomain.subdomain}",container="{container}"}}'
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

        form = self.get_form(request, project, app_slug, app_id)

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
            context = {
                "form": form,
                "project": project,
                "app_id": app_id,
                "app_slug": app_slug,
                "form_header": form_header,
                "user": request.user,
                "model_name": str(APP_REGISTRY.get_orm_model(app_slug).__name__).lower(),
            }
            if _is_ajax_request(request):
                html = render_to_string(self.template_name, context, request=request)
                return JsonResponse({"success": False, "html": html}, status=400)
            return render(request, self.template_name, context)

        should_deploy = should_trigger_deployment_from_form(form, app_id=app_id)

        # Otherwise we can create the instance
        instance_id = create_instance_from_form(form, project, app_slug, app_id)
        detail_url = _build_project_app_path(str(project_slug), f"details/{app_slug}/{instance_id}")
        progress_url = _build_project_app_path(str(project_slug), f"progress/{app_slug}/{instance_id}")
        background_tasks_url = _build_project_app_path(str(project_slug), f"tasks/{app_slug}/{instance_id}")
        status_api_url = _build_project_app_path(str(project_slug), f"tasks/{app_slug}/{instance_id}/status")
        redirect_url = progress_url if should_deploy else detail_url

        if _is_ajax_request(request):
            action = "updated" if app_id else "created"
            return JsonResponse(
                {
                    "success": True,
                    "instance_id": instance_id,
                    "detail_url": detail_url,
                    "progress_url": progress_url,
                    "background_tasks_url": background_tasks_url,
                    "status_api_url": status_api_url,
                    "redirect_url": redirect_url,
                    "action": action,
                }
            )

        return HttpResponseRedirect(redirect_url)

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
            return form_class(request.POST or None, project_pk=project.pk, instance=instance, request=request)
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
        from apps.models import BackgroundTask

        project_obj, instance = _get_project_app_instance(project, app_slug, app_id)

        tasks = _select_latest_task_records(
            list(BackgroundTask.objects.filter(app_instance=instance).order_by("execution_order", "created_at"))
        )
        tasks_data = [_serialize_background_task(task) for task in tasks]
        summary = _build_task_summary(tasks_data)
        workflow = _build_workflow_state(tasks_data)
        deployment = _build_deployment_state(instance, workflow, tasks_data)

        context = {
            "instance": instance,
            "project": project_obj,
            "app_slug": app_slug,
            "summary": summary,
            "workflow": workflow,
            "deployment": deployment,
            "detail_url": _build_project_app_path(str(project_obj.slug), f"details/{app_slug}/{instance.pk}"),
            "form_url": _build_project_app_path(str(project_obj.slug), f"settings/{app_slug}/{instance.pk}"),
            "background_tasks_url": _build_project_app_path(str(project_obj.slug), f"tasks/{app_slug}/{instance.pk}"),
        }

        return render(request, self.template, context)


@method_decorator(
    permission_required_or_403("can_view_project", (Project, "slug", "project")),
    name="dispatch",
)
class AppDetailsView(View):
    template = "apps/details.html"

    def get(self, request, project, app_slug, app_id):
        from apps.models import BackgroundTask

        project_obj, instance = _get_project_app_instance(project, app_slug, app_id)

        tasks = _select_latest_task_records(
            list(BackgroundTask.objects.filter(app_instance=instance).order_by("execution_order", "created_at"))
        )
        recent_tasks = _build_details_task_rows(tasks)
        tasks_data = [_serialize_background_task(task) for task in tasks]
        summary = _build_task_summary(tasks_data)
        workflow = _build_workflow_state(tasks_data)
        deployment = _build_deployment_state(instance, workflow, tasks_data)

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
            "recent_tasks": recent_tasks,
            "summary": summary,
            "workflow": workflow,
            "deployment": deployment,
            "description": description,
            "details_rows": details_rows,
            "tags": tags,
            "public_details_url": reverse("app-metadata", kwargs={"app_id": instance.pk}) if access == "public" else "",
            "background_tasks_url": reverse(
                "apps:background_tasks",
                kwargs={"project": project_obj.slug, "app_slug": app_slug, "app_id": instance.pk},
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
        response = HttpResponse(
            generate_schema_org_compliant_app_metadata(app),
            content_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="SciLifeLab_Serve_App_{app.name}_metadata.json"'},
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
        from apps.models import BackgroundTask

        project_obj, instance = _get_project_app_instance(project, app_slug, app_id)

        # Get all background tasks for this instance
        tasks_qs = BackgroundTask.objects.filter(app_instance=instance).order_by("execution_order", "created_at")
        tasks = _select_latest_task_records(list(tasks_qs))
        summary = _build_task_summary([_serialize_background_task(task) for task in tasks])

        context = {
            "instance": instance,
            "project": project_obj,
            "tasks": tasks,
            "summary": summary,
            "app_slug": app_slug,
            "detail_url": _build_project_app_path(str(project_obj.slug), f"details/{app_slug}/{instance.pk}"),
            "redirect_to_details": request.GET.get("redirect_to") == "details",
        }

        return render(request, self.template, context)


@method_decorator(
    permission_required_or_403("can_view_project", (Project, "slug", "project")),
    name="dispatch",
)
class BackgroundTaskStatusAPI(View):
    """API endpoint to get task status for an app instance."""

    def get(self, request, project, app_slug, app_id):
        from apps.models import BackgroundTask

        try:
            _, instance = _get_project_app_instance(project, app_slug, app_id)
        except (Http404, PermissionDenied):
            return JsonResponse({"error": "App instance not found"}, status=404)

        # Get all background tasks for this instance
        tasks = _select_latest_task_records(
            list(BackgroundTask.objects.filter(app_instance=instance).order_by("execution_order", "created_at"))
        )
        tasks_data = [_serialize_background_task(task) for task in tasks]
        summary = _build_task_summary(tasks_data)

        # Build execution graph data (stage-based DAG from execution_order).
        order_to_task_ids: dict[int, list[int]] = {}
        for task in tasks_data:
            order = task["execution_order"]
            order_to_task_ids.setdefault(order, []).append(task["id"])

        sorted_orders = sorted(order_to_task_ids.keys())
        graph_nodes = [
            {
                "id": f"task-{task['id']}",
                "task_id": task["id"],
                "label": task["task_name"],
                "status": task["status"],
                "execution_order": task["execution_order"],
                "is_critical": task["is_critical"],
                "task_type": task["task_type"],
            }
            for task in tasks_data
        ]
        graph_edges: list[dict[str, str]] = []

        for idx in range(len(sorted_orders) - 1):
            current_order = sorted_orders[idx]
            next_order = sorted_orders[idx + 1]
            for source_id in order_to_task_ids[current_order]:
                for target_id in order_to_task_ids[next_order]:
                    graph_edges.append(
                        {
                            "source": f"task-{source_id}",
                            "target": f"task-{target_id}",
                        }
                    )

        workflow = _build_workflow_state(tasks_data)
        blocked = workflow["blocked"]
        ready_for_deploy = workflow["ready_for_deploy"]
        has_in_progress = workflow["has_in_progress"]
        deployment = _build_deployment_state(instance, workflow, tasks_data)

        if sorted_orders:
            for source_id in order_to_task_ids[sorted_orders[-1]]:
                graph_edges.append(
                    {
                        "source": f"task-{source_id}",
                        "target": "deploy",
                    }
                )

        if blocked:
            deploy_status = "blocked"
        elif ready_for_deploy:
            deploy_status = "ready"
        elif has_in_progress:
            deploy_status = "waiting"
        else:
            deploy_status = "idle"

        graph_nodes.append(
            {
                "id": "deploy",
                "label": "Deploy",
                "status": deploy_status,
                "execution_order": (sorted_orders[-1] + 1) if sorted_orders else 0,
                "is_critical": True,
                "task_type": "deploy",
            }
        )

        return JsonResponse(
            {
                "tasks": tasks_data,
                "summary": summary,
                "graph": {
                    "nodes": graph_nodes,
                    "edges": graph_edges,
                },
                "workflow": workflow,
                "deployment": deployment,
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
