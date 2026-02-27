"""
Optional DOI provisioning background task.

When the doi_minting_using_invenio waffle switch is on, this task sends app
metadata to Invenio and mints a DOI when the app is eligible (e.g. public
access, new image version). The task is optional (is_critical=False) so
deployment is not blocked if DOI minting fails.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import waffle  # type: ignore

from apps.background_tasks.base import BaseBackgroundTask
from apps.background_tasks.registry import TASK_REGISTRY
from apps.background_tasks.utils import resolve_app_image
from studio.utils import get_logger

logger = get_logger(__name__)

DOI_MINTING_SWITCH = "doi_minting_using_invenio"


def _build_additional_metadata(app_instance) -> Optional[Dict[str, Any]]:
    """
    Build additional_metadata from app instance for Invenio (language, subjects/tags).

    Mirrors the form-derived metadata used in helpers.create_instance_from_form().
    """
    additional_metadata: Dict[str, Any] = {}

    # Language: only available from form in helpers; instance may not have it.
    lang = getattr(app_instance, "language", None)
    if lang:
        additional_metadata["languages"] = lang

    # Tags / subjects (from SocialMixin; tagulous TagField)
    if hasattr(app_instance, "tags") and app_instance.tags:
        try:
            tag_names = [t.name for t in app_instance.tags.all()]
            if tag_names:
                additional_metadata["subjects"] = tag_names
        except Exception:
            pass

    return additional_metadata if additional_metadata else None


@TASK_REGISTRY.register(
    name="doi_provisioning",
    is_critical=False,
    execution_order=2,
    app_types=["customapp"],
)
class DOIProvisioningTask(BaseBackgroundTask):
    """
    Optional task: provision DOI via Invenio when the app is eligible.

    Respects the doi_minting_using_invenio waffle switch. When the switch is off,
    the task exits successfully without calling Invenio (feature flag still controls
    behaviour). When on, calls the same Invenio DOI minting flow as the inline
    path in helpers.
    """

    max_retries = 2
    task_type = "external_api"
    timeout_seconds = 300

    def execute(self, app_instance, **kwargs) -> Dict[str, Any]:
        if not waffle.switch_is_active(DOI_MINTING_SWITCH):
            logger.debug(
                "DOI provisioning skipped: waffle switch '%s' is off",
                DOI_MINTING_SWITCH,
            )
            return {"skipped": True, "reason": "doi_minting_using_invenio switch is off"}

        # Only run for instances that have an image (use shared resolver for all app types)
        image = resolve_app_image(app_instance)
        if not image:
            logger.debug(
                "DOI provisioning skipped: app instance %s has no image",
                app_instance.id,
            )
            return {"skipped": True, "reason": "no image"}

        app_slug = app_instance.app.slug
        instance_id = app_instance.id
        additional_metadata = _build_additional_metadata(app_instance)

        try:
            from doi_minting.services.invenio_svc import (
                save_metadata_to_invenio_then_mint_doi,
            )

            save_metadata_to_invenio_then_mint_doi(app_slug, instance_id, additional_metadata=additional_metadata)
            return {
                "success": True,
                "app_slug": app_slug,
                "app_id": instance_id,
            }
        except Exception as e:
            # Log but do not block deployment (task is optional)
            logger.warning(
                "DOI provisioning failed for app %s (id=%s): %s",
                app_slug,
                instance_id,
                e,
                exc_info=True,
            )
            raise
