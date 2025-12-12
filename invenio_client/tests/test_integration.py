"""
Integration tests for the complete workflow.
"""
import json

import pytest
import responses

from invenio_client import InvenioClient, transform_to_invenio_metadata


@responses.activate
def test_complete_workflow(invenio_client, sample_schema_org_data):
    """
    Test a complete workflow similar to the example in examples_invenio_clients.py
    """
    # Mock all the API endpoints
    base_url = "https://invenio.example.com"

    # 1. Create draft
    create_url = f"{base_url}/api/records"
    draft_response = {
        "id": "draft-123",
        "metadata": {"title": "Initial Draft"},
        "links": {"self": f"{base_url}/api/records/draft-123/draft"},
    }
    responses.add(responses.POST, create_url, json=draft_response, status=201)

    # 2. Publish draft
    publish_url = f"{base_url}/api/records/draft-123/draft/actions/publish"
    published_response = {"id": "published-123", "metadata": {"title": "Published Record"}, "versions": {"index": 1}}
    responses.add(responses.POST, publish_url, json=published_response, status=202)

    # 3. Search records
    search_url = f"{base_url}/api/records"
    search_response = {"hits": {"total": 1, "hits": [{"id": "published-123"}]}}
    responses.add(responses.GET, search_url, json=search_response, status=200)

    # 4. Edit published record (create draft)
    edit_url = f"{base_url}/api/records/published-123/draft"
    edit_draft_response = {"id": "draft-from-published-123", "metadata": {"title": "Draft from Published"}}
    responses.add(responses.POST, edit_url, json=edit_draft_response, status=201)

    # 5. Get draft (to see current state)
    get_draft_url = f"{base_url}/api/records/draft-from-published-123/draft"
    current_draft_response = {
        "id": "draft-from-published-123",
        "metadata": {"title": "Draft from Published"},
        "access": {"record": "public", "files": "public"},
        "files": {"enabled": False},
        "custom_fields": {"test": "value"},
        "pids": {},
    }
    responses.add(responses.GET, get_draft_url, json=current_draft_response, status=200)

    # 6. Update draft
    update_draft_url = f"{base_url}/api/records/draft-from-published-123/draft"
    updated_draft_response = {"id": "draft-from-published-123", "metadata": {"title": "Updated Draft Title"}}
    responses.add(responses.PUT, update_draft_url, json=updated_draft_response, status=200)

    # 7. Publish updated draft
    publish_updated_url = f"{base_url}/api/records/draft-from-published-123/draft/actions/publish"
    published_updated_response = {
        "id": "published-updated-123",
        "metadata": {"title": "Updated Published Record"},
        "versions": {"index": 1},
    }
    responses.add(responses.POST, publish_updated_url, json=published_updated_response, status=202)

    # 8. Create new version
    new_version_url = f"{base_url}/api/records/published-updated-123/versions"
    new_version_response = {"id": "new-version-draft-123", "metadata": {"title": "New Version Draft"}}
    responses.add(responses.POST, new_version_url, json=new_version_response, status=201)

    # 9. Get new version draft
    get_new_version_url = f"{base_url}/api/records/new-version-draft-123/draft"
    new_version_draft_response = {
        "id": "new-version-draft-123",
        "metadata": {"title": "New Version Draft"},
        "access": {"record": "public", "files": "public"},
        "files": {"enabled": False},
        "custom_fields": {"test": "value"},
        "pids": {},
    }
    responses.add(responses.GET, get_new_version_url, json=new_version_draft_response, status=200)

    # 10. Update new version draft
    update_new_version_url = f"{base_url}/api/records/new-version-draft-123/draft"
    updated_new_version_response = {"id": "new-version-draft-123", "metadata": {"title": "New Version Draft - Updated"}}
    responses.add(responses.PUT, update_new_version_url, json=updated_new_version_response, status=200)

    # 11. Publish new version
    publish_new_version_url = f"{base_url}/api/records/new-version-draft-123/draft/actions/publish"
    published_new_version_response = {
        "id": "published-new-version-123",
        "metadata": {"title": "Published New Version"},
        "versions": {"index": 2},
    }
    responses.add(responses.POST, publish_new_version_url, json=published_new_version_response, status=202)

    # 12. Get all versions
    versions_url = f"{base_url}/api/records/published-updated-123/versions"
    versions_response = {
        "hits": {
            "total": 2,
            "hits": [
                {"id": "published-updated-123", "versions": {"index": 1}},
                {"id": "published-new-version-123", "versions": {"index": 2}},
            ],
        }
    }
    responses.add(responses.GET, versions_url, json=versions_response, status=200)

    # 13. Get latest version
    latest_version_url = f"{base_url}/api/records/published-updated-123/versions/latest"
    latest_version_response = {"id": "published-new-version-123", "versions": {"index": 2, "is_latest": True}}
    responses.add(responses.GET, latest_version_url, json=latest_version_response, status=200)

    # Transform metadata
    invenio_data = transform_to_invenio_metadata(sample_schema_org_data)
    metadata = invenio_data["metadata"]
    access = invenio_data.get("access")
    files = invenio_data.get("files")
    custom_fields = metadata.pop("custom_fields", None)

    # Execute the workflow
    # 1. Create draft
    draft = invenio_client.create_draft(metadata=metadata, access=access, files=files, custom_fields=custom_fields)
    assert draft["id"] == "draft-123"

    # 2. Publish draft
    published = invenio_client.publish_draft(draft["id"])
    assert published["id"] == "published-123"

    # 3. Search
    search_results = invenio_client.search_records(query="test")
    assert search_results["hits"]["total"] == 1

    # 4. Edit published record
    edit_draft = invenio_client.edit_published_record(published["id"])
    assert edit_draft["id"] == "draft-from-published-123"

    # 5. Update draft
    updated_draft = invenio_client.update_draft(record_id=edit_draft["id"], metadata={"title": "Updated Draft Title"})
    assert updated_draft["metadata"]["title"] == "Updated Draft Title"

    # 6. Publish updated draft
    published_updated = invenio_client.publish_draft(updated_draft["id"])
    assert published_updated["id"] == "published-updated-123"

    # 7. Create new version
    new_version = invenio_client.create_new_version(published_updated["id"])
    assert new_version["id"] == "new-version-draft-123"

    # 8. Update new version
    updated_new_version = invenio_client.update_draft(
        record_id=new_version["id"], metadata={"title": "New Version Draft - Updated"}
    )
    assert updated_new_version["metadata"]["title"] == "New Version Draft - Updated"

    # 9. Publish new version
    published_new_version = invenio_client.publish_draft(updated_new_version["id"])
    assert published_new_version["id"] == "published-new-version-123"

    # 10. Get all versions
    all_versions = invenio_client.get_all_versions(published_updated["id"])
    assert all_versions["hits"]["total"] == 2

    # 11. Get latest version
    latest_version = invenio_client.get_latest_version(published_updated["id"])
    assert latest_version["id"] == "published-new-version-123"
    assert latest_version["versions"]["index"] == 2


def test_metadata_transformation_integration(sample_schema_org_data):
    """Test the metadata transformation with real data."""
    result = transform_to_invenio_metadata(sample_schema_org_data)

    # Verify the transformation produced valid structure
    assert isinstance(result, dict)
    assert "metadata" in result
    assert "access" in result
    assert "files" in result

    metadata = result["metadata"]

    # Verify required fields
    required_fields = [
        "title",
        "description",
        "publication_date",
        "publisher",
        "resource_type",
        "creators",
        "rights",
        "additional_descriptions",
        "subjects",
    ]
    for field in required_fields:
        assert field in metadata, f"Missing required field: {field}"

    # Verify custom fields structure
    assert "custom_fields" in metadata
    assert "kcr:application_deployment" in metadata["custom_fields"]
