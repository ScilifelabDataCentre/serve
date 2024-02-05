import re
import time
import uuid
from datetime import datetime
from enum import Enum
from typing import Optional

from django.apps import apps
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.template import engines

from projects.models import Flavor

from .models import AppInstance, AppStatus
from .serialize import serialize_app
from .tasks import deploy_resource

ReleaseName = apps.get_model(app_label=settings.RELEASENAME_MODEL)


def create_instance_params(instance, action="create"):
    print("HELPER - CREATING INSTANCE PARAMS")
    RELEASE_NAME = "r" + uuid.uuid4().hex[0:8]
    print("RELEASE_NAME: " + RELEASE_NAME)

    SERVICE_NAME = RELEASE_NAME + "-" + instance.app.slug
    # TODO: Fix for multicluster setup, look at e.g. labs
    HOST = settings.DOMAIN
    AUTH_HOST = settings.AUTH_DOMAIN
    AUTH_PROTOCOL = settings.AUTH_PROTOCOL
    NAMESPACE = settings.NAMESPACE

    # Add some generic parameters.
    parameters = {
        "release": RELEASE_NAME,
        "chart": str(instance.app.chart),
        "namespace": NAMESPACE,
        "app_slug": str(instance.app.slug),
        "app_revision": str(instance.app.revision),
        "appname": RELEASE_NAME,
        "global": {
            "domain": HOST,
            "auth_domain": AUTH_HOST,
            "protocol": AUTH_PROTOCOL,
        },
        "s3sync": {"image": "scaleoutsystems/s3-sync:latest"},
        "service": {
            "name": SERVICE_NAME,
            "port": instance.parameters["default_values"]["port"],
            "targetport": instance.parameters["default_values"]["targetport"],
        },
        "storageClass": settings.STORAGECLASS,
    }

    instance.parameters.update(parameters)

    if "project" not in instance.parameters:
        instance.parameters["project"] = dict()

    instance.parameters["project"].update({"name": instance.project.name, "slug": instance.project.slug})


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

    if app_instance.access == "public":
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

    return access


def create_app_instance(user, project, app, app_settings, data=[], wait=False):
    app_name = data.get("app_name")
    app_description = data.get("app_description")
    created_by_admin = False
    # For custom apps, if admin user fills form, then data.get("admin") exists as hidden input
    if data.get("created_by_admin"):
        created_by_admin = True
    parameters_out, app_deps, model_deps = serialize_app(data, project, app_settings, user.username)
    parameters_out["created_by_admin"] = created_by_admin
    authorized = can_access_app_instances(app_deps, user, project)

    if not authorized:
        raise Exception("Not authorized to use specified app dependency")

    access = handle_permissions(parameters_out, project)

    flavor_id = data.get("flavor", None)
    flavor = Flavor.objects.get(pk=flavor_id, project=project) if flavor_id else None

    app_instance = AppInstance(
        name=app_name,
        description=app_description,
        access=access,
        app=app,
        project=project,
        info={},
        parameters=parameters_out,
        owner=user,
        flavor=flavor,
    )

    create_instance_params(app_instance, "create")

    # Attempt to create a ReleaseName model object
    rel_name_obj = []
    if "app_release_name" in data and data.get("app_release_name") != "":
        submitted_rn = data.get("app_release_name")
        try:
            rel_name_obj = ReleaseName.objects.get(name=submitted_rn, project=project, status="active")
            rel_name_obj.status = "in-use"
            rel_name_obj.save()
            app_instance.parameters["release"] = submitted_rn
        except Exception as e:
            print("Error: Submitted release name not owned by project.")
            print(e)
            return [False, None, None]

    # Add fields for apps table:
    # to be displayed as app details in views
    if app_instance.app.table_field and app_instance.app.table_field != "":
        django_engine = engines["django"]
        info_field = django_engine.from_string(app_instance.app.table_field).render(app_instance.parameters)
        app_instance.table_field = eval(info_field)
    else:
        app_instance.table_field = {}

    # Setting status fields before saving app instance
    status = AppStatus(appinstance=app_instance)
    status.status_type = "Created"
    status.info = app_instance.parameters["release"]
    if "appconfig" in app_instance.parameters:
        if "path" in app_instance.parameters["appconfig"]:
            if app_deps:
                if not created_by_admin:
                    app_instance.parameters["appconfig"]["path"] = (
                        "/home/" + app_instance.parameters["appconfig"]["path"]
                    )
        if "userid" not in app_instance.parameters["appconfig"]:
            app_instance.parameters["appconfig"]["userid"] = "1000"
    app_instance.save()
    # Saving ReleaseName, permissions, status and
    # setting up dependencies
    if rel_name_obj:
        rel_name_obj.app = app_instance
        rel_name_obj.save()
    status.save()
    app_instance.app_dependencies.set(app_deps)
    app_instance.model_dependencies.set(model_deps)

    # Finally, attempting to create apps resources
    res = deploy_resource.delay(app_instance.pk, "create")

    # wait is passed as a function parameter
    if wait:
        while not res.ready():
            time.sleep(0.1)

    return [True, project.slug, app_instance.app.category.slug]


class HandleUpdateStatusResponseCode(Enum):
    NO_ACTION = 0
    UPDATED_STATUS = 1
    UPDATED_TIME_OF_STATUS = 2
    CREATED_FIRST_STATUS = 3


def handle_update_status_request(
    release: str, new_status: str, event_ts: datetime, event_msg: Optional[str] = None
) -> HandleUpdateStatusResponseCode:
    """
    Helper function to handle update app status requests by determining if the
    request should be performed or ignored.

    :param release str: The release id of the app instance, stored in the AppInstance.parameters dict.
    :param new_status str: The new status code.
    :param event_ts timestamp: A JSON-formatted timestamp in UTC, e.g. 2024-01-25T16:02:50.00Z.
    :param event_msg json dict: An optional json dict containing pod-msg and/or container-msg.
    :returns: A value from the HandleUpdateStatusResponseCode enum.
              Raises an ObjectDoesNotExist exception if the app instance does not exist.
    """

    try:
        # Begin by verifying that the requested app instance exists
        # We wrap the select and update tasks in a select_for_update lock
        # to avoid race conditions.
        with transaction.atomic():
            app_instance = (
                AppInstance.objects.select_for_update().filter(parameters__contains={"release": release}).last()
            )
            if app_instance is None:
                print(f"The specified app instance was not found {release=}.")
                raise ObjectDoesNotExist

            print(f"DEBUG: The app instance exists. name={app_instance.name}, state={app_instance.state}")

            # Also get the latest app status object for this app instance
            if app_instance.status is None or app_instance.status.count() == 0:
                # Missing app status so create one now
                print(f"AppInstance {release} does not have an associated AppStatus. Creating one now.")
                status_object = AppStatus(appinstance=app_instance)
                update_status(app_instance, status_object, new_status, event_ts, event_msg)
                return HandleUpdateStatusResponseCode.CREATED_FIRST_STATUS
            else:
                app_status = app_instance.status.latest()

            print(f"DEBUG: AppStatus {app_status.status_type=}, {app_status.time=}, {app_status.info=}.")

            # Now determine whether to update the state and status

            # Compare timestamps
            time_ftm = "%Y-%m-%d %H:%M:%S"
            if event_ts <= app_status.time:
                msg = "The incoming event-ts is older than the current status ts so nothing to do."
                msg += (
                    f"event_ts={event_ts.strftime(time_ftm)}, app_status.time={str(app_status.time.strftime(time_ftm))}"
                )
                print(f"DEBUG: {msg}")
                return HandleUpdateStatusResponseCode.NO_ACTION

            # The event is newer than the existing persisted object

            if new_status == app_instance.state:
                # The same status. Simply update the time.
                print("DEBUG: The same status. Simply update the time.")
                update_status_time(app_status, event_ts, event_msg)
                return HandleUpdateStatusResponseCode.UPDATED_TIME_OF_STATUS

            # Different status and newer time
            print("DEBUG: Different status and newer time.")
            status_object = AppStatus(appinstance=app_instance)
            update_status(app_instance, status_object, new_status, event_ts, event_msg)
            return HandleUpdateStatusResponseCode.UPDATED_STATUS

    except Exception as err:
        print(f"Unable to fetch or update the specified app instance {release=}. {err}, {type(err)}")
        raise


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
