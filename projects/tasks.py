import collections
import json
import secrets
import string

from celery import shared_task
from django.apps import apps
from django.conf import settings
from django.contrib.auth import get_user_model

import apps.tasks as apptasks
from apps.controller import delete
from apps.helpers import create_app_instance, create_instance_from_form
from studio.utils import get_logger

from .exceptions import ProjectCreationException
from .models import S3, Environment, Flavor, MLFlow, Project

logger = get_logger(__name__)

Apps = apps.get_model(app_label=settings.APPS_MODEL)
AppInstance = apps.get_model(app_label="apps.AppInstance")

User = get_user_model()


@shared_task
def create_resources_from_template(user, project_slug, template):
    logger.info("Create Resources From Project Template...")
    
    ## THIS IS JUST FOR TESTING PURPOSES
    project = Project.objects.get(slug=project_slug)
    logger.critical("CREATING A VOLUME FROM FORM")
    from apps.forms import VolumeForm
    from apps.models import Subdomain, AppStatus
    from apps.tasks import deploy_resource_new
    from django.core import serializers
    from apps.helpers import SLUG_MODEL_FORM_MAP
    data = {
        "name": "project-vol",
        "size": 5
    }
    form = VolumeForm(data)
    if form.is_valid():
        logger.critical("FORM IS VALID YEEHOOO")
        
        instance = form.save(commit=False)
        
        # THIS COULD ALL BE A FUNCTION I GUESS
        subdomain, created = Subdomain.objects.get_or_create(subdomain=form.cleaned_data.get("subdomain"), project=project)
        status = AppStatus.objects.create()
        
        instance.app = Apps.objects.get(slug="volumeK8s")
        instance.chart = instance.app.chart # Keep history of the chart used, since it can change in App.
        instance.project = project
        
        user_obj = User.objects.get(username=user)
        instance.owner = user_obj
        instance.subdomain = subdomain
        instance.app_status = status
        instance.save()

        form.save_m2m()
        
        instance.set_k8s_values()
        ####
        
        # If your model form uses many-to-many fields, you might need to call save_m2m()
        

        serialized_instance = serializers.serialize("json", [instance])
        
        deploy_resource_new.delay(serialized_instance)
        
        
    else:
        logger.critical("FORM IS INVALID NOOOOOOOOOOOOOOOOOOOOO!!!!!")             
    
    decoder = json.JSONDecoder(object_pairs_hook=collections.OrderedDict)
    parsed_template = template.replace("'", '"')
    template = decoder.decode(parsed_template)
    alphabet = string.ascii_letters + string.digits
    
    
    apps_dict = template.get("apps", {})
    
    # Handle volume
    #TODO: Handle other stuff
    volume_slug = "volumeK8s"
    volumes = apps_dict.get(volume_slug, None)
    if volumes:
        data = {
            "name": "project-vol",
            "size": int(volumes.get("size", 5))
        }
        form = SLUG_MODEL_FORM_MAP[volume_slug]["form"](data)
        create_instance_from_form(form, project, volume_slug)
    
    logger.info("Parsing template...")
    flavor_dict = template.get("flavors", {})
    for flavor_name, resources in flavor_dict.items():
        flavor = Flavor(
            name=flavor_name,
            cpu_req=resources["cpu"]["requirement"],
            cpu_lim=resources["cpu"]["limit"],
            mem_req=resources["mem"]["requirement"],
            mem_lim=resources["mem"]["limit"],
            gpu_req=resources["gpu"]["requirement"],
            gpu_lim=resources["gpu"]["limit"],
            ephmem_req=resources["ephmem"]["requirement"],
            ephmem_lim=resources["ephmem"]["limit"],
            project=project,
        )
        flavor.save()
    
    env_dict = template.get("environments", {})
    for name, settings in env_dict.items():
        try:
            app = Apps.objects.filter(slug=settings["app"]).order_by("-revision")[0]
        except Exception as err:
            logger.error(
                ("App for environment not found. item.app=%s project_slug=%s " "user=%s err=%s"),
                settings["app"],
                project_slug,
                user,
                err,
                exc_info=True,
            )
            raise
        try:
            environment = Environment(
                name=name,
                project=project,
                repository=settings["repository"],
                image=settings["image"],
                app=app,
            )
            environment.save()
        except Exception as err:
            logger.error(
                (
                    "Failed to create new environment: "
                    "key=%s "
                    "project=%s "
                    "item.repository=%s "
                    "image=%s "
                    "app=%s "
                    "user%s "
                    "err=%s"
                ),
                name,
                project,
                settings["repository"],
                settings["image"],
                app,
                user,
                err,
                exc_info=True,
            )
          
    project.status = "active"
    project.save()


@shared_task
def delete_project_apps(project_slug):
    project = Project.objects.get(slug=project_slug)
    apps = AppInstance.objects.filter(project=project)
    for app in apps:
        apptasks.delete_resource.delay(app.pk)


@shared_task
def delete_project(project_pk):
    logger.info("SCHEDULING DELETION OF ALL INSTALLED APPS")
    project = Project.objects.get(pk=project_pk)
    delete_project_apps_permanently(project)

    project.delete()


@shared_task
def delete_project_apps_permanently(project):
    apps = AppInstance.objects.filter(project=project)

    for app in apps:
        helm_output = delete(app.parameters)
        logger.info(helm_output.stderr.decode("utf-8"))
