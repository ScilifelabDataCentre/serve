from datetime import datetime
from enum import Enum
from typing import Optional

from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction

from apps.types_.subdomain import SubdomainCandidateName, SubdomainTuple
from studio.utils import get_logger

from .models import Apps, AppStatus, BaseAppInstance, Subdomain

logger = get_logger(__name__)


def get_select_options(project_pk, selected_option=""):
    select_options = []
    for sub in Subdomain.objects.filter(project=project_pk, is_created_by_user=True).values_list(
        "subdomain", flat=True
    ):
        subdomain_candidate = SubdomainCandidateName(sub, project_pk)
        if subdomain_candidate.is_available() or sub == selected_option:
            select_options.append(sub)
    return select_options


def can_access_app_instance(instance, user, project):
    """Checks if a user has access to an app instance

    Args:
        instance (subclass of BaseAppInstance): instance object
        user (User): user object
        project (Project): project object

    Returns:
        Boolean: returns False if user lack permission to provided app instance
    """
    authorized = False

    if instance.access in ("public", "link"):
        authorized = True
    elif instance.access == "project":
        if user.has_perm("can_view_project", project):
            authorized = True
    else:
        if user.has_perm("can_access_app", instance):
            authorized = True

    return authorized


def can_access_app_instances(instances, user, project):
    """Checks if user has access to all app instances provided

    Args:
        instances (Queryset<BaseAppInstance>): list of instances
        user (User): user object
        project (Project): project object

    Returns:
        Boolean: returns False if user lacks
        permission to any of the instances provided
    """
    for instance in instances:
        authorized = can_access_app_instance(instance, user, project)

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


def handle_update_status_request(
    release: str, new_status: str, event_ts: datetime, event_msg: Optional[str] = None
) -> HandleUpdateStatusResponseCode:
    """
    Helper function to handle update app status requests by determining if the
    request should be performed or ignored.

    :param release str: The release id of the app instance, stored in the AppInstance.k8s_values dict in the subdomain.
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

        # release takes on the value of the subdomain
        subdomain = Subdomain.objects.get(subdomain=release)

        with transaction.atomic():
            instance = BaseAppInstance.objects.select_for_update().filter(subdomain=subdomain).last()
            if instance is None:
                logger.info(f"The specified app instance identified by release {release} was not found")
                raise ObjectDoesNotExist

            logger.debug(f"The app instance identified by release {release} exists. App name={instance.name}")

            # Also get the latest app status object for this app instance
            if instance.app_status is None:
                # Missing app status so create one now
                logger.debug(f"AppInstance {release} does not have an associated AppStatus. Creating one now.")
                app_status = AppStatus.objects.create()
                update_status(instance, app_status, new_status, event_ts, event_msg)
                return HandleUpdateStatusResponseCode.CREATED_FIRST_STATUS
            else:
                app_status = instance.app_status

            logger.debug(
                f"AppStatus object was created or updated with status {app_status.status}, ts={app_status.time}, \
                {app_status.info}"
            )

            # Now determine whether to update the state and status

            # Compare timestamps
            time_ftm = "%Y-%m-%d %H:%M:%S"
            if event_ts <= app_status.time:
                msg = "The incoming event-ts is older than the current status ts so nothing to do."
                msg += f"event_ts={event_ts.strftime(time_ftm)} vs \
                    app_status.time={str(app_status.time.strftime(time_ftm))}"
                logger.debug(msg)
                return HandleUpdateStatusResponseCode.NO_ACTION

            # The event is newer than the existing persisted object

            if new_status == instance.app_status.status:
                # The same status. Simply update the time.
                logger.debug(f"The same status {new_status}. Simply update the time.")
                update_status_time(app_status, event_ts, event_msg)
                return HandleUpdateStatusResponseCode.UPDATED_TIME_OF_STATUS

            # Different status and newer time
            logger.debug(
                f"Different status and newer time. New status={new_status} vs Old={instance.app_status.status}"
            )
            status_object = instance.app_status
            update_status(instance, status_object, new_status, event_ts, event_msg)
            return HandleUpdateStatusResponseCode.UPDATED_STATUS

    except Exception as err:
        logger.error(f"Unable to fetch or update the specified app instance with release={release}. {err}, {type(err)}")
        raise


@transaction.atomic
def update_status(appinstance, status_object, status, status_ts=None, event_msg=None):
    """
    Helper function to update the status of an appinstance and a status object.
    """
    # Persist a new app statuss object
    status_object.status = status
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
    appinstance.app_status = status_object
    appinstance.save(update_fields=["app_status"])


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


def get_URI(instance):
    values = instance.k8s_values
    # Subdomain is empty if app is already deleted
    subdomain = values["subdomain"] if "subdomain" in values else ""
    URI = f"https://{subdomain}.{values['global']['domain']}"
    URI = URI.strip("/")
    if hasattr(instance, "default_url_subpath") and instance.default_url_subpath != "":
        URI = URI + "/" + instance.default_url_subpath
        logger.info("Modified URI by adding default url subpath for the custom app: " + URI)
    return URI


@transaction.atomic
def create_instance_from_form(form, project, app_slug, app_id=None):
    """
    Create or update an instance from a form. This function handles both the creation of new instances
    and the updating of existing ones based on the presence of an app_id.

    Parameters:
    - form: The form instance containing validated data.
    - project: The project to which this instance belongs.
    - app_slug: Slug of the app associated with this instance.
    - app_id: Optional ID of an existing instance to update. If None, a new instance is created.

    Returns:
    - The newly created or updated instance.

    Raises:
    - ValueError: If the form does not have a 'subdomain' or if the specified app cannot be found.
    """
    from .tasks import deploy_resource

    new_app = app_id is None

    logger.debug(f"Creating or updating a user app via UI form for app_id={app_id}, new_app={new_app}")

    # Do not deploy resource for edits that do not require a k8s re-deployment
    do_deploy = False

    if new_app:
        do_deploy = True
    else:
        # Only re-deploy existing apps if one of the following fields was changed:
        redeployment_fields = [
            "subdomain",
            "volume",
            "path",
            "flavor",
            "port",
            "image",
            "access",
            "shiny_site_dir",
        ]
        logger.debug(f"An existing app has changed. The changed form fields: {form.changed_data}")

        # Because not all forms contain all fields, we check if the supposedly changed field
        # is actually contained in the form
        for field in form.changed_data:
            if field.lower() in redeployment_fields and (
                field.lower() in form.Meta.fields or field.lower() == "subdomain"
            ):
                # subdomain is a special field not contained in meta fields
                do_deploy = True
                break

    subdomain_name, is_created_by_user = get_subdomain_name(form)

    instance = form.save(commit=False)

    # Handle status creation or retrieval
    status = get_or_create_status(instance, app_id)
    # Retrieve or create the subdomain
    subdomain, created = Subdomain.objects.get_or_create(
        subdomain=subdomain_name, project=project, is_created_by_user=is_created_by_user
    )

    if app_id:
        handle_subdomain_change(instance, subdomain, subdomain_name)

    app_slug = handle_shiny_proxy_case(instance, app_slug, app_id)

    app = get_app(app_slug)

    setup_instance(instance, subdomain, app, project, status)
    save_instance_and_related_data(instance, form)

    if do_deploy:
        logger.debug(f"Now deploying resource app with app_id = {app_id}")
        deploy_resource.delay(instance.serialize())
    else:
        logger.debug(f"Not re-deploying this app with app_id = {app_id}")


def get_subdomain_name(form):
    subdomain_tuple = form.cleaned_data.get("subdomain")
    if not str(subdomain_tuple):
        raise ValueError("Subdomain is required")
    return subdomain_tuple


def get_or_create_status(instance, app_id):
    return instance.app_status if app_id else AppStatus.objects.create()


def handle_subdomain_change(instance, subdomain, subdomain_name):
    from .tasks import delete_resource

    if instance.subdomain.subdomain != subdomain_name:
        # The user modified the subdomain name
        # In this special case, we avoid async task.
        delete_resource(instance.serialize())
        old_subdomain = instance.subdomain
        instance.subdomain = subdomain
        instance.save(update_fields=["subdomain"])
        if old_subdomain and not old_subdomain.is_created_by_user:
            old_subdomain.delete()


def handle_shiny_proxy_case(instance, app_slug, app_id):
    conditions = {("shinyapp", True): "shinyproxyapp", ("shinyproxyapp", False): "shinyapp"}

    proxy_status = getattr(instance, "proxy", False)
    new_slug = conditions.get((app_slug, proxy_status), app_slug)

    return new_slug


def get_app(app_slug):
    try:
        return Apps.objects.get(slug=app_slug)
    except Apps.DoesNotExist:
        logger.error("App with slug %s not found during instance creation", app_slug)
        raise ValueError(f"App with slug {app_slug} not found")


def setup_instance(instance, subdomain, app, project, status, is_created_by_user=False):
    instance.subdomain = subdomain
    instance.app = app
    instance.chart = instance.app.chart
    instance.project = project
    instance.owner = project.owner
    instance.app_status = status


def save_instance_and_related_data(instance, form):
    instance.save()
    form.save_m2m()
    instance.set_k8s_values()
    instance.url = get_URI(instance)
    instance.save(update_fields=["k8s_values", "url"])
