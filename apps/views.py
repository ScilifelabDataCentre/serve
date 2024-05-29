from datetime import datetime

import requests
from django.apps import apps
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import HttpResponseRedirect, render, reverse
from django.utils.decorators import method_decorator
from django.views import View
from guardian.decorators import permission_required_or_403

from projects.models import Project
from studio.utils import get_logger

from .constants import APP_REGISTRY
from .helpers import create_instance_from_form
from .models import BaseAppInstance
from .tasks import delete_resource

logger = get_logger(__name__)

User = get_user_model()


def get_status_defs():
    status_success = settings.APPS_STATUS_SUCCESS
    status_warning = settings.APPS_STATUS_WARNING
    return status_success, status_warning


# TODO: This view must be updated to adhere to new logic
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

        # container name is often same as subdomain name
        container = instance.subdomain.subdomain

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
            status_success, status_warning = get_status_defs()

            for model_class in BaseAppInstance.__subclasses__():
                instances = model_class.objects.filter(pk__in=arr)

                for instance in instances:
                    status_object = instance.app_status
                    if status_object:
                        status = status_object.status
                    else:
                        status = None

                    status_group = (
                        "success" if status in status_success else "warning" if status in status_warning else "danger"
                    )

                    obj = {
                        "status": status,
                        "statusGroup": status_group,
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

    delete_resource.delay(serialized_instance)
    # fix: in case appinstance is public swich to private
    instance.access = "private"
    instance.save()

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
        project_slug = project  # TODO CHANGE THIS IN THE TEMPLATES
        project = Project.objects.get(slug=project_slug)

        form = self.get_form(request, project, app_slug, app_id)

        if form is None or not getattr(form, "is_valid", False):
            raise PermissionDenied()

        return render(
            request, self.template_name, {"form": form, "project": project, "app_id": app_id, "app_slug": app_slug}
        )

    @transaction.atomic
    def post(self, request, project, app_slug, app_id=None):
        # App id is used when updataing an instance

        project_slug = project  # TODO CHANGE THIS IN THE TEMPLATES
        project = Project.objects.get(slug=project_slug)

        form = self.get_form(request, project, app_slug, app_id)
        if form is None:
            raise PermissionDenied()

        if not form.is_valid():
            return render(request, self.template_name, {"form": form})

        # Otherwise we can create the instance
        create_instance_from_form(form, project, app_slug, app_id)

        return HttpResponseRedirect(
            reverse(
                "projects:details",
                kwargs={
                    "project_slug": str(project_slug),
                },
            )
        )

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
            user_can_edit = model_class.objects.user_can_edit(request.user, project, app_slug)
            instance = model_class.objects.get(pk=app_id)
        else:
            user_can_create = model_class.objects.user_can_create(request.user, project, app_slug)
            instance = None

        if user_can_edit or user_can_create:
            return form_class(request.POST or None, project_pk=project.pk, instance=instance)
            # Maybe this makes typing hard.
        else:
            return None
