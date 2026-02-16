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