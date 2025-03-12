from datetime import datetime
from typing import Any, Optional

import regex as re
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db import transaction

from apps.constants import AppActionOrigin, HandleUpdateStatusResponseCode
from apps.types_.subdomain import SubdomainCandidateName
from studio.utils import get_logger

from .models import Apps, BaseAppInstance, K8sUserAppStatus, Subdomain

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


def handle_update_status_request(
    release: str, new_status: str, event_ts: datetime, event_msg: Optional[str] = None
) -> HandleUpdateStatusResponseCode:
    """
    Helper function to handle update k8s user app status requests by determining if the request should be performed or
    ignored.
    Technically this function either updates or creates and persists a new K8sUserAppStatus object.

    :param release str: The release id of the app instance, stored in the AppInstance.k8s_values dict in the subdomain.
    :param new_status str: The new status code. Trimmed to max 20 chars if needed.
    :param event_ts timestamp: A JSON-formatted timestamp in UTC, e.g. 2024-01-25T16:02:50.00Z.
    :param event_msg json dict: An optional json dict containing pod-msg and/or container-msg.
    :returns: A value from the HandleUpdateStatusResponseCode enum.
              Raises an ObjectDoesNotExist exception if the app instance does not exist.
    """

    if len(new_status) > 20:
        new_status = new_status[:20]

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
                # TODO: This should not raise an exception. It is not a problematic event.
                raise ObjectDoesNotExist

            logger.debug(f"The app instance identified by release {release} exists. App name={instance.name}")

            # Also get the latest k8s_user_app_status object for this app instance
            if instance.k8s_user_app_status is None:
                # Missing k8s_user_app_status so create one now
                logger.debug(f"AppInstance {release} does not have an associated K8sUserAppStatus. Creating one now.")
                k8s_user_app_status = K8sUserAppStatus.objects.create()
                update_k8s_user_app_status(instance, k8s_user_app_status, new_status, event_ts, event_msg)
                return HandleUpdateStatusResponseCode.CREATED_FIRST_STATUS
            else:
                k8s_user_app_status = instance.k8s_user_app_status

            logger.debug(
                f"K8sUserAppStatus object was created or updated with status {k8s_user_app_status.status}, \
                    ts={k8s_user_app_status.time}, {k8s_user_app_status.info}"
            )

            # Now determine whether to update the state and status

            # Compare timestamps
            time_ftm = "%Y-%m-%d %H:%M:%S"
            if event_ts <= k8s_user_app_status.time:
                msg = "The incoming event-ts is older than the current status ts so nothing to do."
                msg += f"event_ts={event_ts.strftime(time_ftm)} vs \
                    k8s_user_app_status.time={str(k8s_user_app_status.time.strftime(time_ftm))}"
                logger.debug(msg)
                return HandleUpdateStatusResponseCode.NO_ACTION

            # The event is newer than the existing persisted object

            if new_status == instance.k8s_user_app_status.status:
                # The same status. Simply update the time.
                logger.debug(f"The same status {new_status}. Simply update the time.")
                update_status_time(k8s_user_app_status, event_ts, event_msg)
                return HandleUpdateStatusResponseCode.UPDATED_TIME_OF_STATUS

            # Different status and newer time
            logger.debug(
                f"Different status and newer time. New status={new_status} vs Old={instance.k8s_user_app_status.status}"
            )
            status_object = instance.k8s_user_app_status
            update_k8s_user_app_status(instance, status_object, new_status, event_ts, event_msg)
            return HandleUpdateStatusResponseCode.UPDATED_STATUS

    except Exception as err:
        logger.error(f"Unable to fetch or update the specified app instance with release={release}. {err}, {type(err)}")
        raise


@transaction.atomic
def update_k8s_user_app_status(
    appinstance: BaseAppInstance,
    status_object: K8sUserAppStatus,
    status: str,
    status_ts: datetime = None,
    event_msg: str = None,
):
    """
    Helper function to update the k8s user app status of an appinstance and a status object.
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
    appinstance.k8s_user_app_status = status_object
    appinstance.save(update_fields=["k8s_user_app_status"])


@transaction.atomic
def update_status(appinstance, status_object, status, status_ts=None, event_msg=None):
    """
    Helper function to update the status of an appinstance and a status object.
    """

    raise DeprecationWarning("This function is deprecated. To be removed.")

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
def update_status_time(status_object: Any, status_ts: datetime, event_msg: str | None = None):
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
        logger.info("Modified URI by adding custom default url for the custom app: %s", URI)
    return URI


@transaction.atomic
def create_instance_from_form(form, project, app_slug, app_id=None) -> int:
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

    assert form is not None, "This function requires a form object"
    assert project is not None, "This function requires a project object"

    new_app = app_id is None

    logger.debug(f"Creating or updating a user app via UI form for app_id={app_id}, new_app={new_app}")

    # Do not deploy resource for edits that do not require a k8s re-deployment
    do_deploy = False

    if new_app:
        do_deploy = True
        user_action = "Creating"
    else:
        # Update an existing app
        user_action = "Changing"

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

    # Retrieve or create the subdomain
    subdomain, created = Subdomain.objects.get_or_create(
        subdomain=subdomain_name, project=project, is_created_by_user=is_created_by_user
    )
    assert subdomain is not None
    assert subdomain.subdomain == subdomain_name

    subdomain = Subdomain.objects.get(subdomain=subdomain_name, project=project, is_created_by_user=is_created_by_user)
    assert subdomain is not None
    assert subdomain.subdomain == subdomain_name

    if not new_app:
        handle_subdomain_change(instance, subdomain, subdomain_name)

    app_slug = handle_shiny_proxy_case(instance, app_slug, app_id)

    app = get_app(app_slug)

    setup_instance(instance, subdomain, app, project, user_action)
    instance_id = save_instance_and_related_data(instance, form)

    if do_deploy:
        logger.debug(f"Now deploying resource app with app_id = {app_id}")
        deploy_resource.delay(instance.serialize())
    else:
        logger.debug(f"Not re-deploying this app with app_id = {app_id}")

    return instance_id


def get_subdomain_name(form):
    subdomain_tuple = form.cleaned_data.get("subdomain")
    if not str(subdomain_tuple):
        raise ValueError("Subdomain is required")
    return subdomain_tuple


def get_or_create_status(instance, app_id):
    raise DeprecationWarning("Deprecated function. To be removed.")
    # return instance.app_status if app_id else AppStatus.objects.create()


def handle_subdomain_change(instance: Any, subdomain: str, subdomain_name: str) -> None:
    """
    Detects if there has been a user-initiated subdomain change and if so,
    then re-creates the app instance, also re-deploying the k8s resource.
    """
    from .tasks import delete_resource

    assert instance is not None, "instance is required"

    if instance.subdomain is None:
        # The subdomain is not yet created, nothing to do
        logger.debug("The subdomain is not yet created, nothing to do")
        return

    if instance.subdomain.subdomain != subdomain_name:
        # The user modified the subdomain name
        # In this special case, we avoid async task.
        delete_resource(instance.serialize(), AppActionOrigin.USER.value)
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


def setup_instance(instance, subdomain, app, project, user_action=None, is_created_by_user=False):
    instance.subdomain = subdomain
    instance.app = app
    instance.chart = instance.app.chart
    instance.project = project
    instance.owner = project.owner
    instance.latest_user_action = user_action


def save_instance_and_related_data(instance: Any, form: Any) -> int:
    """
    Saves a new or re-saves an existing app instance to the database.

    Returns:
    - int: The Id of the new or updated app instance.
    """
    instance.save()
    form.save_m2m()
    instance.set_k8s_values()
    instance.url = get_URI(instance)
    # For MLFLOW, we need to set the k8s_values again to update the URL
    instance.set_k8s_values()
    instance.save(update_fields=["k8s_values", "url"])
    return instance.id


def validate_path_k8s_label_compatible(candidate: str) -> None:
    """
    Validates to be compatible with k8s labels specification.
    See: https://kubernetes.io/docs/concepts/overview/working-with-objects/labels/#syntax-and-character-set
    The RegexValidator will raise a ValidationError if the input does not match the regular expression.
    It is up to the caller to handle the raised exception if desired.
    """
    error_message = (
        "Please provide a valid path. "
        "It can be empty. "
        "Otherwise, it must be 63 characters or less. "
        " It must begin and end with an alphanumeric character (a-z, or 0-9, or A-Z)."
        " It could contain dashes ( - ), underscores ( _ ), dots ( . ), "
        "and alphanumerics."
    )

    pattern = r"^(?:[a-zA-Z0-9](?:[a-zA-Z0-9._-]{0,61}[a-zA-Z0-9])?)?$"

    if not re.match(pattern, candidate):
        raise ValidationError(error_message)
