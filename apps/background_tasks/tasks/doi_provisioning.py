"""
DOI provisioning background task.

This task sends app metadata to Invenio and reserves a DOI + publishes it
if needed (e.g. public access, new image version).
"""

from __future__ import annotations

import json
from typing import Any

from django.utils.dateparse import parse_datetime

from apps.background_tasks.base import BaseBackgroundTask
from apps.background_tasks.registry import TASK_REGISTRY
from apps.background_tasks.utils import resolve_app_image, select_latest_task_records
from apps.models import BackgroundTask
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

    # Subjects/keywords from form data (prefer form data over model instance subjects_keywords)
    if subjects and isinstance(subjects, list):
        # Form-processed subjects/keywords take priority
        additional_metadata["subjects"] = subjects
        logger.debug(f"DOI provisioning: Added {len(subjects)} subjects from form data")
    elif hasattr(app_instance, "subjects_keywords"):
        # Fallback to model instance subjects_keywords if no form data
        try:
            subjects_keywords = app_instance.subjects_keywords or []
            if subjects_keywords:
                additional_metadata["subjects"] = subjects_keywords
                logger.debug(f"DOI provisioning: Added {len(subjects_keywords)} subjects from model instance")
        except Exception:
            subjects_keywords = None

    return additional_metadata if additional_metadata else None


@TASK_REGISTRY.register(
    name="doi_provisioning",
    is_critical=True,
    execution_order=3,
    app_types=["customapp", "dashapp", "shinyproxyapp", "shinyapp", "gradio", "streamlit"],
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

    def _has_failed_required_checks(self, app_instance, started_at: str | None = None) -> bool:
        earlier_required_tasks = BackgroundTask.objects.filter(
            app_instance_id=app_instance.id,
            is_critical=True,
            execution_order__lt=self.execution_order,
        )
        if started_at:
            parsed_started_at = parse_datetime(started_at)
            if parsed_started_at is not None:
                earlier_required_tasks = earlier_required_tasks.filter(created_at__gte=parsed_started_at)

        latest_earlier_required_tasks = select_latest_task_records(earlier_required_tasks)
        return any(task.status == "failed" for task in latest_earlier_required_tasks)

    def execute(self, app_instance, **kwargs) -> dict[str, Any]:
        # Only run for instances that have an image (use shared resolver for all app types)
        image = resolve_app_image(app_instance)
        if not image:
            logger.debug(
                "DOI provisioning skipped: app instance %s has no image",
                app_instance.id,
            )
            return {"skipped": True, "reason": "no image"}

        if self._has_failed_required_checks(app_instance, kwargs.get("_task_started_at")):
            logger.info(
                "DOI provisioning skipped for app %s: a required deployment check failed earlier",
                app_instance.id,
            )
            return {"skipped": True, "reason": "A required deployment check failed earlier"}

        app_slug = app_instance.app.slug
        instance_id = app_instance.id
        additional_metadata = _build_additional_metadata(
            app_instance,
            language=kwargs.get("language"),
            funding=kwargs.get("funding"),
            creators=kwargs.get("creators"),
            subjects=kwargs.get("subjects_keywords"),
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
            logger.warning(
                "DOI provisioning failed for app %s (id=%s): %s",
                app_slug,
                instance_id,
                e,
                exc_info=True,
            )
            raise
