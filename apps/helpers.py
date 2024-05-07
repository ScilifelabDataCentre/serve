import re
import time
import uuid
from datetime import datetime
from enum import Enum
from typing import Optional

from django.apps import apps
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.core import serializers 
from django.db import transaction
from django.template import engines

from projects.models import Flavor
from studio.utils import get_logger

from .models import AppInstance, AppStatus, JupyterInstance, VolumeInstance, Apps, Subdomain
from .tasks import deploy_resource, deploy_resource, delete_resource

logger = get_logger(__name__)

ReleaseName = apps.get_model(app_label=settings.RELEASENAME_MODEL)


def can_access_app_instance(app_instance, user, project):
    """Checks if a user has access to an app instance

    Args:
        app_instance (AppInstance): app instance object
        user (User): user object
        project (Project): project object

    Returns:
        Boolean: returns False if user lack permission to provided app instance
    """
    authorized = False

    if app_instance.access in ("public", "link"):
        authorized = True
    elif app_instance.access == "project":
        if user.has_perm("can_view_project", project):
            authorized = True
    else:
        if user.has_perm("can_access_app", app_instance):
            authorized = True

    return authorized


def can_access_app_instances(app_instances, user, project):
    """Checks if user has access to all app instances provided

    Args:
        app_instances (Queryset<AppInstace>): list of app instances
        user (User): user object
        project (Project): project object

    Returns:
        Boolean: returns False if user lacks
        permission to any of the app instances provided
    """
    for app_instance in app_instances:
        authorized = can_access_app_instance(app_instance, user, project)

        if not authorized:
            return False

    return True


def handle_permissions(parameters, project):
    access = ""

    if parameters["permissions"]["public"]:
        access = "public"
    elif parameters["permissions"]["project"]:
        access = "project"

        if "project" not in parameters:
            parameters["project"] = dict()

        parameters["project"]["client_id"] = project.slug
        parameters["project"]["client_secret"] = project.slug
        parameters["project"]["slug"] = project.slug
        parameters["project"]["name"] = project.name

    elif parameters["permissions"]["private"]:
        access = "private"
    elif parameters["permissions"]["link"]:
        access = "link"

    return access




class HandleUpdateStatusResponseCode(Enum):
    NO_ACTION = 0
    UPDATED_STATUS = 1
    UPDATED_TIME_OF_STATUS = 2
    CREATED_FIRST_STATUS = 3

#TODO: Need to be updated to adhere to new logic
def handle_update_status_request(
    release: str, new_status: str, event_ts: datetime, event_msg: Optional[str] = None
) -> HandleUpdateStatusResponseCode:
    """
    Helper function to handle update app status requests by determining if the
    request should be performed or ignored.

    :param release str: The release id of the app instance, stored in the AppInstance.parameters dict.
    :param new_status str: The new status code. Trimmed to max 15 chars if needed.
    :param event_ts timestamp: A JSON-formatted timestamp in UTC, e.g. 2024-01-25T16:02:50.00Z.
    :param event_msg json dict: An optional json dict containing pod-msg and/or container-msg.
    :returns: A value from the HandleUpdateStatusResponseCode enum.
              Raises an ObjectDoesNotExist exception if the app instance does not exist.
    """

    if len(new_status) > 15:
        new_status = new_status[:15]

    try:
        # Begin by verifying that the requested app instance exists
        # We wrap the select and update tasks in a select_for_update lock
        # to avoid race conditions.

        with transaction.atomic():
            app_instance = (
                AppInstance.objects.select_for_update().filter(parameters__contains={"release": release}).last()
            )
            if app_instance is None:
                logger.info("The specified app instance was not found release=%s.", release)
                raise ObjectDoesNotExist

            logger.debug("The app instance exists. name=%s, state=%s", app_instance.name, app_instance.state)

            # Also get the latest app status object for this app instance
            if app_instance.status is None or app_instance.status.count() == 0:
                # Missing app status so create one now
                logger.info("AppInstance %s does not have an associated AppStatus. Creating one now.", release)
                status_object = AppStatus(appinstance=app_instance)
                update_status(app_instance, status_object, new_status, event_ts, event_msg)
                return HandleUpdateStatusResponseCode.CREATED_FIRST_STATUS
            else:
                app_status = app_instance.status.latest()

            logger.debug("AppStatus %s, %s, %s.", app_status.status_type, app_status.time, app_status.info)

            # Now determine whether to update the state and status

            # Compare timestamps
            time_ftm = "%Y-%m-%d %H:%M:%S"
            if event_ts <= app_status.time:
                msg = "The incoming event-ts is older than the current status ts so nothing to do."
                msg += (
                    f"event_ts={event_ts.strftime(time_ftm)}, app_status.time={str(app_status.time.strftime(time_ftm))}"
                )
                logger.debug(msg)
                return HandleUpdateStatusResponseCode.NO_ACTION

            # The event is newer than the existing persisted object

            if new_status == app_instance.state:
                # The same status. Simply update the time.
                logger.debug("The same status. Simply update the time.")
                update_status_time(app_status, event_ts, event_msg)
                return HandleUpdateStatusResponseCode.UPDATED_TIME_OF_STATUS

            # Different status and newer time
            logger.debug("Different status and newer time.")
            status_object = AppStatus(appinstance=app_instance)
            update_status(app_instance, status_object, new_status, event_ts, event_msg)
            return HandleUpdateStatusResponseCode.UPDATED_STATUS

    except Exception as err:
        logger.error("Unable to fetch or update the specified app instance %s. %s, %s", release, err, type(err))
        raise

#TODO: Need to be updated to adhere to new logic
@transaction.atomic
def update_status(appinstance, status_object, status, status_ts=None, event_msg=None):
    """
    Helper function to update the status of an appinstance and a status object.
    """
    # Persist a new app statuss object
    status_object.status_type = status
    status_object.time = status_ts
    status_object.info = event_msg
    status_object.save()

    # Must re-save the app statuss object with the new event ts
    status_object.time = status_ts

    if event_msg is None:
        status_object.save(update_fields=["time"])
    else:
        status_object.info = event_msg
        status_object.save(update_fields=["time", "info"])

    # Update the app instance object
    appinstance.state = status
    appinstance.save(update_fields=["state"])


@transaction.atomic
def update_status_time(status_object, status_ts, event_msg=None):
    """
    Helper function to update the time of an app status event.
    """
    status_object.time = status_ts

    if event_msg is None:
        status_object.save(update_fields=["time"])
    else:
        status_object.info = event_msg
        status_object.save(update_fields=["time", "info"])

#TODO: Add docstring
@transaction.atomic
def create_instance_from_form(form, project, app_slug, app_id=None):
    subdomain, created = Subdomain.objects.get_or_create(subdomain=form.cleaned_data.get("subdomain"), project=project)
    
    status = AppStatus.objects.create()

    instance = form.save(commit=False)
    
    # If subdomain is changed, we must delete the old helm release
    if app_id and instance.subdomain.subdomain != form.cleaned_data.get("subdomain"):
        serialized_instance = instance.serialize()
        delete_resource.delay(serialized_instance)

    instance.app = Apps.objects.get(slug=app_slug)
    instance.chart = instance.app.chart # Keep history of the chart used, since it can change in App.
    instance.project = project
    instance.owner = project.owner
    instance.subdomain = subdomain
    instance.app_status = status

    instance.save()
    # If your model form uses many-to-many fields, you might need to call save_m2m()
    form.save_m2m()

    instance.set_k8s_values()
    instance.save(update_fields=["k8s_values"])

    serialized_instance = instance.serialize()

    deploy_resource.delay(serialized_instance)