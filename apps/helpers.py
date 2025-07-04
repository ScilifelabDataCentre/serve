import json
from datetime import datetime
from typing import Any, Optional, Tuple

import regex as re
import requests
from django.conf import settings
from django.contrib.auth.models import User
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db import transaction
from django.forms.models import model_to_dict
from django.utils import timezone
from prometheus_client.parser import text_string_to_metric_families

from apps.constants import AppActionOrigin, HandleUpdateStatusResponseCode
from apps.types_.subdomain import SubdomainCandidateName
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
                return image

        raise ValidationError(f"Tag '{tag}' not found in GHCR image. Please try again.")

    except KeyError:
        raise ValidationError("Unable to find GHCR image tag. Please try again.")


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
                "affiliation": get_university_suffix_information(user_profile.affiliation),
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


def get_minio_usage_v2(minio_service_name):
    logger.error(str(minio_service_name))
    metrics_url = f"http://{minio_service_name}/minio/v2/metrics/cluster"
    logger.error(str(metrics_url))

    try:
        # Fetch the minio metrics from the provided URL
        raw = requests.get(metrics_url, timeout=5).text

    except Exception as e:
        logger.error(f"Failed to fetch metrics from {metrics_url}: {e}")
        return None

    try:
        used_bytes = sum(
            float(s.value)
            for fam in text_string_to_metric_families(raw)
            if fam.name == "minio_cluster_usage_total_bytes"
            for s in fam.samples
        )
    except Exception as e:
        logger.error(f"Failed to parse 'minio_cluster_usage_total_bytes' from metrics: {e}")
        return None

    try:
        total_bytes = sum(
            float(s.value)
            for fam in text_string_to_metric_families(raw)
            if fam.name == "minio_cluster_capacity_usable_total_bytes"
            for s in fam.samples
        )
    except Exception as e:
        logger.error(f"Failed to parse 'minio_cluster_capacity_usable_total_bytes' from metrics: {e}")
        return None

    # Convert bytes to GiB and round to 2 decimal places
    used_gib = round(used_bytes / 1_073_741_824, 2)
    total_gib = round(total_bytes / 1_073_741_824, 2)

    return used_gib, total_gib


def get_minio_usage(minio_service_name: str) -> Optional[Tuple[float, float]]:
    metrics_url = f"http://{minio_service_name}/minio/v2/metrics/cluster"

    try:
        response = requests.get(metrics_url, timeout=5)
        response.raise_for_status()
        raw_metrics = response.text
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
    except Exception as e:
        logger.error(f"MinIO metrics parsing failed: {e}")
        return None

    # Convert to GiB and round
    return (round(used_bytes / GIB_FACTOR, 2), round(total_bytes / GIB_FACTOR, 2))
