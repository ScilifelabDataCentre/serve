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
                    "language": "en",
                    "creators": [
                        {
                            "name": "Mock Creator",
                            "lastName": "User",
                            "affiliation": "Mock University",
                            "orcid": "0000-0000-0000-0000",
                        }
                    ],
                    "tags": ["mock", "test"],
                    "funding_sources_json": [{"funder_name": "Mock Funder", "award_number": "1234"}],
                },
                "pids": {"doi": {"identifier": "10.1234/mockdoi"}},
            }
        return {}
