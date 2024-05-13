from datetime import datetime

import requests
from django.apps import apps
from django.conf import settings
from django.contrib.auth import get_user_model

from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import HttpResponseRedirect, render, reverse
from django.utils.decorators import method_decorator
from django.views import View
from guardian.decorators import permission_required_or_403
from studio.utils import get_logger

from django.db import transaction
 
from .tasks import delete_resource
from .constants import SLUG_MODEL_FORM_MAP
from .helpers import create_instance_from_form
from .models import AppInstance, AbstractAppInstance
from .tasks import delete_resource

logger = get_logger(__name__)


Project = apps.get_model(app_label=settings.PROJECTS_MODEL)

User = get_user_model()


def get_status_defs():
    status_success = settings.APPS_STATUS_SUCCESS
    status_warning = settings.APPS_STATUS_WARNING
    return status_success, status_warning

#TODO: This view must be updated to adhere to new logic
@method_decorator(
    permission_required_or_403("can_view_project", (Project, "slug", "project")),
    name="dispatch",
)
class GetLogsView(View):
    def get(self, request, project, ai_id):
        template = "apps/logs.html"
        app = AppInstance.objects.get(pk=ai_id)
        project = Project.objects.get(slug=project)
        return render(request, template, locals())

    def post(self, request, project):
        body = request.POST.get("app", "")
        container = request.POST.get("container", "")
        app = AppInstance.objects.get(pk=body)
        project = Project.objects.get(slug=project)
        app_settings = app.app.settings
        logs = []
        # Looks for logs in app settings. TODO: this logs entry is not used. Remove or change this later.
        if "logs" in app_settings:
            try:
                url = settings.LOKI_SVC + "/loki/api/v1/query_range"
                app_params = app.parameters
                if app.app.slug == "shinyproxyapp":
                    log_query = '{release="' + app_params["release"] + '",container="' + "serve" + '"}'
                else:
                    log_query = '{release="' + app_params["release"] + '",container="' + container + '"}'
                logger.info(log_query)
                query = {
                    "query": log_query,
                    "limit": 500,
                    "since": "24h",
                }
                res = requests.get(url, params=query)
                res_json = res.json()["data"]["result"]
                # TODO: change timestamp logic. Timestamps are different in prod and dev
                for item in res_json:
                    for log_line in reversed(item["values"]):
                        # separate timestamp and log
                        separated_log = log_line[1].split(None, 1)
                        # improve timestamp formatting for table
                        filtered_log = separated_log[0][:-4] if settings.DEBUG else separated_log[0][:-10]
                        formatted_time = datetime.strptime(filtered_log, "%Y-%m-%dT%H:%M:%S.%f")
                        separated_log[0] = datetime.strftime(formatted_time, "%Y-%m-%d, %H:%M:%S")
                        logs.append(separated_log)

            except Exception as e:
                logger.error(str(e), exc_info=True)

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

            for model_class in AbstractAppInstance.__subclasses__():
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

    model_class, _ = SLUG_MODEL_FORM_MAP.get(app_slug, (None, None))
    logger.info(f"Deleting app type {model_class} with id {app_id}")


    instance = model_class.objects.get(pk=app_id) if app_id else None
    
    #TODO: Add check here and redirect if instance is not found
    
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
        project_slug = project # TODO CHANGE THIS IN THE TEMPLATES
        project = Project.objects.get(slug=project_slug)
        
        form = self.get_form(request, project, app_slug, app_id)
        
        return render(request, self.template_name, {"form": form})

    @transaction.atomic
    def post(self, request, project, app_slug, app_id=None):
        # App id is used when updataing an instance

        project_slug = project # TODO CHANGE THIS IN THE TEMPLATES
        project = Project.objects.get(slug=project_slug)
        
        form = self.get_form(request, project, app_slug, app_id)
        if not form.is_valid():
            print(form.errors.as_data(), flush=True)
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

        model_class, form_class = SLUG_MODEL_FORM_MAP.get(app_slug, (None, None))

        #TODO: Add check here
        
        # Check if user is allowed
        user_can_create = model_class.objects.user_can_create(request.user, project, app_slug)
        
        if user_can_create:
            instance = model_class.objects.get(pk=app_id) if app_id else None
            
            return form_class(request.POST or None, project_pk=project.pk, instance=instance)
            # Maybe this makes typing hard.
        else:
            return HttpResponseForbidden()


