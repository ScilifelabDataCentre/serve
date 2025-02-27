import collections
import json

from celery import shared_task
from django.apps import apps
from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.app_registry import APP_REGISTRY
from apps.helpers import create_instance_from_form
from apps.models import BaseAppInstance, VolumeInstance
from apps.tasks import delete_resource
from studio.utils import get_logger

from .exceptions import ProjectCreationException
from .models import Environment, Flavor, Project

logger = get_logger(__name__)

Apps = apps.get_model(app_label=settings.APPS_MODEL)

User = get_user_model()


@shared_task
def create_resources_from_template(user, project_slug, template):
    logger.info("Create Resources From Project Template...")

    project = Project.objects.get(slug=project_slug)

    decoder = json.JSONDecoder(object_pairs_hook=collections.OrderedDict)
    parsed_template = template.replace("'", '"')
    template = decoder.decode(parsed_template)

    logger.info("Creating Project Flavors...")
    flavor_dict = template.get("flavors", {})
    for flavor_name, resources in flavor_dict.items():
        logger.info("Creating flavor ")
        logger.info(f"Creating flavor: {flavor_name}")
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

    logger.info("Creating Project Volumes...")
    volume_dict = template.get("volumes", {})
    for volume_name, data in volume_dict.items():
        data["name"] = volume_name
        logger.info(f"Creating volume using {data}")
        form_class = APP_REGISTRY.get_form_class("volumeK8s")
        form = form_class(data, project_pk=project.pk)
        if form.is_valid():
            create_instance_from_form(form, project, "volumeK8s")
        else:
            logger.error(f"Form is invalid: {form.errors.as_data()}")
            raise ProjectCreationException(f"Form is invalid: {form.errors.as_data()}")

    apps_dict = template.get("apps", {})
    logger.info("Initiate Creation of Project Apps...")
    form_dict = {}
    for app_slug, data in apps_dict.items():
        logger.info(f"Creating {app_slug} using raw data {data}")

        # Handle mounting of volumes
        if "volume" in data:
            try:
                volumes = VolumeInstance.objects.filter(project=project, name=data["volume"])
                data["volume"] = volumes
                logger.info(f"Modified data with specified volume: {data}")
            except VolumeInstance.DoesNotExist:
                raise ProjectCreationException(f"Volume {data['volume']} not found")

        # Handle flavor selection
        if "flavor" in data:
            try:
                # Get the only flavor that matches the project and the name
                flavor = Flavor.objects.filter(project__pk=project.pk, name=data["flavor"]).first()
                data["flavor"] = flavor
                logger.info(f"Modified data with specified flavor: {data}")
            except Flavor.DoesNotExist:
                raise ProjectCreationException(f"Flavor {data['flavor']} not found")

        model_form_tuple = APP_REGISTRY.get(app_slug)

        # Check if the model form tuple exists
        if not model_form_tuple:
            logger.error(f"App {app_slug} not found")
            raise ProjectCreationException(f"App {app_slug} not found")

        # Create form
        form = model_form_tuple.Form(data, project_pk=project.pk)

        # Handle validation
        if form.is_valid():
            logger.info("Form is valid - Appending form to list")
            form_dict[app_slug] = form
        else:
            logger.error(f"Form is invalid: {form.errors.as_data()}")
            raise ProjectCreationException(f"Form is invalid: {form.errors.as_data()}")

    # All forms are valid, lets create apps.
    logger.info("All forms valid, creating apps...")
    for app_slug, form in form_dict.items():
        create_instance_from_form(form, project, app_slug)

    env_dict = template.get("environments", {})
    logger.info("Creating Project Environments...")
    for name, env_settings in env_dict.items():
        try:
            app = Apps.objects.filter(slug=env_settings["app"]).order_by("-revision")[0]
        except Exception as err:
            logger.error(
                ("App for environment not found. item.app=%s project_slug=%s " "user=%s err=%s"),
                env_settings["app"],
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
                repository=env_settings["repository"],
                image=env_settings["image"],
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
def delete_project(project_pk):
    logger.info("SCHEDULING DELETION OF ALL INSTALLED APPS")
    project = Project.objects.get(pk=project_pk)
    delete_project_apps(project)

    project.status = "deleted"
    project.deleted_on = timezone.now()
    project.save()


@shared_task
def delete_project_apps(project):
    for orm_model in APP_REGISTRY.iter_orm_models():
        queryset = orm_model.objects.filter(project=project)
        for instance in queryset:
            serialized_instance = instance.serialize()
            instance.latest_user_action = "Deleting"
            instance.save(update_fields=["latest_user_action"])
            delete_resource(serialized_instance)


@shared_task
def clean_up_projects_in_database():
    """
    This task retrieves projects that have been deleted (i.e. got status 'deleted') over a specified
    amount of days ago and removes them from the database.
    TODO: Make projects_clean_up_threshold_days a variable in settings.py.
    """

    projects_clean_up_threshold_days = 425
    logger.info(
        f"Running task clean_up_projects_in_database to remove all projects that have been \
                 deleted more than {projects_clean_up_threshold_days} days ago."
    )

    projects_to_be_cleaned_up = Project.objects.filter(
        deleted_on__lt=timezone.now() - timezone.timedelta(days=projects_clean_up_threshold_days), status="deleted"
    )

    if projects_to_be_cleaned_up:
        logger.info(f"Removing {len(projects_to_be_cleaned_up)} project(s) from the database.")
        for project in projects_to_be_cleaned_up:
            project.delete()
    else:
        logger.info("There were no projects to be cleaned up.")
