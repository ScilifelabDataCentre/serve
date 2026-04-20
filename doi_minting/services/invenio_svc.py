"""
Invenio Record Management Service

This module provides a clean interface for managing Invenio records and DOI minting for application instances.
"""

import json
import logging
import time
import traceback
from datetime import datetime
from typing import Any, List, Optional, Type, TypedDict

from django.conf import settings
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.forms.models import model_to_dict

from apps.background_tasks.utils import resolve_app_access, resolve_app_image
from doi_minting.clients.invenio_client import InvenioClient
from doi_minting.clients.invenio_client.mock_client import MockInvenioClient
from studio.utils import get_logger

from .schemas import (
    AccessConfig,
    AdditionalMetadata,
    Affiliation,
    AppData,
    Award,
    AwardIdentifier,
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
        self, base_url: Optional[str] = None, token: Optional[str] = None, verify: bool = True, mock_mode: bool = False
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
        invenio_record_id = getattr(app_instance, "invenio_record_id", None)
        if not invenio_record_id:
            logger.debug(f"No existing Invenio record ID for app, image '{image_value}' is new.")
            return False

        try:
            all_versions = self.client.get_all_versions(invenio_record_id)

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

    def is_app_access_public(self, app_instance: Any) -> tuple[bool, str]:
        """
        Check if DOI minting is allowed for the app's current access level.

        Args:
            app_instance: The application instance to check

        Returns:
            Tuple of (is_eligible, reason)
        """
        access = resolve_app_access(app_instance)

        # Check if app is public
        if access != "public":
            if access:
                return False, f"DOI minting is only available for Public apps. Visibility level: {access}"
            return False, "DOI minting is only available for public apps."

        return True, "App is public"

    def is_app_eligible_for_doi(self, app_instance: Any) -> tuple[bool, str]:
        """
        Check if the application is eligible for DOI minting.

        Args:
            app_instance: The application instance to check

        Returns:
            Tuple of (is_eligible, reason)
        """
        is_public, reason = self.is_app_access_public(app_instance)
        if not is_public:
            return False, reason

        # Check if it's a new image version
        image_value = resolve_app_image(app_instance)
        if not image_value:
            return False, "DOI minting requires an app image."
        if self.check_image_version_exists(app_instance, image_value):
            return False, f"Image '{image_value}' already exists in previous versions"
        return True, "App is eligible for DOI minting"

    def _are_subjects_different(self, current_subjects: Any, new_subjects: Any) -> bool:
        """Compare subjects lists with case-insensitive and order-independent comparison."""
        if current_subjects is None or new_subjects is None:
            return bool(current_subjects != new_subjects)

        def extract_subject_text(subject: Any) -> str:
            return str(subject.get("subject", "")) if isinstance(subject, dict) else str(subject)

        current_texts = sorted([extract_subject_text(s).lower().strip() for s in current_subjects])
        new_texts = sorted([extract_subject_text(s).lower().strip() for s in new_subjects])

        return current_texts != new_texts

    def has_app_metadata_changed(
        self, app_instance: Any, new_metadata: InvenioMetadata, current_metadata_obj: Optional["InvenioMetadata"] = None
    ) -> tuple[bool, str]:
        """
        Check if the new metadata for an app differ from the current metadata in its Invenio record.

        Args:
            app_instance: The application instance to check
            new_metadata: The new metadata Pydantic model to compare
            current_metadata_obj: Optional current metadata to avoid fetching it again

        Returns:
            Tuple of (changed: bool, reason: str)
        """
        if not app_instance.invenio_record_id:
            logger.debug("App instance has no Invenio record ID.")
            return False, "App does not have an Invenio record."

        if current_metadata_obj is None:
            return False, "Current metadata not provided for metadata check."

        # Ensure new_metadata is a Pydantic model before calling model_dump
        if isinstance(new_metadata, dict):
            from .schemas import InvenioMetadata

            new_metadata = InvenioMetadata(**new_metadata)

        # Compare new_metadata to current_metadata (shallow comparison)
        changed_fields = []
        new_metadata_dict = new_metadata.model_dump(mode="json")
        current_metadata_dict = current_metadata_obj.model_dump(mode="json")

        for key, value in new_metadata_dict.items():
            current_value = current_metadata_dict.get(key)
            if key == "subjects":
                # Special handling for subjects: case-insensitive and order-independent comparison
                subjects_changed = self._are_subjects_different(current_value, value)
                if subjects_changed:
                    changed_fields.append(key)
            elif current_value != value:
                changed_fields.append(key)

        if changed_fields:
            logger.info(f"Metadata has changed: {', '.join(changed_fields)}")
            return True, f"Metadata fields changed: {', '.join(changed_fields)}"
        else:
            logger.info("No metadata changes detected.")
            return False, "No metadata changes detected."

    def has_app_image_changed(
        self, app_instance: Any, new_image: str, current_metadata_obj: Optional["InvenioMetadata"] = None
    ) -> tuple[bool, str]:
        """Check if the app image has changed compared to the current Invenio record."""
        if not app_instance.invenio_record_id:
            return False, "No Invenio record exists"

        try:
            # Use provided metadata or fetch it
            if current_metadata_obj is None:
                return False, "Current metadata not provided for image check."
            else:
                current_metadata_dict = current_metadata_obj.model_dump(mode="json")
                related_ids = current_metadata_dict.get("related_identifiers") or []
                logger.debug(f"Using provided metadata for image check: {current_metadata_dict}")

            # Ensure related_ids is a list (handle None case)
            if related_ids is None:
                related_ids = []

            logger.debug(f"Related identifiers for image check: {related_ids}")

            # Find current image URL (relation_type with "hasversion")
            current_image_url = None
            for rel_id in related_ids:
                logger.debug(f"Checking related identifier: {rel_id}")
                relation_type_id = rel_id.get("relation_type", {}).get("id", "").lower()
                logger.debug(f"Relation type ID: {relation_type_id}")
                if relation_type_id == "hasversion":
                    current_image_url = rel_id.get("identifier", "")
                    logger.debug(f"Found current image URL: {current_image_url}")
                    break

            # Convert new image to URL format
            new_image_url = f"https://{new_image}" if not new_image.startswith(("http://", "https://")) else new_image
            logger.debug(f"New image URL: {new_image_url}")
            logger.debug(f"Current image URL: {current_image_url}")

            if current_image_url != new_image_url:
                logger.info(f"Image changed: {current_image_url} -> {new_image_url}")
                return True, f"Image changed: {current_image_url} -> {new_image_url}"
            logger.info("Image unchanged")
            return False, "Image unchanged"

        except Exception as e:
            logger.error(f"Error checking image: {e}")
            return False, f"Error checking image: {e}"

    def create_new_record(
        self,
        app_instance: Any,
        invenio_record: InvenioRecord,
    ) -> dict[str, Any]:
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

    def create_new_version(self, app_instance: Any, metadata: InvenioMetadata) -> dict[str, Any]:
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

    def edit_and_publish_record(
        self,
        record_id: str,
        metadata: dict[str, Any],
        access: Optional[dict[str, Any]] = None,
        files: Optional[dict[str, Any]] = None,
        custom_fields: Optional[dict[str, Any]] = None,
        pids: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """
        Edit a published record: create a draft, update it with new metadata, and publish it.

        Args:
            record_id: The identifier of the published record to edit.
            metadata: The new metadata dict to update the draft with.
            access: (Optional) Updated access options.
            files: (Optional) Updated files options.
            custom_fields: (Optional) Updated custom fields.
            pids: (Optional) Updated persistent identifiers.

        Returns:
            The published record data after update.
        """
        logger.info(f"Editing and publishing Invenio record with ID: {record_id}")
        # Step 1: Create a draft from the published record
        draft_record = self.client.edit_published_record(record_id)
        draft_id = draft_record.get("id")
        logger.debug(f"Draft created from published record: {draft_id}")

        # Step 2: Update the draft with new metadata
        updated_draft = self.client.update_draft(
            record_id=draft_id,
            metadata=metadata,
            access=access,
            files=files,
            custom_fields=custom_fields,
            pids=pids,
        )
        logger.debug(f"Draft updated with new metadata: {updated_draft}")

        # Step 3: Publish the draft
        published_record = self.client.publish_draft(draft_id)
        record_id_val = None
        if hasattr(published_record, "id"):
            record_id_val = getattr(published_record, "id", None)
        elif isinstance(published_record, dict):
            record_id_val = published_record.get("id", None)
        logger.info(f"Published updated record: {record_id_val}")
        if not isinstance(published_record, dict):
            raise TypeError("publish_draft did not return a dict")
        return published_record

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

    def get_app_metadata(self, record_id: str) -> Optional["InvenioMetadata"]:
        """
        Retrieve metadata for a given Invenio record ID as an InvenioMetadata Pydantic model.

        Args:
            record_id: The Invenio record ID to retrieve metadata for
        Returns:
            InvenioMetadata instance or None if not found/invalid
        """
        try:
            record = self.client.get_record(record_id)
            metadata = record.get("metadata", {})
            if not isinstance(metadata, dict):
                logger.error(f"Metadata for record ID {record_id} is not a dict.")
                return None
            from .schemas import InvenioMetadata

            try:
                return InvenioMetadata(**metadata)
            except Exception as validation_error:
                logger.error(f"Validation error for InvenioMetadata (record {record_id}): {validation_error}")
                return None
        except Exception as e:
            logger.error(f"Error retrieving record {record_id}: {e}")
            return None

    def extract_language_id(self, metadata: InvenioMetadata) -> Optional[str]:
        """
        Extract the language ID from Invenio record metadata.

        Args:
            metadata: The InvenioMetadata instance to extract language from
        """
        if metadata is None:
            logger.warning("Metadata is None, cannot extract language")
            return None

        metadata_dict = metadata.model_dump(mode="json")
        logger.info(f"Extracting language from metadata dict: {metadata_dict}")

        if not isinstance(metadata_dict, dict):
            logger.warning("Metadata dict is not a dict")
            return None

        languages = metadata_dict.get("languages")
        logger.info(f"Found languages: {languages} (type: {type(languages)})")

        if not isinstance(languages, list) or not languages:
            logger.warning("Languages is not a list or is empty")
            return None

        language_entry = languages[0]
        logger.info(f"First language entry: {language_entry} (type: {type(language_entry)})")

        if not isinstance(language_entry, dict):
            logger.warning("Language entry is not a dict")
            return None

        language_id = language_entry.get("id")
        logger.info(f"Extracted language ID: '{language_id}' (type: {type(language_id)})")

        if not isinstance(language_id, str):
            logger.warning("Language ID is not a string")
            return None

        return language_id

    def extract_funding(self, metadata: InvenioMetadata) -> Optional[list[dict[str, Any]]]:
        """
        Extract funding information from Invenio record metadata.

        Args:
            metadata: The InvenioMetadata instance to extract funding from
        """
        if metadata is None:
            logger.warning("Metadata is None, cannot extract funding")
            return None

        metadata_dict = metadata.model_dump(mode="json")
        if not isinstance(metadata_dict, dict):
            return None

        funding = metadata.model_dump(mode="json").get("funding", None)
        if not isinstance(funding, list):
            return []

        items: list[dict[str, Any]] = []
        for entry in funding:
            if not isinstance(entry, dict):
                continue

            funder = entry.get("funder")
            if not isinstance(funder, dict):
                continue

            funder_id = funder.get("id")
            if not isinstance(funder_id, str) or not funder_id:
                continue

            funder_name = funder.get("name")
            if not isinstance(funder_name, str) or not funder_name:
                funder_name = funder_id

            item: dict[str, str] = {
                "funder_id": funder_id,
                "funder_name": funder_name,
            }

            award = entry.get("award")
            if isinstance(award, dict):
                award_number = award.get("number")
                if isinstance(award_number, str) and award_number:
                    item["number"] = award_number

                award_title = award.get("title")
                if isinstance(award_title, str) and award_title:
                    item["title"] = award_title
                elif isinstance(award_title, dict) and award_title:
                    title_en = award_title.get("en")
                    if isinstance(title_en, str) and title_en:
                        item["title"] = title_en
                    else:
                        for localized_title in award_title.values():
                            if isinstance(localized_title, str) and localized_title:
                                item["title"] = localized_title
                                break

                award_url = award.get("url")
                if not (isinstance(award_url, str) and award_url):
                    identifiers = award.get("identifiers")
                    if isinstance(identifiers, list):
                        for identifier_entry in identifiers:
                            if not isinstance(identifier_entry, dict):
                                continue
                            if identifier_entry.get("scheme") != "url":
                                continue
                            identifier_value = identifier_entry.get("identifier")
                            if isinstance(identifier_value, str) and identifier_value:
                                award_url = identifier_value
                                break
                if isinstance(award_url, str) and award_url:
                    item["url"] = award_url

            items.append(item)

        return items

    def extract_creators(self, metadata: InvenioMetadata) -> Optional[list[dict[str, Any]]]:
        if metadata is None:
            logger.warning("Metadata is None, cannot extract creators")
            return None

        creators = metadata.model_dump(mode="json").get("creators", None)
        logger.info(f"Extracting creators from metadata: {creators} (type: {type(creators)})")

        if not creators or not isinstance(creators, list):
            logger.warning("No creators found or creators is not a list")
            return []

        items: list[dict[str, str]] = []
        for i, entry in enumerate(creators):
            logger.info(f"Processing creator {i}: {entry}")

            if not isinstance(entry, dict):
                logger.warning(f"Creator {i} is not a dict, skipping")
                continue

            # Handle new nested person_or_org structure
            person_or_org = entry.get("person_or_org")
            logger.info(f"Creator {i} person_or_org: {person_or_org}")

            if not isinstance(person_or_org, dict):
                logger.warning(f"Creator {i} person_or_org is not a dict, skipping")
                continue

            creator_name = person_or_org.get("name")
            if not isinstance(creator_name, str) or not creator_name:
                # Fall back to constructing name from given_name and family_name
                given_name = person_or_org.get("given_name", "")
                family_name = person_or_org.get("family_name", "")
                logger.info(f"Creator {i} constructing name from given: '{given_name}', family: '{family_name}'")

                if given_name and family_name:
                    creator_name = f"{given_name} {family_name}"
                elif given_name or family_name:
                    creator_name = given_name or family_name
                else:
                    logger.warning(f"Creator {i} has no name information, skipping")
                    continue  # Skip if no name available

            # Extract affiliation information
            affiliation = ""
            affiliations = entry.get("affiliations")
            logger.info(f"Creator {i} affiliations: {affiliations}")

            if isinstance(affiliations, list) and affiliations:
                # Get the first affiliation's name
                first_affiliation = affiliations[0]
                if isinstance(first_affiliation, dict):
                    affiliation = first_affiliation.get("name", "")
                    logger.info(f"Creator {i} extracted affiliation: '{affiliation}'")

            # Extract ORCID from identifiers
            orcid = ""
            identifiers = person_or_org.get("identifiers")
            logger.info(f"Creator {i} identifiers: {identifiers}")

            if isinstance(identifiers, list):
                for identifier in identifiers:
                    if isinstance(identifier, dict) and identifier.get("scheme") == "orcid":
                        orcid = identifier.get("identifier", "")
                        logger.info(f"Creator {i} found ORCID: '{orcid}'")
                        break

            item: dict[str, str] = {
                "creator_id": orcid,
                "creator_name": creator_name,
                "affiliation": affiliation,
            }
            logger.info(f"Creator {i} final item: {item}")

            items.append(item)

        logger.info(f"Extracted {len(items)} creators total: {items}")
        return items

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

        # Handle creators metadata
        creators_input = extra.get("creators")
        logger.debug(f"[Invenio] creators_input from extra: {creators_input}")
        if creators_input and isinstance(creators_input, list):
            creators_list: list[Creator] = []
            for creator_data in creators_input:
                if isinstance(creator_data, dict):
                    # Build Creator with InvenioRDM-compatible person_or_org structure
                    filtered_data = {
                        "name": creator_data.get("name", ""),
                        "lastName": creator_data.get("lastName", ""),
                        "affiliation": creator_data.get("affiliation", ""),
                        "orcid": creator_data.get("orcid", ""),
                    }
                    logger.debug(f"[Invenio] Processing creator: {filtered_data}")

                    # Create identifiers list for ORCID if provided
                    identifiers = None
                    if filtered_data["orcid"]:
                        identifiers = [Identifier(scheme="orcid", identifier=filtered_data["orcid"])]

                    # Create person name from first and last name
                    first_name = filtered_data["name"] or "Unknown"
                    last_name = filtered_data["lastName"] or "Creator"
                    full_name = f"{first_name} {last_name}"

                    # Create person_or_org structure with required fields for personal type
                    person_or_org = PersonOrOrg(
                        name=full_name,
                        type="personal",
                        given_name=first_name,
                        family_name=last_name,
                        identifiers=identifiers,
                    )

                    # Create affiliations list if affiliation exists
                    affiliations = None
                    affiliation_data = creator_data.get("affiliation")
                    if affiliation_data:
                        logger.debug(
                            f"[Invenio] Processing affiliation data: {affiliation_data} "
                            f"(type: {type(affiliation_data)})"
                        )
                        affiliations_list = []

                        if isinstance(affiliation_data, str):
                            # Simple string affiliation - try ROR lookup
                            from apps.helpers import fetch_ror_id_for_org

                            # TODO: Use ror_id=fetch_ror_id_for_org(affiliation_data) when ROR
                            # vocabulary is loaded into the Invenio instance
                            ror_id = None
                            affiliations_list.append(Affiliation(name=affiliation_data, id=ror_id))
                        elif isinstance(affiliation_data, dict) and "ror_id" in affiliation_data:
                            # ROR API format: transform to structured Affiliation
                            # Temporarily set id to None until ROR vocabulary is loaded into Invenio
                            affiliations_list.append(
                                Affiliation(
                                    name=affiliation_data.get("title", ""),
                                    id=None,
                                )
                            )
                        elif isinstance(affiliation_data, dict) and "identifier" in affiliation_data:
                            # ORCID-sourced format: structured affiliation with identifier
                            identifier = affiliation_data.get("identifier", "")

                            affiliations_list.append(
                                Affiliation(
                                    name=affiliation_data.get("name", ""),
                                    id=identifier,
                                )
                            )
                        else:
                            name = str(affiliation_data)
                            if isinstance(affiliation_data, dict):
                                name = affiliation_data.get("name") or affiliation_data.get("title", name)
                            affiliations_list.append(Affiliation(name=name))

                        affiliations = affiliations_list

                    creator = Creator(person_or_org=person_or_org, affiliations=affiliations)
                    logger.debug(f"[Invenio] Created Creator object: {creator}")
                    creators_list.append(creator)

            if creators_list:
                target_metadata["creators"] = creators_list
                logger.debug(f"[Invenio] Applied {len(creators_list)} creators from form data")
                logger.debug(f"[Invenio] creators_list contents: {creators_list}")
            else:
                logger.warning("[Invenio] creators_input was not empty but no valid creators were created")
            # If creators_input exists but results in empty list, keep existing creators
        else:
            logger.debug("[Invenio] No valid creators_input provided, keeping existing creators")
        # If no creators_input provided, keep existing creators (don't modify target_metadata)
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

    def _build_creators(
        self,
        user_full_name: str,
        user_first_name: str,
        user_family_name: str,
        user_orcid: str = "",
        user_affiliation: str = "",
    ) -> list[Creator]:
        """Build the creators list with user information."""

        # Create identifiers list for ORCID if provided
        identifiers = None
        if user_orcid:
            identifiers = [Identifier(scheme="orcid", identifier=user_orcid)]

        # InvenioRDM requires family_name and given_name for personal type
        # Ensure they are never None/empty
        final_given_name = user_first_name if user_first_name else "No First Name Given"
        final_family_name = user_family_name if user_family_name else "No Family Name Given"

        person_or_org = PersonOrOrg(
            name=user_full_name,
            type="personal",
            given_name=final_given_name,
            family_name=final_family_name,
            identifiers=identifiers,
        )

        affiliations = None
        if user_affiliation:
            affiliations = [Affiliation(name=user_affiliation)]

        creator = Creator(person_or_org=person_or_org, affiliations=affiliations)

        return [creator]

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
                    identifier=f"https://{app_data.image}",
                    scheme="url",
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

    def generate_invenio_record(
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
        user_data: dict[str, Any] = model_to_dict(user_instance, exclude=["_state", "password"])

        # Get user profile data for ORCID and affiliation
        user_orcid = ""
        user_affiliation = ""
        try:
            user_profile = user_instance.userprofile
            user_orcid = user_profile.orcid_id or ""
            user_affiliation = user_profile.get_organization_name() if user_profile.get_affiliations() else ""
        except Exception:
            # UserProfile doesn't exist or other error - use defaults
            pass

        # Get user full name
        user_full_name: str = f"{user_data.get('first_name', '')} {user_data.get('last_name', '')}".strip()
        user_first_name: str = user_data.get("first_name", "")
        user_family_name: str = user_data.get("last_name", "")
        user_email: str = user_data.get("email", "")

        # Handle missing names - InvenioRDM requires family_name for personal type
        if not user_full_name:
            user_full_name = user_email.split("@")[0] if user_email else "Unknown"

        dates = self._build_dates(app_instance)
        publication_date = next(
            (d.date.strftime("%Y-%m-%d") for d in dates if d.type.id == "available"),
            datetime.now().strftime("%Y-%m-%d"),  # in case the app has not yet been made publicly available, use today
        )

        # Build components using helper methods
        creators = self._build_creators(user_full_name, user_first_name, user_family_name, user_orcid, user_affiliation)
        identifiers = self._build_identifiers(str(app_data.id))
        related_identifiers = self._build_related_identifiers(app_data)

        # Add documentation link if applicable
        # Modifies the list in place by reference
        self._add_documentation_link(related_identifiers, app_data)

        # Build metadata using Pydantic models
        metadata = InvenioMetadata(
            title=app_data.name,
            description=app_data.description,
            publication_date=publication_date,  # this one is a separate field on purpose
            dates=dates,
            publisher="SciLifeLab Serve",
            resource_type=ResourceType(id="software", title={"en": "Software"}),
            creators=creators,
            identifiers=identifiers,
            related_identifiers=related_identifiers,
        )

        # Apply additional metadata if provided
        if additional_metadata:
            metadata_dict = metadata.model_dump()
            logger.debug(
                "[Invenio] metadata_dict before apply_additional: creators = %s",
                metadata_dict.get("creators", "NOT_FOUND"),
            )
            self._apply_additional_invenio_metadata(metadata_dict, additional_metadata)
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

        # Check if the app is publicly accessible
        is_public, reason = self.is_app_access_public(app_instance)

        # Early exit for non-public apps
        if not is_public:
            logger.info(f"Skipping DOI minting: {reason}")
            return

        logger.debug("App is eligible for DOI minting or updating, proceeding...")

        # Generate new metadata for comparison
        invenio_record = self.generate_invenio_record(app_instance, additional_metadata=additional_metadata)

        # Get current metadata once (if record exists)
        current_metadata_obj = None
        if app_instance.invenio_record_id:
            current_metadata_obj = self.get_app_metadata(app_instance.invenio_record_id)

        # Check for changes using the fetched metadata
        metadata_change, metadata_reason = self.has_app_metadata_changed(
            app_instance, invenio_record.metadata, current_metadata_obj
        )
        image_change, image_reason = self.has_app_image_changed(app_instance, app_data.image, current_metadata_obj)

        logger.info(
            f"Change detection results - Image change: {image_change} ({image_reason}), "
            f"Metadata change: {metadata_change} ({metadata_reason})"
        )

        logger.debug("App is eligible for DOI minting or updating, proceeding...")

        try:
            # Prioritize image change (new version) over metadata change (edit record)
            if image_change:
                logger.info(f"App image has changed: {image_reason}. Creating new version.")
                published_record = self.create_new_version(app_instance, invenio_record.metadata)
            elif metadata_change:
                logger.info(f"Metadata has changed: {metadata_reason}. Updating existing record.")
                published_record = self.edit_and_publish_record(
                    record_id=app_instance.invenio_record_id,
                    metadata=invenio_record.metadata.model_dump(mode="json", by_alias=True),
                    files={"enabled": False},
                )
            elif not app_instance.invenio_record_id or app_instance.invenio_record_id == "":
                logger.info(f"Creating a new Invenio record for app '{app_data.name}'")
                published_record = self.create_new_record(app_instance, invenio_record)
            else:
                logger.info(f"Creating a new version of Invenio record for app '{app_data.name}'")
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
