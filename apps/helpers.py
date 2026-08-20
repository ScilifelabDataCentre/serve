import json
from collections.abc import Iterable
from datetime import datetime
from typing import Any, Dict, NamedTuple, Optional, Type

import regex as re
import requests
import waffle
import yaml
from django.conf import settings
from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db import transaction
from django.db.models.query import QuerySet
from django.forms.models import model_to_dict
from django.utils import timezone
from prometheus_client.parser import text_string_to_metric_families

from apps.constants import (
    UNIVERSITY_NAMES,
    AppActionOrigin,
    HandleUpdateStatusResponseCode,
)
from apps.validators.container_images import (
    get_authenticator_for_registry,
    get_image_architectures,
)
from common.models import UserProfile
from projects.models import Project
from studio.utils import get_logger

from .models import Apps, BaseAppInstance, K8sUserAppStatus, Subdomain

logger = get_logger(__name__)


def parse_funding_sources_json(funding_raw: Any) -> list[dict[str, Any]]:
    """Normalize funding_sources_json from form data into a list."""
    if not funding_raw:
        return []

    parsed_funding = funding_raw
    if isinstance(parsed_funding, str):
        try:
            parsed_funding = json.loads(parsed_funding)
        except json.JSONDecodeError:
            logger.warning(
                "Unable to parse funding_sources_json while creating app. " "Proceeding with empty funding metadata."
            )
            return []

    if not isinstance(parsed_funding, list):
        logger.warning(
            "funding_sources_json has unsupported type %s. Proceeding with empty funding metadata.",
            type(parsed_funding).__name__,
        )
        return []

    return parsed_funding


def parse_related_publications_datasets_json(related_publications_datasets_raw: Any) -> list[dict[str, Any]]:
    """Normalize a related publications/datasets JSON form field into a list."""
    if not related_publications_datasets_raw:
        return []

    parsed_related_publications_datasets = related_publications_datasets_raw
    if isinstance(parsed_related_publications_datasets, str):
        try:
            parsed_related_publications_datasets = json.loads(parsed_related_publications_datasets)
        except json.JSONDecodeError:
            logger.warning(
                "Unable to parse related_publications_json or related_datasets_json while creating app. "
                "Proceeding with empty related publications or datasets metadata."
            )
            return []

    if not isinstance(parsed_related_publications_datasets, list):
        logger.warning(
            "related_publications_json or related_datasets_json has unsupported type %s. "
            "Proceeding with empty related publications/datasets metadata.",
            type(parsed_related_publications_datasets).__name__,
        )
        return []

    return parsed_related_publications_datasets


def get_select_options(project_pk, selected_option=""):
    from apps.types_.subdomain import SubdomainCandidateName

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

    if new_status == "Running" and getattr(settings, "POD_STATUS_AGGREGATION_ENABLED", True):
        from .tasks import verify_app_running

        instance = BaseAppInstance.objects.filter(subdomain__subdomain=release).last()
        if instance is None:
            logger.info(f"No such subdomain exists identified by release={release}")
            return HandleUpdateStatusResponseCode.OBJECT_NOT_FOUND

        verify_app_running.delay(instance.pk)
        logger.debug(f"Running event for release {release} queued a workload readiness check.")
        return HandleUpdateStatusResponseCode.DEFERRED_TO_AGGREGATION

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


class CreateInstanceResult(NamedTuple):
    instance_id: int
    progress_started_at: str | None
    workflow_started: bool
    skip_deploy: bool = False


_DEPICTIO_ACCESS_GROUPS = {
    "private": "auth",
    "project": "auth",
    "public": "open",
    "link": "open",
}


def _is_depictio_access_chart_noop(old_access, new_access):
    if not old_access or not new_access:
        return False
    return _DEPICTIO_ACCESS_GROUPS.get(old_access) == _DEPICTIO_ACCESS_GROUPS.get(new_access)


@transaction.atomic
def create_instance_from_form(
    form,
    project,
    app_slug,
    app_id=None,
    force_redeploy: bool = False,
) -> CreateInstanceResult:
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
    - CreateInstanceResult: instance_id plus progress_started_at/workflow_started metadata.

    Raises:
    - ValueError: If the form does not have a 'subdomain' or if the specified app cannot be found.
    """
    assert form is not None, "This function requires a form object"
    assert project is not None, "This function requires a project object"

    new_app = app_id is None
    requested_app_slug = app_slug
    run_background_tasks_only = False

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
        # Treat every update as a user-initiated change, while the redirect logic
        # decides whether the user should see deployment progress or details.
        user_action = "Changing"
        invenio_metadata_fields = [
            "name",
            "description",
            "language",
            "funding_sources_json",
            "related_publications_json",
            "related_datasets_json",
            "creators",
            "subjects_keywords",
            "invenio_tags",
            "source_code_url",
            "note_on_linkonly_privacy",
        ]

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
                "mount_path",
                "default_url_subpath",
            ]
            logger.debug(f"An existing app has changed. The changed form fields: {form.changed_data}")

            # Because not all forms contain all fields, we check if the supposedly changed field
            # is actually contained in the form
            for field in form.changed_data:
                if field.lower() in redeployment_fields and (
                    field.lower() in form.Meta.fields or field.lower() == "subdomain"
                ):
                    logger.debug("create_instance_from_form.redeploy_field_changed app_id=%s field=%s", app_id, field)
                    do_deploy = True
                    break

            for field in form.changed_data:
                if field.lower() in invenio_metadata_fields:
                    logger.debug(
                        "create_instance_from_form.metadata_only_field_changed app_id=%s field=%s",
                        app_id,
                        field,
                    )
                    run_background_tasks_only = True
                    break

    subdomain_name, is_created_by_user = get_subdomain_name(form)
    logger.info(
        "create_instance_from_form.subdomain_selected app_id=%s subdomain=%s is_created_by_user=%s",
        app_id,
        subdomain_name,
        is_created_by_user,
    )

    # This is needed for Depictio later on.
    original_instance = None
    if not new_app:
        from .app_registry import APP_REGISTRY

        original_instance = APP_REGISTRY.get_orm_model(app_slug).objects.get(pk=app_id)

    instance = form.save(commit=False)

    # Retrieve or create the subdomain. Look up on the unique field only, so an existing
    # row with a different project or is_created_by_user is reused, not inserted again.
    subdomain, created = Subdomain.objects.get_or_create(
        subdomain=subdomain_name,
        defaults={"project": project, "is_created_by_user": is_created_by_user},
    )
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

    # set the date when the app was made public
    if hasattr(instance, "access") and instance.access == "public":
        if instance.made_public_on is None:
            instance.made_public_on = timezone.now()
    else:
        instance.made_public_on = None

    setup_instance(instance, subdomain, app, project, user_action)

    # Depictio public <-> link and private <-> project produce identical
    # rendered manifests, so handle this case.
    if (
        not new_app
        and do_deploy
        and app_slug == "depictio"
        and original_instance is not None
        and _is_depictio_access_chart_noop(
            getattr(original_instance, "access", None), getattr(instance, "access", None)
        )
    ):
        logger.info(
            "create_instance_from_form.depictio_access_chart_noop app_id=%s — treating as metadata-only",
            app_id,
        )
        do_deploy = False
        run_background_tasks_only = True

    # Re-check GPU capacity under lock before saving.
    from apps.gpu import ensure_gpu_capacity

    ensure_gpu_capacity(instance)

    instance_id = save_instance_and_related_data(instance, form)
    if do_deploy:
        reset_k8s_user_app_status_for_deployment(instance)
    logger.info(
        "create_instance_from_form.instance_saved app_id=%s instance_id=%s user_action=%s do_deploy=%s",
        app_id,
        instance_id,
        user_action,
        do_deploy,
    )

    progress_started_at: str | None = None

    if do_deploy:
        serialized_instance = instance.serialize()
        logger.info(
            "create_instance_from_form.enqueue_on_commit app_id=%s instance_id=%s model=%s pk=%s",
            app_id,
            instance_id,
            serialized_instance.get("model"),
            serialized_instance.get("pk"),
        )
        logger.debug(f"Now deploying resource app with app_id = {app_id}")

        progress_started_at = timezone.now().isoformat()

        _deploy_with_background_tasks_and_doi(
            instance,
            form,
            app_slug,
            progress_started_at=progress_started_at,
        )
    elif run_background_tasks_only:
        # Only run background tasks, do not deploy
        progress_started_at = timezone.now().isoformat()

        _run_background_tasks_and_doi_only(
            instance,
            form,
            app_slug,
            progress_started_at=progress_started_at,
        )
        logger.info("create_instance_from_form.background_tasks_only app_id=%s instance_id=%s", app_id, instance_id)
    else:
        logger.info("create_instance_from_form.deploy_skipped app_id=%s instance_id=%s", app_id, instance_id)

    return CreateInstanceResult(
        instance_id=instance_id,
        progress_started_at=progress_started_at,
        workflow_started=do_deploy or run_background_tasks_only,
        skip_deploy=run_background_tasks_only and not do_deploy,
    )


def _run_background_tasks_and_doi_only(
    instance,
    form,
    app_slug,
    skip_deploy=True,
    progress_started_at: str | None = None,
):
    """Run background tasks (including DOI minting) for an instance, without deployment."""
    from .tasks import run_background_tasks

    logger.info(
        "run_background_tasks_and_doi_only start for app_slug=%s instance_id=%s skip_deploy=%s",
        app_slug,
        instance.id,
        skip_deploy,
    )

    serialized_instance, task_kwargs_by_task_name = _prepare_doi_task_kwargs(instance, form, app_slug)

    transaction.on_commit(
        lambda: run_background_tasks.delay(
            serialized_instance,
            app_slug,
            task_kwargs_by_task_name,
            progress_started_at,
            skip_deploy=skip_deploy,
        )
    )


def _deploy_with_background_tasks_and_doi(
    instance,
    form,
    app_slug,
    progress_started_at: str | None = None,
):
    """Deploy using background tasks with DOI minting."""
    from .tasks import run_background_tasks

    logger.info(
        "_deploy_with_background_tasks_and_doi start for app_slug=%s instance_id=%s",
        app_slug,
        instance.id,
    )

    serialized_instance, task_kwargs_by_task_name = _prepare_doi_task_kwargs(instance, form, app_slug)

    transaction.on_commit(
        lambda: run_background_tasks.delay(
            serialized_instance,
            app_slug,
            task_kwargs_by_task_name,
            progress_started_at,
        )
    )


def _prepare_doi_task_kwargs(instance, form, app_slug):
    """
    Prepare the serialized instance and DOI provisioning task kwargs for background tasks.
    Returns (serialized_instance, task_kwargs_by_task_name)
    """
    serialized_instance = instance.serialize()

    # NB: Before we only included public apps in DOI provisioning, now all apps
    # Public apps are published in Invenio; non-public apps are saved as a draft.
    funding_list = parse_funding_sources_json(form.cleaned_data.get("funding_sources_json"))

    # Both related publications and datasets go under the same metadata field on Invenio,
    # specifically as related identifiers but with different resource_type values.
    related_publications_list = parse_related_publications_datasets_json(
        form.cleaned_data.get("related_publications_json")
    )
    related_datasets_list = parse_related_publications_datasets_json(form.cleaned_data.get("related_datasets_json"))
    related_identifiers_list = related_publications_list + related_datasets_list

    # Get creators data from form if available
    creators_data = None
    if hasattr(form, "get_creators_data"):
        creators_data = form.get_creators_data()
        logger.debug(f"Background task: creators_data from form: {creators_data}")

    # Get processed tags data from form if available
    subjects_keywords_data = form.cleaned_data.get("subjects_keywords") if hasattr(form, "cleaned_data") else None
    logger.debug(f"Background task: subjects_keywords data from form: {subjects_keywords_data}")

    task_kwargs_by_task_name = {
        "doi_provisioning": {
            "language": form.cleaned_data.get("language"),
            "funding": funding_list,
            "related_publications_datasets": related_identifiers_list,
            "creators": creators_data,
            "subjects_keywords": form.cleaned_data.get("subjects_keywords"),
        },
    }
    logger.debug("DOI provisioning will be handled by background task for app '%s' (id=%s).", app_slug, instance.id)

    return serialized_instance, task_kwargs_by_task_name


def get_subdomain_name(form):
    subdomain_tuple = form.cleaned_data.get("subdomain")
    if not str(subdomain_tuple):
        raise ValueError("Subdomain is required")
    return subdomain_tuple


def get_or_create_status(instance, app_id):
    raise DeprecationWarning("Deprecated function. To be removed.")
    # return instance.app_status if app_id else AppStatus.objects.create()


def _old_release_is_removed(delete_result: Any) -> bool:
    """
    Whether delete_resource confirmed that nothing is left in the cluster.

    Without a confirmed result the old release must be assumed to be running.
    """
    if not isinstance(delete_result, dict):
        return False

    return bool(delete_result.get("success")) or bool(delete_result.get("release_missing"))


SUBDOMAIN_RELEASE_EXCLUDED_APP_SLUGS = ("volumeK8s", "netpolicy")


def release_subdomain_after_delete(instance: BaseAppInstance) -> Optional[Subdomain]:
    """
    Detach a deleted app from its subdomain so that the name becomes available again.

    Only user-chosen names are reclaimed, and volumes are excluded because the apps that
    mount them still read their subdomain.

    Must only be called once the release is confirmed gone from the cluster, otherwise the
    name becomes available while its resources are still running.

    Returns the detached subdomain, or None if nothing was released. The caller is
    responsible for saving the instance.
    """
    subdomain = instance.subdomain

    if subdomain is None or not subdomain.is_created_by_user:
        return None

    if instance.app.slug in SUBDOMAIN_RELEASE_EXCLUDED_APP_SLUGS:
        return None

    instance.subdomain = None
    return subdomain


def handle_subdomain_change(instance: Any, subdomain: str, subdomain_name: str) -> None:
    """
    Detects if there has been a user-initiated subdomain change and if so,
    then re-creates the app instance, also re-deploying the k8s resource.

    Raises:
    - SubdomainChangeError: if the app's current release could not be removed from the
      cluster. The subdomain is then left unchanged.
    """
    from apps.types_.subdomain import SubdomainChangeError

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
        delete_result = delete_resource(instance.serialize(), AppActionOrigin.USER.value)

        if not _old_release_is_removed(delete_result):
            logger.error(
                "handle_subdomain_change.aborted_release_not_removed instance_id=%s "
                "old_subdomain=%s requested_subdomain=%s error=%s",
                instance.pk,
                instance.subdomain.subdomain,
                subdomain_name,
                delete_result.get("error") if isinstance(delete_result, dict) else None,
            )
            raise SubdomainChangeError()

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


def reset_k8s_user_app_status_for_deployment(instance: BaseAppInstance) -> None:
    status_object = getattr(instance, "k8s_user_app_status", None)
    info = getattr(instance, "info", None)
    info_changed = False

    if isinstance(info, dict) and "helm" in info:
        updated_info = dict(info)
        updated_info.pop("helm", None)
        instance.info = updated_info
        instance.save(update_fields=["info"])
        info_changed = True
        logger.info("reset_k8s_user_app_status_for_deployment.cleared_helm_info instance_id=%s", instance.pk)

    if status_object is None:
        return

    if status_object.status is None and status_object.info in (None, {}):
        if not info_changed:
            logger.info("reset_k8s_user_app_status_for_deployment.noop instance_id=%s", instance.pk)
        return

    status_object.status = None
    status_object.info = None
    status_object.save(update_fields=["status", "info"])
    logger.info("reset_k8s_user_app_status_for_deployment instance_id=%s", instance.pk)


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
        auth = get_authenticator_for_registry("ghcr.io")
        if auth:
            architectures = get_image_architectures(
                auth=auth,
                repo=f"{owner}/{image_name}",
                reference=tag,
                registry="ghcr.io",
            )
        else:
            architectures = []
        if architectures and any(arch.arch != "amd64" for arch in architectures):
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
        auth = get_authenticator_for_registry("registry-1.docker.io")
        if auth:
            architectures = get_image_architectures(
                auth=auth,
                repo=repository,
                reference=tag,
            )
        else:
            architectures = []
        if architectures and any(arch.arch != "amd64" for arch in architectures):
            raise ValidationError(
                f"Docker image '{image}' is not built for the right CPU architecture. "
                "Please use docker build --platform linux/amd64 to build your image"
            )


def fetch_ror_id_for_org(org_name: str) -> str | None:
    """
    Fetch ROR ID for organization name using existing ROR API logic.
    Returns ROR ID (without URL prefix) or None if not found.
    """
    if not org_name or not org_name.strip():
        return None

    try:
        # Use same logic as RORAutocompleteView
        response = requests.get("https://api.ror.org/organizations", params={"query": org_name.strip()}, timeout=2)
        response.raise_for_status()
        data = response.json()

        # Look for exact organization name match (case-insensitive)
        for item in data.get("items", []):
            ror_id = item.get("id", "")

            # Extract organization title from names array (same logic as RORAutocompleteView)
            title = ""
            for name in item.get("names", []):
                if "ror_display" in name.get("types", []):
                    title = name.get("value", "")
                    break

            # If no ror_display found, use first name
            if not title and item.get("names"):
                title = item["names"][0].get("value", "")

            # Check for exact match
            if title and title.lower() == org_name.lower():
                # Clean ROR ID (remove URL prefixes)
                ror_id = ror_id.replace("https://ror.org/", "").replace("https://api.ror.org/organizations/", "")
                logger.debug(f"Found ROR ID for '{org_name}': {ror_id}")
                return ror_id

        logger.debug(f"No exact ROR match found for '{org_name}'")
        return None

    except Exception as e:
        logger.debug(f"ROR API error for '{org_name}': {e}")
        return None


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
        affs = user_profile.get_affiliations()
        user_data["affiliations"] = affs

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
                    "affiliations": [
                        {
                            "@type": "Organization",
                            "name": aff.get("title", ""),
                            "department": aff.get("department", ""),
                            "identifier": aff.get("ror_id", ""),
                        }
                        for aff in user_data.get("affiliations", [])
                    ],
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
                "name": user_data.get("affiliations", [{}])[0].get("title", "")
                if user_data.get("affiliations")
                else "",
                "additionalProperty": {
                    "@type": "PropertyValue",
                    "name": "department",
                    "value": user_data.get("affiliations", [{}])[0].get("department", "")
                    if user_data.get("affiliations")
                    else "",
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

    no_force_charts = ("volumek8s", "depictio")
    if any(name in chart for name in no_force_charts):
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
