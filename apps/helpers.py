import json
import traceback
from collections.abc import Iterable
from datetime import datetime
from typing import Any, Dict, Optional, Type

import regex as re
import requests
import waffle
import yaml
from django.conf import settings
from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.exceptions import ObjectDoesNotExist, PermissionDenied, ValidationError
from django.db import transaction
from django.db.models.query import QuerySet
from django.forms.models import model_to_dict
from django.utils import timezone
from prometheus_client.parser import text_string_to_metric_families
from requests.exceptions import ConnectionError, Timeout

from apps.constants import AppActionOrigin, HandleUpdateStatusResponseCode
from apps.types_.subdomain import SubdomainCandidateName
from apps.validators.container_images import (
    DockerHubAuthenticator,
    GHCRAuthenticator,
    get_image_architectures,
)
from common.models import UserProfile
from projects.models import Project
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
    release: str, new_status: str, event_ts: datetime, event_msg: str | None = None
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
                return HandleUpdateStatusResponseCode.OBJECT_NOT_FOUND

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

    except ObjectDoesNotExist:
        logger.info(f"No such subdomain exists identified by release={release}")
        return HandleUpdateStatusResponseCode.OBJECT_NOT_FOUND

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
def create_instance_from_form(form, project, app_slug, app_id=None, force_redeploy: bool = False) -> int:
    """
    Create or update an instance from a form. This function handles both the creation of new instances
    and the updating of existing ones based on the presence of an app_id.

    Parameters:
    - form: The form instance containing validated data.
    - project: The project to which this instance belongs.
    - app_slug: Slug of the app associated with this instance.
    - app_id: Optional ID of an existing instance to update. If None, a new instance is created.
    - force_redeploy: Forces a re-deploy even if no tracked fields changed. Useful for actions that
      mutate underlying infrastructure without altering standard form fields.

    Returns:
    - The newly created or updated instance.

    Raises:
    - ValueError: If the form does not have a 'subdomain' or if the specified app cannot be found.
    """
    from .tasks import deploy_resource

    assert form is not None, "This function requires a form object"
    assert project is not None, "This function requires a project object"

    new_app = app_id is None
    requested_app_slug = app_slug

    logger.info(
        "create_instance_from_form.start app_id=%s new_app=%s app_slug=%s project_id=%s",
        app_id,
        new_app,
        app_slug,
        project.pk,
    )

    if new_app:
        do_deploy = True
        user_action = "Creating"
    else:
        do_deploy = force_redeploy
        # Update an existing app
        user_action = "Changing"

        if not do_deploy:
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
    logger.info(
        "create_instance_from_form.subdomain_selected app_id=%s subdomain=%s is_created_by_user=%s",
        app_id,
        subdomain_name,
        is_created_by_user,
    )

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
    logger.info(
        "create_instance_from_form.subdomain_ready app_id=%s subdomain=%s created=%s",
        app_id,
        subdomain_name,
        created,
    )

    if not new_app:
        handle_subdomain_change(instance, subdomain, subdomain_name)

    app_slug = handle_shiny_proxy_case(instance, app_slug, app_id)
    logger.info(
        "create_instance_from_form.app_slug_resolved app_id=%s requested_slug=%s resolved_slug=%s",
        app_id,
        requested_app_slug,
        app_slug,
    )

    app = get_app(app_slug)

    # set the reminder date if this is a link-only app
    if hasattr(instance, "access") and instance.access == "link":
        if instance.reminder_date_linkonly_privacy is None:
            set_linkonly_reminder_date(instance)
    else:
        instance.reminder_date_linkonly_privacy = None

    setup_instance(instance, subdomain, app, project, user_action)
    instance_id = save_instance_and_related_data(instance, form)
    logger.info(
        "create_instance_from_form.instance_saved app_id=%s instance_id=%s user_action=%s do_deploy=%s",
        app_id,
        instance_id,
        user_action,
        do_deploy,
    )

    if do_deploy:
        serialized_instance = instance.serialize()
        logger.info(
            "create_instance_from_form.enqueue_on_commit app_id=%s instance_id=%s model=%s pk=%s",
            app_id,
            instance_id,
            serialized_instance.get("model"),
            serialized_instance.get("pk"),
        )

        def enqueue_deploy_task():
            logger.info(
                "create_instance_from_form.enqueue_dispatch app_id=%s instance_id=%s model=%s pk=%s",
                app_id,
                instance_id,
                serialized_instance.get("model"),
                serialized_instance.get("pk"),
            )
            deploy_resource.delay(serialized_instance)

        transaction.on_commit(enqueue_deploy_task)
    else:
        logger.info("create_instance_from_form.deploy_skipped app_id=%s instance_id=%s", app_id, instance_id)

    if waffle.switch_is_active("doi_minting_using_invenio"):
        image_value_changed = False
        app_contains_image = False
        for field in form.cleaned_data:
            if field.lower() == "image":
                app_contains_image = True
                break
        for field in form.changed_data:
            if field.lower() == "image":
                image_value_changed = True
                break
        # Collect additional metadata from form
        additional_metadata = {}
        lang = form.cleaned_data.get("language")
        if lang:
            additional_metadata["languages"] = lang
        # Check for changes
        if image_value_changed:
            logger.info(
                f"App '{app_slug}' with app id '{app_id}', Image value changed in form," "checking to minting DOI.."
            )
            continuation_message = "Continuing with app deployment despite DOI minting failure"
            try:
                # Wrap the DOI minting call in try-except to handle potential failures
                save_metadata_to_invenio_then_mint_doi(app_slug, instance_id, additional_metadata=additional_metadata)

            except ValueError as e:
                logger.error(
                    f"Failed to mint DOI for app '{app_slug}' (ID: {instance_id}): " f"Validation error - {str(e)}"
                )
                # Don't raise the error - app creation should continue even if DOI minting fails
                logger.debug(continuation_message)

            except PermissionDenied as e:
                logger.error(
                    f"Failed to mint DOI for app '{app_slug}' (ID: {instance_id}): " f"Permission denied - {str(e)}"
                )
                logger.debug(continuation_message)

            except requests.RequestException as e:
                logger.error(
                    f"Failed to mint DOI for app '{app_slug}' (ID: {instance_id}): "
                    f"Network error connecting to external service - {str(e)}"
                )
                logger.debug(continuation_message)

            except ConnectionError as e:
                logger.error(
                    f"Failed to mint DOI for app '{app_slug}' (ID: {instance_id}): "
                    f"Connection error to external service - {str(e)}"
                )
                logger.debug(continuation_message)

            except Timeout as e:
                logger.error(
                    f"Failed to mint DOI for app '{app_slug}' (ID: {instance_id}): "
                    f"Timeout connecting to external service - {str(e)}"
                )
                logger.debug(continuation_message)

            except Exception as e:
                logger.error(
                    f"Failed to mint DOI for app '{app_slug}' (ID: {instance_id}): " f"Unexpected error - {str(e)}"
                )
                logger.error(f"Traceback for DOI minting failure: {traceback.format_exc()}")
                logger.debug(continuation_message)

        elif app_contains_image:
            logger.debug(f"App '{app_slug}' with app id '{app_id}', Image value did not change no need to mint DOI...")
        else:
            logger.debug(f"App '{app_slug}' with app id '{app_id}' does not have image, no need to mint DOI...")
    else:
        logger.debug(
            "Make sure to turn the 'doi_minting_using_invenio' waffle switch on"
            f" if you want to mint the DOI of App '{app_slug}' with app id '{app_id}'.",
        )

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
    logger.info(
        "handle_subdomain_change.start instance_id=%s current_subdomain=%s requested_subdomain=%s",
        instance.pk,
        instance.subdomain.subdomain if instance.subdomain else None,
        subdomain_name,
    )

    if instance.subdomain is None:
        # The subdomain is not yet created, nothing to do
        logger.info("handle_subdomain_change.skip_no_existing_subdomain instance_id=%s", instance.pk)
        return

    if instance.subdomain.subdomain != subdomain_name:
        # The user modified the subdomain name
        # In this special case, we avoid async task.
        delete_resource(instance.serialize(), AppActionOrigin.USER.value)
        old_subdomain = instance.subdomain
        instance.subdomain = subdomain
        instance.save(update_fields=["subdomain"])
        logger.info(
            "handle_subdomain_change.updated instance_id=%s old_subdomain=%s new_subdomain=%s",
            instance.pk,
            old_subdomain.subdomain if old_subdomain else None,
            subdomain_name,
        )
        if old_subdomain and not old_subdomain.is_created_by_user:
            old_subdomain.delete()
            logger.info(
                "handle_subdomain_change.deleted_old_subdomain instance_id=%s old_subdomain=%s",
                instance.pk,
                old_subdomain.subdomain,
            )
    else:
        logger.info("handle_subdomain_change.no_change instance_id=%s subdomain=%s", instance.pk, subdomain_name)


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
    logger.info(
        "setup_instance.assigned instance_id=%s subdomain=%s app_slug=%s project_id=%s user_action=%s",
        instance.pk,
        subdomain.subdomain if subdomain else None,
        app.slug if app else None,
        project.pk if project else None,
        user_action,
    )


def save_instance_and_related_data(instance: Any, form: Any) -> int:
    """
    Saves a new or re-saves an existing app instance to the database.

    Returns:
    - int: The Id of the new or updated app instance.
    """
    logger.info("save_instance_and_related_data.start instance_id=%s", instance.pk)
    instance.save()
    form.save_m2m()
    instance.set_k8s_values()
    instance.url = get_URI(instance)
    # For MLFLOW, we need to set the k8s_values again to update the URL
    instance.set_k8s_values()
    instance.save(update_fields=["k8s_values", "url"])
    logger.info("save_instance_and_related_data.finish instance_id=%s url=%s", instance.id, instance.url)
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


def check_ghcr_owner_type(owner: str):
    """Determines whether a GHCR owner is a User or an Organization."""

    gh_owner_url = f"{settings.GITHUB_API}/users/{owner}"
    headers = {"Accept": "application/vnd.github+json"}

    try:
        response = requests.get(gh_owner_url, headers=headers)
        response.raise_for_status()
        data = response.json()

        owner_type = data.get("type")
        if owner_type in {"User", "Organization"}:
            return owner_type

        raise ValidationError("Invalid response structure from GitHub API for Owner type.")

    except requests.RequestException as e:
        raise ValidationError(f"Failed to fetch GHCR owner type: {e}")


def validate_ghcr_image(image: str):
    """Validates whether a given GHCR image exists."""

    # regex match:
    # ghcr\.io/ - ghcr.io
    # (?P) used to capture a named group eg. owner, image and tag
    # [\w-]+ allow more than 1 character of letters, numbers underscores and hyphens
    match = re.match(r"ghcr\.io/(?P<owner>[\w-]+)/(?P<image>[\w-]+):(?P<tag>[\w.-]+)", image)

    if not match:
        raise ValidationError("Invalid image URL format. Please try again.")

    owner, image_name, tag = match.group("owner"), match.group("image"), match.group("tag")

    owner_type = check_ghcr_owner_type(owner)
    if owner_type == "Organization":
        image_url = f"https://api.github.com/orgs/{owner}/packages/container/{image_name}/versions"
    elif owner_type == "User":
        image_url = f"https://api.github.com/users/{owner}/packages/container/{image_name}/versions"
    else:
        raise ValidationError("Could not recognise the GHCR owner. Please try again.")

    # Return the image if the GitHub API token is missing
    if settings.GITHUB_API_TOKEN in ["", None]:
        return image

    headers = {"Authorization": f"Bearer {settings.GITHUB_API_TOKEN}", "Accept": "application/vnd.github+json"}

    try:
        response = requests.get(image_url, headers=headers)
        response.raise_for_status()
    except requests.RequestException as e:
        raise ValidationError(f"The specified GHCR image was not found.: {e}")

    try:
        versions = response.json()
        for version in versions:
            container_metadata = version["metadata"]["container"]
            tags = container_metadata.get("tags", [])
            if tag in tags:
                break
        else:
            raise ValidationError(f"Tag '{tag}' not found in GHCR image. Please try again.")

    except KeyError:
        raise ValidationError("Unable to find GHCR image tag. Please try again.")

    if waffle.switch_is_active("docker_image_architecture_validator"):
        architectures = get_image_architectures(
            auth=GHCRAuthenticator(
                username=settings.GITHUB_API_USERNAME,
                token=settings.GITHUB_API_TOKEN,
            ),
            repo=f"{owner}/{image_name}",
            reference=tag,
            registry="ghcr.io",
        )
        if any(arch.arch != "amd64" for arch in architectures):
            raise ValidationError(
                f"Docker image '{image}' is not built for the right CPU architecture. "
                "Please use docker build --platform linux/amd64 to build your image"
            )

    return image


def validate_docker_image(image: str):
    """Validates whether a given Docker image exists on Docker Hub."""

    if ":" in image:
        repository, tag = image.rsplit(":", 1)
    else:
        repository, tag = image, "latest"

    repository = repository.replace("docker.io/", "", 1)

    # Ensure repository is in the correct format
    if "/" not in repository:
        repository = f"library/{repository}"

    docker_api_url = f"{settings.DOCKER_HUB_TAG_SEARCH}/{repository}/tags/{tag}"

    try:
        response = requests.get(docker_api_url, timeout=5)
        response.raise_for_status()
    except requests.RequestException:
        raise ValidationError(
            f"Docker image '{image}' is not publicly available on Docker Hub. "
            "The URL you have entered may be incorrect, or the image might be private."
        )

    if waffle.switch_is_active("docker_image_architecture_validator"):
        architectures = get_image_architectures(
            auth=DockerHubAuthenticator(username=settings.DOCKER_HUB_USERNAME, token=settings.DOCKER_HUB_TOKEN),
            repo=repository,
            reference=tag,
        )
        if any(arch.arch != "amd64" for arch in architectures):
            raise ValidationError(
                f"Docker image '{image}' is not built for the right CPU architecture. "
                "Please use docker build --platform linux/amd64 to build your image"
            )


def generate_schema_org_compliant_app_metadata(app_instance: BaseAppInstance) -> str:
    """Generate schema.org structured data for App, User, and Project models."""

    # Safely get related objects
    try:
        user_instance = User.objects.get(id=app_instance.owner_id)
    except User.DoesNotExist as error:
        raise ValueError(f"User with id {app_instance.owner_id} does not exist") from error

    try:
        project_instance = Project.objects.get(id=app_instance.project_id)
    except Project.DoesNotExist:
        raise ValueError(f"Project with id {app_instance.project_id} does not exist")

    # Convert models to dictionaries with safe defaults
    app_data = model_to_dict(app_instance, exclude=["_state"])
    user_data = model_to_dict(user_instance, exclude=["_state", "password"])
    project_data = model_to_dict(project_instance, exclude=["_state"])

    if user_profile := UserProfile.objects.filter(user=user_instance).first():
        user_data.update(
            {
                "department": user_profile.department,
                "affiliation": user_profile.get_organization_name(),
            }
        )

    # Safely add special fields
    app_data.update(
        {"k8s_values": app_instance.k8s_values or {}, "info": app_instance.info or {}, "url": app_instance.url or {}}
    )

    # Build software requirements as PropertyValue list
    additional_property = []

    # some app types does not have app image
    try:
        app_image = app_instance.image
    except AttributeError:
        app_image = ""

    app_values = {
        "appImage": app_image,
        "appCreated": app_instance.created_on.isoformat(),
        "appUpdated": app_instance.updated_on.isoformat(),
    }
    for value_name in app_values.keys():
        additional_property.append({"@type": "PropertyValue", "name": value_name, "value": app_values[value_name]})

    if app_data["k8s_values"]:
        requests = app_data["k8s_values"].get("flavor", {}).get("requests", {})
        limits = app_data["k8s_values"].get("flavor", {}).get("limits", {})

        resource_mapping = [
            ("cpu", "cpu"),
            ("gpu", "nvidia.com/gpu"),
            ("memory", "memory"),
            ("storage", "ephemeral-storage"),
        ]

        for field_name, k8s_name in resource_mapping:
            if requests.get(k8s_name):
                additional_property.append(
                    {"@type": "PropertyValue", "name": f"{field_name}Request", "value": requests[k8s_name]}
                )
            if limits.get(k8s_name):
                additional_property.append(
                    {"@type": "PropertyValue", "name": f"{field_name}Limit", "value": limits[k8s_name]}
                )

    # Build project resource usage properties
    project_properties = []
    project_properties.append(
        {"@type": "PropertyValue", "name": "dateCreated", "value": project_instance.created_at.isoformat()}
    )
    if project_data.get("apps_per_project"):
        for app_name, count in project_data["apps_per_project"].items():
            project_properties.append({"@type": "PropertyValue", "name": app_name, "value": str(count)})

    # Construct new schema structure
    schema = {
        "@context": "https://schema.org",
        "@type": "Dataset",
        "name": "Application Deployment Metadata",
        "description": (
            "Structured metadata for applications, users, and projects deployed on "
            "the SciLifeLab Serve platform (https://serve.scilifelab.se/)."
        ),
        "dateCreated": timezone.now().isoformat(),
        "creator": {"@type": "Organization", "name": "SciLifeLab Data Centre", "url": "https://www.scilifelab.se/data"},
        "hasPart": [
            {
                "@type": "SoftwareApplication",
                "name": app_data.get("name"),
                "description": app_data.get("description"),
                "url": app_data.get("url"),
                "softwareVersion": app_data.get("chart"),
                "author": {
                    "@type": "Person",
                    "name": f"{user_data.get('first_name', '')} {user_data.get('last_name', '')}",
                    "email": user_data.get("email"),
                    "affiliation": {
                        "@type": "Organization",
                        "name": user_data.get("affiliation"),
                        "additionalProperty": {
                            "@type": "PropertyValue",
                            "name": "department",
                            "value": user_data.get("department"),
                        },
                    },
                },
                "applicationCategory": "Cloud Application",
                "operatingSystem": "Kubernetes",
                "additionalProperty": additional_property,
                "hasPart": {"@type": "SoftwareSourceCode", "codeRepository": app_data.get("source_code_url")},
            }
        ],
        "about": {
            "@type": "Project",
            "name": project_data.get("name"),
            "description": project_data.get("description"),
            "additionalProperty": project_properties,
            "funder": {
                "@type": "Person",
                "name": f"{user_data.get('first_name', '')} {user_data.get('last_name', '')}",
                "email": user_data.get("email"),
            },
            "parentOrganization": {
                "@type": "Organization",
                "name": user_data.get("affiliation"),
                "additionalProperty": {
                    "@type": "PropertyValue",
                    "name": "department",
                    "value": user_data.get("department"),
                },
            },
        },
    }

    # Clean null values function
    def clean_nulls(obj):
        if isinstance(obj, dict):
            return {k: clean_nulls(v) for k, v in obj.items() if v is not None}
        elif isinstance(obj, list):
            return [clean_nulls(elem) for elem in obj if elem is not None]
        return obj

    schema_json = json.dumps(clean_nulls(schema), indent=2)

    logger.info(f"Generated schema.org description of app '{app_data.get('name')}' as follows:\n{schema_json}")

    return schema_json


def get_university_suffix_information(university_sufffix: str) -> str:
    """Provide University name from official suffix, ex. uu -> Uppsala universitet (Uppsala University)"""
    # University mapping with consistent formatting
    UNIVERSITY_NAMES = {
        "bth": "Blekinge Tekniska Högskola (Blekinge Institute of Technology)",
        "chalmers": "Chalmers tekniska högskola (Chalmers University of Technology)",
        "du": "Högskolan Dalarna (Dalarna University)",
        "fhs": "Försvarshögskolan (Swedish Defence University)",
        "gih": "Gymnastik- och idrottshögskolan (Swedish School of Sport and Health Sciences)",
        "gu": "Göteborgs universitet (University of Gothenburg)",
        "hb": "Högskolan i Borås (University of Borås)",
        "hh": "Högskolan i Halmstad (Halmstad University)",
        "hhs": "Handelshögskolan i Stockholm (Stockholm School of Economics)",
        "hig": "Högskolan i Gävle (University of Gävle)",
        "his": "Högskolan i Skövde (University of Skövde)",
        "hkr": "Högskolan Kristianstad (Kristianstad University)",
        "hv": "Högskolan Väst (University West)",
        "ju": "Högskolan i Jönköping (Jönköping University)",
        "kau": "Karlstads universitet (Karlstad University)",
        "ki": "Karolinska Institutet (Karolinska Institute)",
        "kth": "Kungliga Tekniska Högskolan (Royal Institute of Technology)",
        "liu": "Linköpings universitet (Linköping University)",
        "lnu": "Linnéuniversitetet (Linnaeus University)",
        "ltu": "Luleå tekniska universitet (Luleå University of Technology)",
        "lu": "Lunds universitet (Lund University)",
        "lth": "Lunds tekniska högskola (Faculty of Engineering, Lund University)",
        "mau": "Malmö universitet (Malmö University)",
        "mdu": "Mälardalens universitet (Mälardalen University)",
        "miun": "Mittuniversitetet (Mid Sweden University)",
        "oru": "Örebro universitet (Örebro University)",
        "sh": "Södertörns högskola (Södertörn University)",
        "slu": "Sveriges lantbruksuniversitet (Swedish University of Agricultural Sciences)",
        "su": "Stockholms universitet (Stockholm University)",
        "umu": "Umeå universitet (Umeå University)",
        "uu": "Uppsala universitet (Uppsala University)",
    }

    return UNIVERSITY_NAMES.get(university_sufffix, university_sufffix)


def get_minio_usage(minio_service_name: str) -> None | tuple[float, float]:
    metrics_url = f"http://{minio_service_name}/minio/v2/metrics/cluster"

    try:
        response = requests.get(metrics_url, timeout=5)
        response.raise_for_status()
        raw_metrics = response.text

    except requests.RequestException as e:
        logger.error(f"MinIO metrics url get request failed for {metrics_url}: {e}")
        return None
    except Exception as e:
        logger.error(f"MinIO metrics fetch failed for {metrics_url}: {e}")
        return None

    # Helper to extract metric values
    def get_metric_value(metric_name: str) -> float:
        total = 0.0
        for family in text_string_to_metric_families(raw_metrics):
            if family.name == metric_name:
                total += sum(float(sample.value) for sample in family.samples)
        return total

    GIB_FACTOR = 1024**3  # 1 GiB in bytes

    try:
        used_bytes = get_metric_value("minio_cluster_usage_total_bytes")
        total_bytes = get_metric_value("minio_cluster_capacity_usable_total_bytes")
    except ValueError as e:
        logger.error(f"MinIO metrics value parsing failed: {e}")
        return None
    except Exception as e:
        logger.error(f"MinIO metrics parsing failed: {e}")
        return None

    # Convert to GiB and round
    return (round(used_bytes / GIB_FACTOR, 2), round(total_bytes / GIB_FACTOR, 2))


def get_cached_ip_count(subdomain: str) -> int:
    """Get IP count from cache."""
    try:
        return cache.get(f"ip_{subdomain}", 0)
    except Exception as e:
        logger.warning(f"Failed to get cached IP count for {subdomain}: {e}")
        return 0


def get_cached_monthly_ip_count(subdomain: str, year_month: str) -> int:
    """
    Get monthly IP count from cache.

    Args:
        subdomain: The app subdomain
        year_month: Year-month string in format 'YYYYMM'.
    """
    try:
        cache_key = f"monthly_ip_{subdomain}_{year_month}"
        return cache.get(cache_key, 0)
    except Exception as e:
        logger.error(f"Failed to get cached monthly IP count for {subdomain}: {e}")
        return 0


def set_linkonly_reminder_date(instance) -> None:
    """
    Set the link permission level reminder email date.
    This date will then be used by the periodic task remind_about_link_only_apps
    """
    today = timezone.localdate()
    days_to_the_reminder = 180
    instance.reminder_date_linkonly_privacy = today + timezone.timedelta(days=days_to_the_reminder)


def deep_merge_dict(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """
    Deep merge two dictionaries, with override taking precedence.

    Args:
        base: Base dictionary
        override: Override dictionary that takes precedence

    Returns:
        Merged dictionary
    """
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge_dict(result[key], value)
        else:
            result[key] = value
    return result


def get_merged_k8s_values(instance: BaseAppInstance, ensure_up_to_date: bool = True) -> dict[str, Any]:
    """
    Get k8s_values for an app instance, merged with k8s_values_override if present.

    Args:
        instance: The app instance
        ensure_up_to_date: If True, calls set_k8s_values() to ensure values are current

    Returns:
        Dictionary containing merged k8s_values
    """
    if ensure_up_to_date:
        instance.set_k8s_values()

    # Get base k8s_values
    values = instance.k8s_values or {}

    # Merge with override values if present
    if instance.k8s_values_override:
        values = deep_merge_dict(values, instance.k8s_values_override)

    return values


def generate_helm_install_command(
    instance: BaseAppInstance | None = None,
    release_name: str | None = None,
    chart: str | None = None,
    namespace: str | None = None,
    values_file: str | None = None,
    version: str | None = None,
) -> str:
    """
    Generate the helm install command for an app instance or from direct parameters.
    This matches the logic used in tasks.py deploy_resource and helm_install functions.

    Args:
        instance: The app instance (if provided, other parameters override instance values)
        release_name: Release name (overrides instance subdomain if provided)
        chart: Chart name/URL (overrides instance.chart if provided)
        namespace: Namespace (overrides instance namespace if provided)
        values_file: Optional path to values file (if None, will use -f <values-file> placeholder)
        version: Chart version (overrides parsed version if provided)

    Returns:
        Helm install command string
    """
    # If instance is provided, get values from it
    if instance:
        values = get_merged_k8s_values(instance, ensure_up_to_date=False)
        if release_name is None:
            release_name = values.get("subdomain", instance.name)
        if namespace is None:
            namespace = values.get("namespace", "default")
        if chart is None:
            chart = instance.chart

    # Ensure required parameters are set
    if release_name is None:
        raise ValueError("release_name must be provided either via instance or directly")
    if chart is None:
        raise ValueError("chart must be provided either via instance or directly")
    if namespace is None:
        namespace = "default"

    # Determine version and chart format (same logic as deploy_resource in tasks.py)
    # Only parse if version is not already provided (chart may already be parsed)
    parsed_version = version
    if version is None:
        if "ghcr" in chart:
            parsed_version = chart.split(":")[-1]
            chart = "oci://" + chart.split(":")[0]
        elif chart.startswith("oci://"):
            # Use regex module (imported as re) to match tasks.py pattern
            CHART_REGEX = re.compile(r"^(?P<chart>.+):(?P<version>.+)$")
            match = CHART_REGEX.match(chart)
            if match:
                chart = match.group("chart")
                parsed_version = match.group("version")

    # Base command (same logic as helm_install in tasks.py)
    if "volumek8s" in chart:
        # Force reinstall doesn't work with volumek8s chart
        command = f"helm upgrade --install {release_name} {chart} --namespace {namespace}"
    else:
        command = f"helm upgrade --force --install {release_name} {chart} --namespace {namespace}"

    if values_file:
        command += f" -f {values_file}"
    else:
        # Use placeholder if no file specified
        command += " -f <values-file>"

    # Append version if deploying via ghcr
    if parsed_version:
        command += f" --version {parsed_version} --repository-cache /app/charts/.cache/helm/repository"

    return command


def export_k8s_values_to_yaml(instances: QuerySet[BaseAppInstance] | Iterable[BaseAppInstance]) -> str:
    """
    Export k8s_values for app instances as YAML string with helm install command comments.

    Args:
        instances: Queryset or list of BaseAppInstance objects

    Returns:
        YAML string representation of the values with helm install commands as comments

    Raises:
        ValueError: If instances is empty or YAML conversion fails
    """
    if not instances:
        raise ValueError("No app instances provided")

    # Collect values and helm commands from all instances
    exported_values = {}
    helm_commands = {}

    for instance in instances:
        # Get merged values
        values = get_merged_k8s_values(instance, ensure_up_to_date=True)

        # Generate helm install command
        helm_command = generate_helm_install_command(instance)

        # Use a unique key for each instance (name + id to ensure uniqueness)
        instance_key = f"{instance.name}_{instance.id}"
        exported_values[instance_key] = values
        helm_commands[instance_key] = helm_command

    # Convert to YAML
    try:
        yaml_content = yaml.dump(exported_values, default_flow_style=False, sort_keys=False, allow_unicode=True)

        # Prepend helm install commands as comments
        comments = []
        comments.append("# Helm install commands for the exported app instances:")
        comments.append("#")

        for instance_key, helm_cmd in helm_commands.items():
            comments.append(f"# {instance_key}:")
            comments.append(f"#   {helm_cmd}")
            comments.append("#")

        # Combine comments and YAML content
        return "\n".join(comments) + "\n" + yaml_content
    except Exception as e:
        logger.error(f"Error converting values to YAML: {e}")
        raise ValueError(f"Error exporting values to YAML: {e}") from e


def _apply_additional_invenio_metadata(target_metadata: dict[str, Any], extra: dict[str, Any]) -> None:
    """
    Apply additional form-only metadata into Invenio metadata.

    Only allow specific keys and enforce correct structure.
    """
    # Allowlist of keys permitted coming from the form
    allowed = {"languages"}  # extend later: "funding", etc.

    for key, value in extra.items():
        if key not in allowed:
            continue  # ignore unknown/unsafe keys

        if key == "languages":
            # Expect either ""/None or a string like "eng" or a list of {"id": "..."}
            if not value:
                target_metadata.pop("languages", None)
            elif isinstance(value, str):
                target_metadata["languages"] = [{"id": value}]
            elif isinstance(value, list):
                target_metadata["languages"] = value


def generate_invenio_metadata(app_instance: Any, additional_metadata: dict[str, Any] | None = None) -> Dict[str, Any]:
    """
    Generate direct InvenioRDM metadata structure.

    Args:
        app_instance: Application instance object

    Returns:
        Dictionary with InvenioRDM metadata structure
    """
    # Get basic app data
    app_data: Dict[str, Any] = model_to_dict(app_instance, exclude=["_state"])

    # Get user data
    try:
        user_instance: User = User.objects.get(id=app_instance.owner_id)
    except User.DoesNotExist as error:
        raise ValueError(f"User with id {app_instance.owner_id} does not exist") from error

    # Convert models to dictionaries
    user_data: Dict[str, Any] = model_to_dict(user_instance, exclude=["_state", "password"])

    # Get user full name
    user_full_name: str = f"{user_data.get('first_name', '')} {user_data.get('last_name', '')}".strip()
    user_first_name: str = user_data.get("first_name", "")
    user_family_name: str = user_data.get("last_name", "")
    user_email: str = user_data.get("email", "")

    if not user_full_name:
        user_full_name = user_email.split("@")[0] if user_email else "Unknown"
        user_first_name = "No First Name Given"
        user_family_name = "No Family Name Given"

    publication_date = ""
    if hasattr(app_instance, "created_on"):
        publication_date = app_instance.created_on.strftime("%Y-%m-%d")
    else:
        publication_date = timezone.now().strftime("%Y-%m-%d")

    # Build Invenio metadata structure
    invenio_metadata: Dict[str, Any] = {
        "access": {"record": "public", "files": "public"},
        "files": {"enabled": False},
        "metadata": {
            # Title
            "title": f"Application: {app_data.get('name', 'Unknown')}",
            # Description
            "description": app_data.get("description", "Application deployment on SciLifeLab Serve platform."),
            # Publication Year (as publication_date)
            "publication_date": publication_date,
            # Publisher
            "publisher": "SciLifeLab Data Centre",
            # Resource Type
            "resource_type": {"id": "software", "title": {"en": "Software"}},
            # Creator (User as personal contributor)
            "creators": [
                {
                    "person_or_org": {
                        "name": user_full_name,
                        "type": "personal",
                        "given_name": user_first_name,
                        "family_name": user_family_name,
                    },
                    "role": {
                        "id": "relatedperson",
                    },
                }
            ],
            # Contributor (SciLifeLab Data Centre as organizational creator)
            "contributors": [
                {
                    "person_or_org": {"name": "SciLifeLab Data Centre", "type": "organizational"},
                    "role": {
                        "id": "hostinginstitution",
                    },
                }
            ],
            # AlternateIdentifier - APP ID
            "identifiers": [{"identifier": f"SERVE:{app_data.get('id', 'Unknown')}", "scheme": "other"}],
            "related_identifiers": [
                {
                    # 1. Application link (running application)
                    "identifier": app_data.get("url"),
                    "scheme": "url",
                    "relation_type": {"id": "issourceof"},
                    "resource_type": {"id": "software"},
                },
                {
                    # 2. App Image, need for versioning
                    "identifier": app_data.get("image"),
                    "scheme": "other",
                    "relation_type": {
                        "id": "hasversion",
                        "title": {"en": "Has image version"},
                    },
                    "resource_type": {"id": "software"},
                },
            ],
        },
    }
    if additional_metadata:
        _apply_additional_invenio_metadata(invenio_metadata["metadata"], additional_metadata)
    access = app_data.get("access")

    if access == "public":
        k8s_values = app_data.get("k8s_values")

        if k8s_values is None:
            k8s_values = {}

        global_config = k8s_values.get("global", {})

        domain = global_config.get("domain")

        if domain:
            invenio_metadata["metadata"]["related_identifiers"].append(
                {
                    # Landing page (documentation, about page)
                    "identifier": f"https://{domain}/apps/{str(app_data.get('id'))}",
                    "relation_type": {"id": "isdocumentedby"},
                    "resource_type": {"id": "publication-softwaredocumentation"},
                }
            )

    # Log the generated metadata
    logger.info(f"Generated Invenio metadata for app '{app_data.get('name')}':")
    logger.info(json.dumps(invenio_metadata, indent=2))

    return invenio_metadata


def save_metadata_to_invenio_then_mint_doi(
    app_slug: str, app_id: int, additional_metadata: dict[str, Any] | None = None
) -> None:
    """
    Save or update application metadata in InvenioRDM.

    Args:
        app_slug: Application slug for registry lookup
        app_id: Application ID to fetch from database
    """
    import time

    from invenio_client.invenio_client import InvenioClient

    from .app_registry import APP_REGISTRY

    app_is_public = False
    new_image_version = False
    mint_doi = False

    # Get the ORM model class
    model_class: Optional[Type] = APP_REGISTRY.get_orm_model(app_slug)
    if not model_class:
        logger.error(f"Missing model for slug: {app_slug}")
        raise PermissionDenied("Application model not found")

    # Get the application instance
    app = model_class.objects.get(pk=app_id)
    app_data: Dict[str, Any] = model_to_dict(app, exclude=["_state"])

    logger.info(
        "Starting task to create Invenio record and then "
        f"minting DOI for the '{app_slug}' app '{app_data.get('name')}' having app_id '{app_id}'..."
    )

    image_value = app_data["image"]
    logger.debug(
        f"Checking if image '{image_value}' is a new app "
        "or a new version from the already existing images in previous versions..."
    )

    invenio_record_id = app.invenio_record_id

    # Initialize Invenio client, later from env
    invenio_client = InvenioClient(
        base_url=settings.INVENIO_URL,
        token=settings.INVENIO_API_TOKEN,
        auth_scheme="Bearer",
        verify=True,
    )

    # We are creating a new app
    if invenio_record_id is None:
        new_image_version = True
        logger.debug(f"'{image_value}' is new and this is the first version.")

    # another app image version for the app is there now, checking if it is new
    else:
        all_previous_image_version_names = []

        all_invenio_record_versions = invenio_client.get_all_versions(app.invenio_record_id)

        if "hits" in all_invenio_record_versions and "hits" in all_invenio_record_versions["hits"]:
            for i, hit in enumerate(all_invenio_record_versions["hits"]["hits"]):
                all_previous_image_version_names.append(hit["metadata"]["related_identifiers"][1]["identifier"])

        logger.debug(f"All previous image versions used: {all_previous_image_version_names}")

        if image_value in all_previous_image_version_names:
            logger.info(
                f"'{image_value}' is already used in one of the prveious version(s), "
                "meaning DOI already exists. Skipping minting DOI..."
            )
        else:
            new_image_version = True
            logger.debug(f"'{image_value}' is new in this version")

    logger.debug("Checking if app access level is okay..")
    if app_data.get("access") == "public":
        app_is_public = True
        logger.debug("App access is 'public'.")
    else:
        logger.info(f"App access is '{app_data.get('access')}', which is not 'public'. Skipping minting DOI...")

    if new_image_version and app_is_public:
        mint_doi = True
        logger.debug("All checkpoints passed. Now minting DOI...")

    if mint_doi:
        # Log current state
        logger.debug("Before Updating to Invenio")
        logger.debug(f"invenio_record_id: {app.invenio_record_id}")
        logger.debug(f"app_doi: {app.app_doi}")

        try:
            # Transform to Invenio format
            invenio_data: Dict[str, Any] = generate_invenio_metadata(app, additional_metadata=additional_metadata)

            # Extract components
            metadata: Dict[str, Any] = invenio_data["metadata"]
            access: Dict[str, Any] = invenio_data.get("access", {})
            custom_fields: Optional[Dict[str, Any]] = metadata.pop("custom_fields", None)

            # This means this is the first time creating the app
            # Also check for empty string as falsy value
            if app.invenio_record_id is None or app.invenio_record_id == "":
                logger.info(
                    f"Creating new Invenio record for app: {app_slug} "
                    f"with ID: {app_id} and name {invenio_data['metadata']['title']}"
                )

                # Create and publish new record
                draft = invenio_client.create_draft(
                    metadata=metadata,
                    access=access,
                    custom_fields=custom_fields,
                    files={"enabled": False},  # Explicitly set for metadata-only
                )

                logger.debug(f"Created Invenio draft with ID: {draft['id']}")

                # RESERVE INTERNAL DOI FOR THIS VERSION
                try:
                    logger.debug(f"Reserving internal DOI for draft: {draft['id']}")
                    draft_with_doi = invenio_client.reserve_doi(draft["id"])
                    logger.debug(
                        "DOI reserved: " f"{draft_with_doi.get('pids', {}).get('doi', {}).get('identifier', 'Unknown')}"
                    )
                except Exception as doi_error:
                    logger.error(f"Could not reserve DOI: {doi_error}")
                    # Continue without DOI

                published_record = invenio_client.publish_draft(draft["id"])
                logger.info(f"Successfully published Invenio record with ID: {published_record['id']}")
                logger.debug(f"Title: {published_record['metadata']['title']}")

                # Get the DOI from published record
                published_doi = published_record.get("pids", {}).get("doi", {}).get("identifier", "")

                # Update application with record ID
                app.invenio_record_id = published_record["id"]
                app.app_doi = published_doi  # general version
                app.save()

            # This means we are changing the version of the existing app
            else:
                logger.info(f"Updating existing Invenio record: {app.invenio_record_id}")

                new_version = invenio_client.create_new_version(app.invenio_record_id)
                logger.debug(f"Created new version with ID: {new_version['id']}")

                # Get the current new version draft
                current_new_version_draft = invenio_client.get_draft(new_version["id"])

                # Update the new version draft - need to add publication_date
                logger.debug("Updating the new version draft...")

                updated_new_version = invenio_client.update_draft(
                    record_id=current_new_version_draft["id"],
                    metadata={
                        **metadata,
                        # when a new version is created, it has the publication_date and version removed
                        # (as those are typically replaced in a new version)
                        "publication_date": datetime.now().strftime("%Y-%m-%d"),
                    },
                    access=current_new_version_draft.get("access"),
                    files={"enabled": False},  # Explicitly set for metadata-only
                    custom_fields=current_new_version_draft.get("custom_fields"),
                    pids=current_new_version_draft.get("pids", {}),
                )
                logger.debug(f"Updated new version draft ID: {updated_new_version['id']}")
                logger.debug(f"Updated new version draft title: {updated_new_version['metadata']['title']}")

                # RESERVE INTERNAL DOI FOR THIS VERSION
                try:
                    logger.debug(f"Reserving internal DOI for draft: {updated_new_version['id']}")
                    updated_new_version_with_doi = invenio_client.reserve_doi(updated_new_version["id"])
                    logger.debug(f"DOI reserved: {updated_new_version_with_doi['pids']['doi']['identifier']}")
                except Exception as doi_error:
                    logger.error(f"Could not reserve DOI: {doi_error}")
                    # Continue without DOI

                # Publish the new version
                logger.debug("Publishing the new version...")
                published_new_version = invenio_client.publish_draft(updated_new_version["id"])
                logger.info(f"Published new version: {published_new_version['id']}")

                # Get the actual DOI from published record
                published_doi = published_new_version.get("pids", {}).get("doi", {}).get("identifier", "")

                app.invenio_record_id = published_new_version["id"]
                app.app_doi = published_doi
                app.save()

            logger.debug("allow some time after saving...")
            time.sleep(3)

            # Log final state
            logger.debug("=== FINAL INVENIO RECORD STATUS ===")
            logger.debug(f"invenio_record_id: {app.invenio_record_id}")
            logger.info(f"app_doi: {app.app_doi}")

            # Get and print latest version information
            logger.debug("=== INVENIO RECORD VERSION INFORMATION ===")

            # Get all versions to see the full history
            logger.debug("Waiting 3 seconds for Invenio to process...")
            time.sleep(3)
            all_versions = invenio_client.get_all_versions(app.invenio_record_id)
            versions_total = all_versions.get("hits", {}).get("total", 0)
            logger.debug(f"Total versions: {versions_total}")

            # Print details of each version
            if "hits" in all_versions and "hits" in all_versions["hits"]:
                logger.debug("Version history:")
                for i, hit in enumerate(all_versions["hits"]["hits"]):
                    logger.debug(
                        f"  Version {i+1}: ID={hit.get('id')}, "
                        f"DOI={hit.get('pids', {}).get('doi', {}).get('identifier', '')}, "
                        f"App-Image={hit['metadata']['related_identifiers'][1]['identifier']}, "
                        f"Title='{hit.get('metadata', {}).get('title')}', "
                        f"Index={hit.get('versions', {}).get('index')},"
                    )

        except Exception as e:
            logger.error(f"Error in save_invenio_metadata: {e}")
            import traceback

            logger.error(traceback.format_exc())
            raise

    logger.info(
        "Invenio record and then minting DOI for "
        f"the '{app_slug}' app '{app_data.get('name')}' having app_id '{app_id}' creation task is completed."
    )
