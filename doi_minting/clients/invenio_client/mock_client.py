from typing import Any, Optional


class MockInvenioClient:
    def create_draft(self, record_data: dict[str, Any]) -> dict[str, Any]:
        return {"id": "mock-draft-id"}

    def reserve_doi(self, draft_id: str) -> dict[str, Any]:
        return {"pids": {"doi": {"identifier": "10.1234/mockdoi"}}}

    def publish_draft(self, draft_id: str) -> dict[str, Any]:
        return {"id": "mock-record-id", "pids": {"doi": {"identifier": "10.1234/mockdoi"}}}

    def create_new_version(self, record_id: str) -> dict[str, Any]:
        return {"id": "mock-version-id"}

    def get_draft(self, version_id: str) -> dict[str, Any]:
        return {"id": "mock-draft-id", "access": {}, "custom_fields": {}, "pids": {}}

    def edit_published_record(self, record_id: str) -> dict[str, Any]:
        # Simulate editing a published record (create draft from published)
        return {"id": f"mock-draft-for-{record_id}"}

    def update_draft(
        self,
        record_id: str,
        metadata: Optional[dict[str, Any]] = None,
        access: Optional[dict[str, Any]] = None,
        files: Optional[dict[str, Any]] = None,
        custom_fields: Optional[dict[str, Any]] = None,
        pids: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        return {"id": "mock-draft-id"}

    def get_all_versions(self, record_id: str) -> dict[str, Any]:
        # Return a mock of record versions for a known id, else empty dict
        if (
            record_id == "mock-record-id"
            or record_id.startswith("mock-draft-for-")
            or record_id.startswith("mock-version-for-")
        ):
            return {
                "hits": {
                    "hits": [
                        {
                            "id": "mock-record-id",
                            "parent": {
                                "id": "mock-record-parent-id",
                                "pids": {
                                    "doi": {
                                        "identifier": "10.83812/SCILIFELAB.ppppp-ppppp",
                                    }
                                },
                            },
                            "pids": {
                                "doi": {
                                    "identifier": "10.83812/SCILIFELAB.rrrrr-rrrrr",
                                },
                            },
                            "versions": {"index": 2},
                        },
                        {
                            "id": "mock-record-previous-id",
                            "parent": {
                                "id": "mock-record-parent-id",
                                "pids": {
                                    "doi": {
                                        "identifier": "10.83812/SCILIFELAB.ppppp-ppppp",
                                    }
                                },
                            },
                            "pids": {
                                "doi": {
                                    "identifier": "10.83812/SCILIFELAB.rrrr2-rrrr2",
                                },
                            },
                            "versions": {"index": 1},
                        },
                    ],
                    "total": 2,
                },
                "sortBy": "version",
            }
        return {}

    def get_record(self, record_id: str) -> dict[str, Any]:
        # Return a mock record for a known id, else empty dict
        if (
            record_id == "mock-record-id"
            or record_id.startswith("mock-draft-for-")
            or record_id.startswith("mock-version-for-")
        ):
            return {
                "id": record_id,
                "pids": {"doi": {"identifier": "10.83812/SCILIFELAB.rrrrr-rrrrr"}},
                "parent": {
                    "id": "mock-record-parent-id",
                    "pids": {"doi": {"identifier": "10.83812/SCILIFELAB.ppppp-ppppp"}},
                },
                "metadata": {
                    "title": "Mock App Title",
                    "description": "Mock description of the app.",
                    "publication_date": "2024-01-01",
                    "publisher": "Mock Publisher",
                    "resource_type": {"id": "software", "title": {"en": "Software"}},
                    "languages": [{"id": "eng", "title": {"en": "English"}}],
                    "dates": [
                        {"date": "2024-01-01T10:00:00+00:00", "type": {"id": "submitted"}},
                        {"date": "2024-01-02T12:00:00+00:00", "type": {"id": "updated"}},
                        {"date": "2024-01-03T14:00:00+00:00", "type": {"id": "available"}},
                    ],
                    "identifiers": [{"identifier": "scilifelab-serve:1", "scheme": "other"}],
                    "creators": [
                        {
                            "person_or_org": {
                                "name": "Jane Doe",
                                "type": "personal",
                                "given_name": "Jane",
                                "family_name": "Doe",
                                "identifiers": None,
                            },
                            "affiliations": [
                                {
                                    "name": "Example Research Institute",
                                    "affiliationIdentifier": None,
                                    "affiliationIdentifierScheme": None,
                                    "schemeUri": None,
                                },
                                {
                                    "name": "Another Research Institute",
                                    "affiliationIdentifier": None,
                                    "affiliationIdentifierScheme": None,
                                    "schemeUri": None,
                                },
                            ],
                        },
                        {
                            "person_or_org": {
                                "name": "John Doe",
                                "type": "personal",
                                "given_name": "John",
                                "family_name": "Doe",
                                "identifiers": [
                                    {"identifier": "https://orcid.org/0000-0001-5393-1421", "scheme": "orcid"}
                                ],
                            },
                            "affiliations": [
                                {
                                    "name": "Example Research Institute",
                                    "id": None,
                                }
                            ],
                        },
                    ],
                    "subjects": [{"id": None, "subject": "Genes, pX"}, {"id": None, "subject": "Antigens"}],
                    "related_identifiers": [
                        {
                            "identifier": "https://ghcr.io/scilifelabdatacentre/example-dash:240314-1126",
                            "scheme": "url",
                            "relation_type": {"id": "hasversion", "title": {"en": "Has version"}},
                            "resource_type": {"id": "software", "title": {"en": "Software"}},
                        },
                        {
                            "identifier": "https://r72a47ca4.studio.127.0.0.1.nip.io",
                            "scheme": "url",
                            "relation_type": {"id": "issourceof", "title": {"en": "Is source of"}},
                            "resource_type": {"id": "software", "title": {"en": "Software"}},
                        },
                    ],
                    "funding": [
                        {
                            "funder": {"id": "004hzzk67", "name": "Knut and Alice Wallenberg Foundation"},
                            "award": {
                                "number": "12",
                                "title": {"en": "award 1"},
                                "identifiers": [{"scheme": "url", "identifier": "https://url.com"}],
                                "url": None,
                            },
                        }
                    ],
                },
            }
        return {}
