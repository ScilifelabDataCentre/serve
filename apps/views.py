import base64
import json
import subprocess
from datetime import datetime

import dateutil.parser
import requests
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import HttpResponseRedirect, render, reverse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from guardian.decorators import permission_required_or_403

from apps.types_.subdomain import SubdomainCandidateName
from projects.models import Project
from studio.utils import get_logger

from .app_registry import APP_REGISTRY
from .constants import AppActionOrigin
from .helpers import (
    create_instance_from_form,
    generate_schema_org_compliant_app_metadata,
    get_minio_usage,
)
from .models import BaseAppInstance
from .tasks import delete_resource

logger = get_logger(__name__)

User = get_user_model()


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
            return render(
                request,
                self.template_name,
                {"form": form, "project": project, "app_id": app_id, "app_slug": app_slug, "form_header": form_header},
            )

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
            # Updating an existing app instance
            user_can_edit = model_class.objects.user_can_edit(request.user, project, app_slug)
            instance = model_class.objects.get(pk=app_id)
        else:
            # Create a new app instance
            user_can_create = model_class.objects.user_can_create(request.user, project, app_slug)
            instance = None

        if user_can_edit or user_can_create:
            return form_class(request.POST or None, project_pk=project.pk, instance=instance)
            # Maybe this makes typing hard.
        else:
            return None


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


def app_metadata(request, project, app_slug, app_id):
    # Get app model instance
    model_class = APP_REGISTRY.get_orm_model(app_slug)
    if not model_class:
        logger.error(f"Missing model for slug: {app_slug}")
        raise PermissionDenied("Application model not found")

    app = model_class.objects.get(pk=app_id)

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
