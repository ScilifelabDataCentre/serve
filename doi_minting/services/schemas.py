"""
Schema definitions for apps module.

This module contains type definitions and validation schemas used throughout the apps module.
Organized with sub-models for better maintainability and reusability.
"""

from __future__ import annotations

from typing import Any, List, TypedDict

from pydantic import BaseModel, ConfigDict, Field


class AdditionalMetadata(TypedDict, total=False):
    """Type definition for additional metadata that can be passed to Invenio."""

    languages: list[Language] | None  # List of Language objects (ISO 639-2 codes) or None
    subject: list[str] | None  # List of tags/keywords for the record


# ============================================================================
# Application Data Models
# ============================================================================


class AppData(BaseModel):
    """Application instance data structure."""

    model_config = ConfigDict(extra="allow")  # Allow additional fields from Django model

    id: int
    name: str
    description: str | None = None
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


class SubjectTerm(BaseModel):
    """Subject/keyword term with full metadata for Invenio subject field."""

    subjectScheme: str
    schemeURI: str
    valueURI: str
    classificationCode: str
    label: str
    lang: str = "en"


class InvenioMetadata(BaseModel):
    """Core Invenio metadata structure with all required and optional fields."""

    # Required core metadata
    title: str
    description: str
    publication_date: str
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
    subject: list[SubjectTerm] | None = None  # List of subject terms for the record


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
