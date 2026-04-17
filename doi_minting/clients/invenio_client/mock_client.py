from typing import Any, Optional


class MockInvenioClient:
    def create_draft(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
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
        metadata: dict[str, Any],
        access: dict[str, Any],
        files: dict[str, Any],
        custom_fields: Optional[dict[str, Any]],
        pids: dict[str, Any],
    ) -> dict[str, Any]:
        return {"id": "mock-draft-id"}

    def get_all_versions(self, record_id: str) -> dict[str, Any]:
        return {"hits": {"hits": []}}

    def get_record(self, record_id: str) -> dict[str, Any]:
        # Return a mock record for a known id, else empty dict
        if (
            record_id == "mock-record-id"
            or record_id.startswith("mock-draft-for-")
            or record_id.startswith("mock-version-for-")
        ):
            return {
                "id": record_id,
                "metadata": {
                    "title": "Mock App Title",
                    "description": "Mock description of the app.",
                    "publication_date": "2024-01-01",
                    "publisher": "Mock Publisher",
                    "resource_type": {"id": "software", "title": {"en": "Software"}},
                    "languages": [{"id": "swe"}],
                    "dates": [
                        {"date": "2024-01-01T10:00:00+00:00", "type": {"id": "submitted"}},
                        {"date": "2024-01-02T12:00:00+00:00", "type": {"id": "updated"}},
                        {"date": "2024-01-03T14:00:00+00:00", "type": {"id": "available"}},
                    ],
                    "identifiers": [{"identifier": "SERVE:mock-app-id", "scheme": "other"}],
                    "creators": [
                        {
                            "person_or_org": {
                                "name": "admin@serve.scilifelab.se User",
                                "type": "personal",
                                "given_name": "admin@serve.scilifelab.se",
                                "family_name": "User",
                                "identifiers": None,
                            },
                            "affiliations": None,
                        },
                        {
                            "person_or_org": {
                                "name": "Jane Doe",
                                "type": "personal",
                                "given_name": "Jane",
                                "family_name": "Doe",
                                "identifiers": [
                                    {"identifier": "https://orcid.org/0000-0002-1584-4316", "scheme": "orcid"}
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
                            "funder": {"id": "039qvmf95", "name": "Wallenberg Wood Science Center"},
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
