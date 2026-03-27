"""
DOI provisioning background task.

This task sends app metadata to Invenio and mints a DOI when the app is eligible
(e.g. public access, new image version). The task is optional (is_critical=False) so
deployment is not blocked if DOI minting fails.
"""

from __future__ import annotations

import json
from typing import Any

from apps.background_tasks.base import BaseBackgroundTask
from apps.background_tasks.registry import TASK_REGISTRY
from apps.background_tasks.utils import resolve_app_image
from doi_minting.services.schemas import Creator, Subject
from studio.utils import get_logger

logger = get_logger(__name__)


def _build_additional_metadata(
    app_instance,
    *,
    language: str | None = None,
    funding: list[dict[str, Any]] | str | None = None,
    creators: list[Creator] | None = None,
    subjects: list[Subject] | None = None,
) -> dict[str, Any] | None:
    """
    Build additional_metadata from app instance for Invenio (language, subjects/tags).

    Mirrors the form-derived metadata used in helpers.create_instance_from_form().
    """
    additional_metadata: dict[str, Any] = {}

    # Language is a form-only field (not a persisted model field). Prefer the
    # form-provided value passed through task kwargs, and only fall back to the
    # instance if present for some app types.
    lang = language or getattr(app_instance, "language", None)
    if lang:
        additional_metadata["languages"] = lang

    funding_entries = funding
    if isinstance(funding_entries, str):
        try:
            funding_entries = json.loads(funding_entries)
        except json.JSONDecodeError:
            logger.warning("Invalid funding payload received by DOI provisioning task; skipping funding metadata.")
            funding_entries = []

    if isinstance(funding_entries, list):
        additional_metadata["funding"] = funding_entries

    # Creators from form data
    if creators and isinstance(creators, list):
        additional_metadata["creators"] = creators
        logger.debug(f"DOI provisioning: Added {len(creators)} creators from form data")

    # Subjects/tags from form data (prefer form data over model instance tags)
    if subjects and isinstance(subjects, list):
        # Form-processed subjects/tags take priority
        additional_metadata["subjects"] = subjects
        logger.debug(f"DOI provisioning: Added {len(subjects)} subjects from form data")
    elif hasattr(app_instance, "tags") and app_instance.tags:
        # Fallback to model instance tags if no form data
        try:
            tag_names = [t.name for t in app_instance.tags.all()]
            if tag_names:
                additional_metadata["subjects"] = tag_names
                logger.debug(f"DOI provisioning: Added {len(tag_names)} subjects from model instance")
        except Exception:
            tag_names = None

    return additional_metadata if additional_metadata else None


@TASK_REGISTRY.register(
    name="doi_provisioning",
    is_critical=False,
    execution_order=2,
    app_types=["customapp", "dashapp", "shinyproxyapp", "shinyapp", "gradio", "streamlit", "tissuumaps", "depictio"],
)
class DOIProvisioningTask(BaseBackgroundTask):
    """
    Task: provision DOI via Invenio when the app is eligible.

    DOI minting is now always enabled. Calls the Invenio DOI minting flow
    as used in the inline path in helpers.
    """

    max_retries = 2
    task_type = "external_api"
    timeout_seconds = 300

    def execute(self, app_instance, **kwargs) -> dict[str, Any]:
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
        additional_metadata = _build_additional_metadata(
            app_instance,
            language=kwargs.get("language"),
            funding=kwargs.get("funding"),
            creators=kwargs.get("creators"),
            subjects=kwargs.get("tags"),  # Note: task receives 'tags' but function expects 'subjects'
        )

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
