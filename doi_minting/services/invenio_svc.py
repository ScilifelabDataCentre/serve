"""
Invenio Record Management Service

This module provides a clean interface for managing Invenio records and DOI minting for application instances.
"""

import json
import logging
import time
import traceback
from datetime import datetime
from typing import Any, Dict, Optional, Type, TypedDict

from django.conf import settings
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.forms.models import model_to_dict

from doi_minting.clients.invenio_client import InvenioClient
from doi_minting.clients.invenio_client.mock_client import MockInvenioClient
from studio.utils import get_logger

from .schemas import (
    AccessConfig,
    AdditionalMetadata,
    AppData,
    Award,
    AwardIdentifier,
    Contributor,
    Creator,
    Date,
    DateType,
    FilesConfig,
    Funder,
    Funding,
    Identifier,
    InvenioMetadata,
    InvenioRecord,
    Language,
    PersonOrOrg,
    RelatedIdentifierItem,
    RelationType,
    ResourceType,
    Role,
    Subject,
)

logger = get_logger(__name__)


class InvenioService:
    """
    Manages Invenio record creation, versioning, and DOI minting for application instances.
    """

    client: Any

    def __init__(
        self, base_url: Optional[str] = None, token: Optional[str] = None, verify: bool = True, mock_mode: bool = True
    ):
        """
        Initialize the Invenio Record Service.

        Args:
            base_url: Invenio instance base URL (defaults to settings.INVENIO_URL)
            token: API token (defaults to settings.INVENIO_API_TOKEN)
            verify: Whether to verify SSL certificates
            mock_mode: If True, forces mock mode. Otherwise falls back to settings.INVENIO_MOCK_MODE.
        """
        self.base_url = base_url or settings.INVENIO_URL
        self.token = token or settings.INVENIO_API_TOKEN
        self.verify = verify
        self.mock_mode = mock_mode or settings.INVENIO_MOCK_MODE

        if self.mock_mode:
            self.client = MockInvenioClient()
        else:
            self.client = InvenioClient(
                base_url=self.base_url,
                token=self.token,
                auth_scheme="Bearer",
                verify=self.verify,
            )

    def check_image_version_exists(self, app_instance: Any, image_value: str) -> bool:
        """
        Check if the given image version already exists in Invenio records.

        Args:
            app_instance: The application instance
            image_value: The image identifier to check

        Returns:
            True if image version already exists, False otherwise
        """
        if not app_instance.invenio_record_id:
            logger.debug(f"No existing Invenio record ID for app, image '{image_value}' is new.")
            return False

        try:
            all_versions = self.client.get_all_versions(app_instance.invenio_record_id)

            if "hits" in all_versions and "hits" in all_versions["hits"]:
                existing_images = []
                for hit in all_versions["hits"]["hits"]:
                    related_ids = hit["metadata"].get("related_identifiers", [])
                    if len(related_ids) > 1:
                        existing_images.append(related_ids[1]["identifier"])

                logger.debug(f"All previous image versions: {existing_images}")

                if image_value in existing_images:
                    logger.info(f"Image '{image_value}' already exists in previous versions.")
                    return True

        except Exception as e:
            logger.error(f"Error checking existing versions: {e}")
            # Assume it's new if we can't check

        return False

    def is_app_eligible_for_doi(self, app_instance: Any) -> tuple[bool, str]:
        """
        Check if the application is eligible for DOI minting.

        Args:
            app_instance: The application instance to check

        Returns:
            Tuple of (is_eligible, reason)
        """
        app_data = model_to_dict(app_instance, exclude=["_state"])

        # Check if app is public
        if app_data.get("access") != "public":
            return False, f"App access is '{app_data.get('access')}', not 'public'"

        # Check if it's a new image version
        image_value = app_data["image"]
        if self.check_image_version_exists(app_instance, image_value):
            return False, f"Image '{image_value}' already exists in previous versions"

        return True, "App is eligible for DOI minting"

    def create_new_record(
        self,
        app_instance: Any,
        invenio_record: InvenioRecord,
    ) -> Dict[str, Any]:
        """
        Create a new Invenio record for the application.

        Args:
            app_instance: The application instance
            invenio_record: Complete Invenio record object with metadata, access, and files config

        Returns:
            Published record data
        """
        logger.info(f"Creating new Invenio record for app: {app_instance.id}")

        # Create draft - use mode="json" to ensure datetime objects are serialized as strings
        draft = self.client.create_draft(invenio_record.model_dump(mode="json"))
        logger.debug(f"Created Invenio draft with ID: {draft['id']}")

        # Reserve DOI
        try:
            logger.debug(f"Reserving internal DOI for draft: {draft['id']}")
            draft_with_doi = self.client.reserve_doi(draft["id"])
            reserved_doi = draft_with_doi.get("pids", {}).get("doi", {}).get("identifier", "Unknown")
            logger.debug(f"DOI reserved: {reserved_doi}")
        except Exception as doi_error:
            logger.error(f"Could not reserve DOI: {doi_error}")

        # Publish record
        published_record = self.client.publish_draft(draft["id"])
        logger.info(f"Successfully published Invenio record with ID: {published_record['id']}")
        if not isinstance(published_record, dict):
            raise TypeError("publish_draft did not return a dict")
        return published_record

    def create_new_version(self, app_instance: Any, metadata: InvenioMetadata) -> Dict[str, Any]:
        """
        Create a new version of an existing Invenio record.

        Args:
            app_instance: The application instance
            metadata: Updated metadata for the new version

        Returns:
            Published new version data
        """
        logger.info(f"Creating new version for existing Invenio record: {app_instance.invenio_record_id}")

        # Create new version
        new_version = self.client.create_new_version(app_instance.invenio_record_id)
        logger.debug(f"Created new version with ID: {new_version['id']}")

        # Get current draft
        current_draft = self.client.get_draft(new_version["id"])

        # Update draft with new metadata
        metadata_dict = metadata.model_dump(mode="json")
        updated_metadata = {**metadata_dict}

        updated_version = self.client.update_draft(
            record_id=current_draft["id"],
            metadata=updated_metadata,
            access=current_draft.get("access"),
            files={"enabled": False},
            custom_fields=current_draft.get("custom_fields"),
            pids=current_draft.get("pids", {}),
        )
        logger.debug(f"Updated new version draft ID: {updated_version['id']}")

        # Reserve DOI for new version
        try:
            logger.debug(f"Reserving internal DOI for new version: {updated_version['id']}")
            version_with_doi = self.client.reserve_doi(updated_version["id"])
            reserved_doi = version_with_doi["pids"]["doi"]["identifier"]
            logger.debug(f"DOI reserved: {reserved_doi}")
        except Exception as doi_error:
            logger.error(f"Could not reserve DOI: {doi_error}")

        # Publish new version
        published_version = self.client.publish_draft(updated_version["id"])
        logger.info(f"Published new version: {published_version['id']}")

        if not isinstance(published_version, dict):
            raise TypeError("publish_draft did not return a dict")
        return published_version

    def update_app_instance(self, app_instance: Any, record_id: str, doi: str) -> None:
        """
        Update the application instance with Invenio record ID and DOI.

        Args:
            app_instance: The application instance to update
            record_id: The Invenio record ID
            doi: The DOI identifier
        """
        app_instance.invenio_record_id = record_id
        app_instance.app_doi = doi
        app_instance.save()

        logger.debug(f"Updated app instance - Record ID: {record_id}, DOI: {doi}")

    def _apply_additional_invenio_metadata(
        self, target_metadata: dict[str, Any], extra: AdditionalMetadata
    ) -> dict[str, Any]:
        """
        Apply additional metadata from AdditionalMetadata schema into Invenio metadata.

        Args:
            target_metadata: The metadata dictionary to modify
            extra: Additional metadata following AdditionalMetadata schema

        Returns:
            The modified metadata dictionary
        """
        logger.debug(f"[Invenio] _apply_additional_invenio_metadata: extra={extra} (type={type(extra)})")
        logger.debug(f"[Invenio] Keys in extra: {list(extra.keys()) if isinstance(extra, dict) else 'Not a dict'}")

        # Handle languages field - accept string, list of strings, or list of Language objects
        languages = extra.get("languages")

        language_objs = []
        if isinstance(languages, str):
            # Single language code as string
            language_objs = [Language(id=languages)]
        elif isinstance(languages, list):
            if languages:
                # List of strings or Language objects
                for lang in languages:
                    if isinstance(lang, Language):
                        language_objs.append(lang)
                    elif isinstance(lang, str):
                        language_objs.append(Language(id=lang))
            # If empty list, leave language_objs empty
        if language_objs:
            target_metadata["languages"] = [lang.model_dump(mode="json") for lang in language_objs]
        else:
            target_metadata.pop("languages", None)

        # Handle subject field (accept both 'subject' and 'subjects' as input)
        subject_input = extra.get("subjects") or extra.get("subject")

        if subject_input and isinstance(subject_input, list):
            try:
                from .keywords_service import VocabularyMemoryService

                vocab_service = VocabularyMemoryService()
            except Exception:
                vocab_service = None

            subject_terms = []
            if vocab_service:
                for tag in subject_input:
                    # Extract tag label
                    tag_label = str(tag) if isinstance(tag, str) else None
                    if not tag_label:
                        continue

                    found_match = False
                    # Find matching vocabulary term
                    # TODO - Include term ID/URI in subject when vocab is configured in our Invenio instance
                    for term_id, term_data in vocab_service.term_metadata.items():
                        if term_data.subject and term_data.subject.lower() == tag_label.lower():
                            subject_term = Subject(subject=tag_label)
                            subject_terms.append(subject_term)
                            found_match = True
                            break

                    # If no vocabulary match found, use as free text subject
                    if not found_match:
                        subject_term = Subject(subject=tag_label)
                        subject_terms.append(subject_term)
            else:
                # If no vocabulary service, use all as free text subjects
                for tag in subject_input:
                    tag_label = str(tag) if isinstance(tag, str) else None
                    if tag_label:
                        subject_term = Subject(subject=tag_label)
                        subject_terms.append(subject_term)

            target_metadata["subjects"] = subject_terms if subject_terms else None
        else:
            target_metadata.pop("subjects", None)

        funding_input: Any = extra.get("funding")
        funding_entries: list[Funding] = []
        if isinstance(funding_input, list):
            for item in funding_input:
                if isinstance(item, Funding):
                    funding_entries.append(item)
                    continue
                if not isinstance(item, dict):
                    continue

                raw_funder = item.get("funder")
                raw_funder = raw_funder if isinstance(raw_funder, dict) else {}

                funder_id = item.get("funder_id") or raw_funder.get("id") or item.get("id") or ""
                funder_id = str(funder_id).strip()
                if not funder_id:
                    continue

                funder_name = item.get("funder_name") or raw_funder.get("name") or item.get("name") or ""
                funder_name = str(funder_name).strip()

                raw_award = item.get("award")
                raw_award = raw_award if isinstance(raw_award, dict) else {}
                award_number = str(item.get("number") or raw_award.get("number") or "").strip()
                award_title_raw = item.get("title") or raw_award.get("title") or ""
                award_title: dict[str, str] | str | None = None
                if isinstance(award_title_raw, dict):
                    award_title_localized = {
                        str(lang).strip(): str(text).strip()
                        for lang, text in award_title_raw.items()
                        if str(lang).strip() and isinstance(text, str) and text.strip()
                    }
                    if award_title_localized:
                        award_title = award_title_localized
                elif isinstance(award_title_raw, str) and award_title_raw.strip():
                    # Invenio expects localized award titles; default to English for free-text form input.
                    award_title = {"en": award_title_raw.strip()}
                award_url = str(item.get("url") or raw_award.get("url") or "").strip()
                award_identifiers: list[AwardIdentifier] = []
                raw_award_identifiers = raw_award.get("identifiers")
                if isinstance(raw_award_identifiers, list):
                    for raw_identifier in raw_award_identifiers:
                        if not isinstance(raw_identifier, dict):
                            continue
                        identifier_scheme = str(raw_identifier.get("scheme") or "").strip()
                        identifier_value = str(raw_identifier.get("identifier") or "").strip()
                        if identifier_scheme and identifier_value:
                            award_identifiers.append(
                                AwardIdentifier(
                                    scheme=identifier_scheme,
                                    identifier=identifier_value,
                                )
                            )
                if award_url and not any(
                    identifier.scheme == "url" and identifier.identifier == award_url
                    for identifier in award_identifiers
                ):
                    award_identifiers.append(
                        AwardIdentifier(
                            scheme="url",
                            identifier=award_url,
                        )
                    )
                award = None
                if award_number or award_title or award_identifiers:
                    award = Award(
                        number=award_number or None,
                        title=award_title,
                        identifiers=award_identifiers or None,
                    )

                funding_entry = Funding(
                    funder=Funder(id=funder_id, name=funder_name or None),
                    award=award,
                )
                funding_entries.append(funding_entry)

        if funding_entries:
            target_metadata["funding"] = [entry.model_dump(exclude_none=True) for entry in funding_entries]
        else:
            target_metadata.pop("funding", None)

        logger.debug(f"Applied additional metadata: {extra}. Resulting metadata: {target_metadata}")

        return target_metadata

    def _build_creators(self, user_full_name: str, user_first_name: str, user_family_name: str) -> list[Creator]:
        """Build the creators list with user information."""
        user_person = PersonOrOrg(
            name=user_full_name, type="personal", given_name=user_first_name, family_name=user_family_name
        )

        user_role = Role(id="relatedperson")

        return [Creator(person_or_org=user_person, role=user_role)]

    def _build_contributors(self) -> list[Contributor]:
        """Build the contributors list with SciLifeLab Data Centre."""
        org_person = PersonOrOrg(name="SciLifeLab Data Centre", type="organizational")

        org_role = Role(id="hostinginstitution")

        return [Contributor(person_or_org=org_person, role=org_role)]

    def _build_identifiers(self, app_id: str) -> list[Identifier]:
        """Build the identifiers list with application ID."""
        return [Identifier(identifier=f"SERVE:{app_id}", scheme="other")]

    def _build_related_identifiers(self, app_data: AppData) -> list[RelatedIdentifierItem]:
        """Build the related identifiers list with app URL and image."""
        related_ids = []

        # 1. Application link (running application)
        if app_data.url:
            related_ids.append(
                RelatedIdentifierItem(
                    identifier=app_data.url,
                    scheme="url",
                    relation_type=RelationType(id="issourceof"),
                    resource_type=ResourceType(id="software"),
                )
            )

        # 2. App Image, need for versioning
        if app_data.image:
            related_ids.append(
                RelatedIdentifierItem(
                    identifier=app_data.image,
                    scheme="other",
                    relation_type=RelationType(id="hasversion", title={"en": "Has image version"}),
                    resource_type=ResourceType(id="software"),
                )
            )

        return related_ids

    def _add_documentation_link(self, related_ids: list[RelatedIdentifierItem], app_data: AppData) -> None:
        """Add documentation link if public app with domain."""
        if app_data.access != "public":
            return

        k8s_values = app_data.k8s_values or {}
        domain = k8s_values.get("global", {}).get("domain")

        if domain:
            doc_link = RelatedIdentifierItem(
                identifier="https://{}/apps/{}".format(domain, app_data.id),
                scheme="url",
                relation_type=RelationType(id="isdocumentedby"),
                resource_type=ResourceType(id="publication-softwaredocumentation"),
            )
            related_ids.append(doc_link)

    def _build_dates(self, app_instance: Any) -> list[Date]:
        """Build the dates list with app information."""
        dates: list[Date] = []

        created_on = app_instance.created_on
        if created_on is None:
            raise ValueError("'created_on' cannot be None for DOI minting")
        created_on = created_on.replace(microsecond=0)
        dates.append(
            Date(
                date=created_on,
                type=DateType(id="submitted"),
            )
        )

        updated_on = app_instance.updated_on
        if updated_on is None:
            raise ValueError("'updated_on' cannot be None for DOI minting")
        updated_on = updated_on.replace(microsecond=0)
        dates.append(
            Date(
                date=updated_on,
                type=DateType(id="updated"),
            )
        )

        made_public_on = app_instance.made_public_on
        if made_public_on:
            made_public_on = made_public_on.replace(microsecond=0)
            dates.append(
                Date(
                    date=made_public_on,
                    type=DateType(id="available"),
                )
            )

        return dates

    def generate_invenio_metadata(
        self, app_instance: Any, additional_metadata: Optional[AdditionalMetadata] = None
    ) -> InvenioRecord:
        """
        Generate direct InvenioRDM metadata structure.

        Args:
            app_instance: Application instance object
            additional_metadata: Optional additional metadata to include

        Returns:
            Validated InvenioRDM metadata as Pydantic model
        """
        # Get basic app data
        app_data_dict = model_to_dict(app_instance, exclude=["_state"])
        app_data = AppData(**app_data_dict)

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

        dates = self._build_dates(app_instance)
        publication_date = next(
            (d.date.strftime("%Y-%m-%d") for d in dates if d.type.id == "available"),
            datetime.now().strftime("%Y-%m-%d"),  # in case the app has not yet been made publicly available, use today
        )

        # Build components using helper methods
        creators = self._build_creators(user_full_name, user_first_name, user_family_name)
        contributors = self._build_contributors()
        identifiers = self._build_identifiers(str(app_data.id))
        related_identifiers = self._build_related_identifiers(app_data)

        # Add documentation link if applicable
        # Modifies the list in place by reference
        self._add_documentation_link(related_identifiers, app_data)

        next(d.date.strftime("%Y-%m-%d") for d in dates if d.type.id == "available")

        # Build metadata using Pydantic models
        metadata = InvenioMetadata(
            title=app_data.name,
            description=app_data.description,
            publication_date=publication_date,  # this one is a separate field on purpose
            dates=dates,
            publisher="SciLifeLab Serve",
            resource_type=ResourceType(id="software", title={"en": "Software"}),
            creators=creators,
            contributors=contributors,
            identifiers=identifiers,
            related_identifiers=related_identifiers,
        )

        # Apply additional metadata if provided
        if additional_metadata:
            metadata_dict = metadata.model_dump()
            self._apply_additional_invenio_metadata(metadata_dict, additional_metadata)
            # Debug: log subject type and value before constructing InvenioMetadata
            subj_val = metadata_dict.get("subjects", None)
            logger.debug(f"[Invenio] Subjects field before model: type={type(subj_val)}, value={subj_val}")
            # If subjects is an empty list, keep it as an empty list (not None)
            if "subjects" in metadata_dict and metadata_dict["subjects"] is None:
                metadata_dict["subjects"] = []
            metadata = InvenioMetadata(**metadata_dict)

        # Build complete record
        invenio_record = InvenioRecord(
            access=AccessConfig(record="public", files="public"), files=FilesConfig(enabled=False), metadata=metadata
        )

        # Log the generated metadata
        logger.info(f"Generated Invenio metadata for app '{app_data.name}'")
        logger.info(json.dumps(invenio_record.model_dump(mode="json", by_alias=True), indent=2))

        return invenio_record

    def log_version_information(self, app_instance: Any) -> None:
        """
        Log detailed version information after processing.

        Args:
            app_instance: The application instance
        """
        if not app_instance.invenio_record_id:
            return

        try:
            # Wait for Invenio to process
            time.sleep(3)

            all_versions = self.client.get_all_versions(app_instance.invenio_record_id)
            versions_total = all_versions.get("hits", {}).get("total", 0)
            logger.debug(f"Total versions: {versions_total}")

            if "hits" in all_versions and "hits" in all_versions["hits"]:
                logger.debug("Version history:")
                for i, hit in enumerate(all_versions["hits"]["hits"]):
                    related_ids = hit["metadata"].get("related_identifiers", [])
                    app_image = related_ids[1]["identifier"] if len(related_ids) > 1 else "Unknown"

                    logger.debug(
                        f"  Version {i+1}: ID={hit.get('id')}, "
                        f"DOI={hit.get('pids', {}).get('doi', {}).get('identifier', '')}, "
                        f"App-Image={app_image}, "
                        f"Title='{hit.get('metadata', {}).get('title')}', "
                        f"Index={hit.get('versions', {}).get('index')}"
                    )
        except Exception as e:
            logger.error(f"Error logging version information: {e}")

    def process_app_metadata(
        self, app_slug: str, app_id: int, additional_metadata: Optional[AdditionalMetadata] = None
    ) -> None:
        """
        Process application metadata and mint DOI.

        Args:
            app_slug: Application slug for registry lookup
            app_id: Application ID to fetch from database
            additional_metadata: Optional additional metadata to include
        """
        from apps.app_registry import APP_REGISTRY

        logger.info(f"Starting metadata processing for app '{app_slug}' with ID '{app_id}'")

        # Get the ORM model class
        model_class: Optional[Type[Any]] = APP_REGISTRY.get_orm_model(app_slug)
        if not model_class:
            logger.error(f"Missing model for slug: {app_slug}")
            raise PermissionDenied("Application model not found")

        # Get the application instance
        app_instance = model_class.objects.get(pk=app_id)
        app_data_dict = model_to_dict(app_instance, exclude=["_state"])
        app_data = AppData(**app_data_dict)

        logger.info(f"Processing app '{app_data.name}' with image '{app_data.image}'")

        # Check eligibility for DOI minting
        is_eligible, reason = self.is_app_eligible_for_doi(app_instance)
        if not is_eligible:
            logger.info(f"Skipping DOI minting: {reason}")
            return

        logger.debug("App is eligible for DOI minting, proceeding...")

        try:
            # Generate Invenio metadata
            invenio_record: InvenioRecord = self.generate_invenio_metadata(
                app_instance, additional_metadata=additional_metadata
            )

            # Create or update record
            logger.info(f"About to create or update Invenio record for app '{app_data.name}'")
            logger.info(json.dumps(invenio_record.model_dump(mode="json", by_alias=True), indent=2))
            if not app_instance.invenio_record_id or app_instance.invenio_record_id == "":
                published_record = self.create_new_record(app_instance, invenio_record)
            else:
                published_record = self.create_new_version(app_instance, invenio_record.metadata)

            # Extract DOI and update app instance
            published_doi = published_record.get("pids", {}).get("doi", {}).get("identifier", "")
            self.update_app_instance(app_instance, published_record["id"], published_doi)

            # Allow processing time and log results
            time.sleep(3)
            logger.debug("=== FINAL INVENIO RECORD STATUS ===")
            logger.debug(f"Record ID: {app_instance.invenio_record_id}")
            logger.info(f"DOI: {app_instance.app_doi}")

            # Log version information
            self.log_version_information(app_instance)

        except Exception as e:
            logger.error(f"Error in process_app_metadata: {e}")
            logger.error(traceback.format_exc())
            raise

        logger.info(f"Completed metadata processing for app '{app_data.name}'")


def save_metadata_to_invenio_then_mint_doi(
    app_slug: str, app_id: int, additional_metadata: Optional[AdditionalMetadata] = None
) -> None:
    """
    Invenio and DOI minting process for application metadata.

    Args:
        app_slug: Application slug for registry lookup
        app_id: Application ID to fetch from database
        additional_metadata: Optional additional metadata to include
    """
    invenio_svc = InvenioService()
    invenio_svc.process_app_metadata(app_slug, app_id, additional_metadata)
