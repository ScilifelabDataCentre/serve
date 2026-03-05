"""
Schema definitions for apps module.

This module contains type definitions and validation schemas used throughout the apps module.
Organized with sub-models for better maintainability and reusability.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, List, Literal, TypedDict

from pydantic import BaseModel, ConfigDict, field_validator


class AdditionalMetadata(TypedDict, total=False):
    """Type definition for additional metadata that can be passed to Invenio."""

    languages: list[Language] | None  # List of Language objects (ISO 639-2 codes) or None
    subjects: list[Subject] | None  # List of tags/keywords for the record
    funding: list[Funding] | None  # List of funding entries for the record


# ============================================================================
# Application Data Models
# ============================================================================


class AppData(BaseModel):
    """Application instance data structure."""

    model_config = ConfigDict(extra="allow")  # Allow additional fields from Django model

    id: int
    name: str
    description: str
    image: str
    url: str | None = None
    access: str
    k8s_values: dict[str, Any] | None = None


# ============================================================================
# Person and Organization Models
# ============================================================================


class PersonOrOrg(BaseModel):
    """Person or organization in Invenio metadata."""

    name: str
    type: str  # "personal" or "organizational"
    given_name: str | None = None
    family_name: str | None = None


class Role(BaseModel):
    """Role definition with localized titles."""

    id: str
    title: dict[str, Any] | None = None


class Creator(BaseModel):
    """Creator with person/org info and role."""

    person_or_org: PersonOrOrg
    role: Role


class Contributor(BaseModel):
    """Contributor with person/org info and role."""

    person_or_org: PersonOrOrg
    role: Role


# ============================================================================
# Resource and Content Type Models
# ============================================================================


class ResourceType(BaseModel):
    """Resource type definition with localized titles."""

    id: str  # e.g., "software", "dataset", "publication"
    title: dict[str, Any] | None = None  # {"en": "Software"}


class Language(BaseModel):
    """Language specification using ISO codes."""

    id: str  # ISO 639-2 language code like "eng", "swe"


class Funder(BaseModel):
    """Funder reference used by Invenio funding metadata."""

    id: str
    name: str | None = None


class AwardIdentifier(BaseModel):
    """Identifier entry for an award."""

    scheme: str
    identifier: str


class Award(BaseModel):
    """Optional grant/award details for a funder entry."""

    number: str | None = None
    title: dict[str, str] | str | None = None
    identifiers: list[AwardIdentifier] | None = None
    url: str | None = None


class Funding(BaseModel):
    """Funding entry containing a required funder and optional award details."""

    funder: Funder
    award: Award | None = None


# ============================================================================
# Date Models
# ============================================================================


class DateType(BaseModel):
    id: Literal["submitted", "accepted", "available", "updated"]


class Date(BaseModel):
    """Various dates"""

    date: datetime
    type: DateType

    @field_validator("date")
    @classmethod
    def require_timezone(cls, v: datetime) -> datetime:
        if v.tzinfo is None or v.utcoffset() is None:
            raise ValueError("Date must be timezone-aware (e.g. 2026-02-23T13:40:27+00:00)")
        return v


# ============================================================================
# Identifier Models
# ============================================================================


class Identifier(BaseModel):
    """Basic identifier with scheme."""

    identifier: str
    scheme: str


class RelationType(BaseModel):
    """Relationship type between resources."""

    id: str  # e.g., "issourceof", "hasversion", "isdocumentedby"
    title: dict[str, Any] | None = None  # {"en": "Has image version"}


class RelatedIdentifierItem(BaseModel):
    """Individual related identifier with full context."""

    identifier: str
    scheme: str  # e.g., "url", "other", "doi"
    relation_type: RelationType
    resource_type: ResourceType | None = None


# ============================================================================
# Core Metadata Structure
# ============================================================================


class Subject(BaseModel):
    """Subject/keyword term for Invenio subject field."""

    id: str | None = None  # Controlled vocabulary identifier URI
    subject: str | None = None  # Free text keyword


class AutocompleteTerm(BaseModel):
    """Autocomplete term with search metadata."""

    id: str
    label: str
    source: str
    score: float


class TermMetadata(BaseModel):
    """Term metadata with detailed information."""

    subject: str | None = None
    subject_scheme: str | None = None
    scheme_uri: str | None = None
    value_uri: str | None = None
    classification_code: str | None = None
    lang: str | None = None


class InvenioMetadata(BaseModel):
    """Core Invenio metadata structure with all required and optional fields."""

    # Required core metadata
    title: str
    description: str
    publication_date: str
    dates: list[Date]
    publisher: str
    resource_type: ResourceType

    # People and organizations
    creators: List[Creator]
    contributors: List[Contributor]

    # Identifiers and relationships
    identifiers: List[Identifier]
    related_identifiers: List[RelatedIdentifierItem] | None = None

    # Optional metadata
    languages: List[Language] | None = None
    subjects: list[Subject] | None = None  # List of subject terms for the record
    funding: list[Funding] | None = None


# ============================================================================
# Access and Configuration Models
# ============================================================================


class AccessConfig(BaseModel):
    """Access permissions for record and files."""

    record: str = "public"
    files: str = "public"


class FilesConfig(BaseModel):
    """File attachment configuration."""

    enabled: bool = False  # Whether files are attached to this record


# ============================================================================
# Complete Record Structure
# ============================================================================


class InvenioRecord(BaseModel):
    """Complete Invenio record structure ready for API submission."""

    access: AccessConfig
    files: FilesConfig
    metadata: InvenioMetadata
