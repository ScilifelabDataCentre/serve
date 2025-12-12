"""
Tests that verify the example code works correctly.
These tests mock the API calls to avoid external dependencies.
"""
import json

import pytest
import responses

from invenio_client import InvenioClient, transform_to_invenio_metadata


class TestExampleWorkflow:
    """Test the workflow from examples_invenio_clients.py."""

    @responses.activate
    def test_phase_1_create_and_publish(self, invenio_client):
        """Test Phase 1: Create and publish initial record."""
        base_url = "https://invenio.example.com"

        # Mock create draft
        create_url = f"{base_url}/api/records"
        draft_data = {
            "id": "draft-1",
            "metadata": {"title": "Test Draft"},
            "access": {"record": "public", "files": "public"},
            "files": {"enabled": False},
        }
        responses.add(responses.POST, create_url, json=draft_data, status=201)

        # Mock publish draft
        publish_url = f"{base_url}/api/records/draft-1/draft/actions/publish"
        published_data = {"id": "published-1", "metadata": {"title": "Published Record"}, "versions": {"index": 1}}
        responses.add(responses.POST, publish_url, json=published_data, status=202)

        # Execute Phase 1
        metadata = {"title": "Test Draft", "resource_type": {"id": "dataset"}}
        access = {"record": "public", "files": "public"}
        files = {"enabled": False}

        # Create draft
        draft = invenio_client.create_draft(metadata=metadata, access=access, files=files)
        assert draft["id"] == "draft-1"

        # Publish draft
        published = invenio_client.publish_draft(draft["id"])
        assert published["id"] == "published-1"

        # Verify API calls
        assert len(responses.calls) == 2
        assert responses.calls[0].request.url == create_url
        assert responses.calls[1].request.url == publish_url

    @responses.activate
    def test_phase_3_edit_current_version(self, invenio_client):
        """Test Phase 3: Edit current version."""
        base_url = "https://invenio.example.com"
        record_id = "published-1"

        # Mock edit published record
        edit_url = f"{base_url}/api/records/{record_id}/draft"
        draft_data = {
            "id": "draft-2",
            "metadata": {"title": "Draft from Published"},
            "access": {"record": "public", "files": "public"},
            "files": {"enabled": False},
            "custom_fields": {"test": "value"},
            "pids": {},
        }
        responses.add(responses.POST, edit_url, json=draft_data, status=201)

        # Mock get draft
        get_draft_url = f"{base_url}/api/records/draft-2/draft"
        responses.add(responses.GET, get_draft_url, json=draft_data, status=200)

        # Mock update draft
        update_url = f"{base_url}/api/records/draft-2/draft"
        updated_draft = {
            "id": "draft-2",
            "metadata": {"title": "Updated Draft"},
            "access": {"record": "public", "files": "public"},
            "files": {"enabled": False},
            "custom_fields": {"test": "value"},
            "pids": {},
        }
        responses.add(responses.PUT, update_url, json=updated_draft, status=200)

        # Mock publish updated draft
        publish_url = f"{base_url}/api/records/draft-2/draft/actions/publish"
        published_update = {
            "id": "published-updated",
            "metadata": {"title": "Published Updated"},
            "versions": {"index": 1},
        }
        responses.add(responses.POST, publish_url, json=published_update, status=202)

        # Execute Phase 3
        # 1. Edit published record
        draft = invenio_client.edit_published_record(record_id)
        assert draft["id"] == "draft-2"

        # 2. Get current draft
        current_draft = invenio_client.get_draft(draft["id"])

        # 3. Update draft
        updated = invenio_client.update_draft(
            record_id=draft["id"],
            metadata={"title": "Updated Draft"},
            access=current_draft.get("access"),
            files={"enabled": False},
            custom_fields=current_draft.get("custom_fields"),
            pids=current_draft.get("pids", {}),
        )
        assert updated["metadata"]["title"] == "Updated Draft"

        # 4. Publish updated draft
        published = invenio_client.publish_draft(updated["id"])
        assert published["id"] == "published-updated"

        # Verify API calls
        assert len(responses.calls) == 4

    @responses.activate
    def test_phase_5_version_management(self, invenio_client):
        """Test Phase 5: Version management."""
        base_url = "https://invenio.example.com"
        old_version_id = "v1"
        new_version_id = "v2"

        # Mock get all versions from new version ID
        versions_url_new = f"{base_url}/api/records/{new_version_id}/versions"
        versions_response = {
            "hits": {
                "total": 2,
                "hits": [
                    {"id": "v1", "metadata": {"title": "Version 1"}, "versions": {"index": 1}},
                    {"id": "v2", "metadata": {"title": "Version 2"}, "versions": {"index": 2}},
                ],
            }
        }
        responses.add(responses.GET, versions_url_new, json=versions_response, status=200)

        # Mock get all versions from old version ID
        versions_url_old = f"{base_url}/api/records/{old_version_id}/versions"
        responses.add(responses.GET, versions_url_old, json=versions_response, status=200)

        # Mock get latest version
        latest_url = f"{base_url}/api/records/{old_version_id}/versions/latest"
        latest_response = {"id": "v2", "metadata": {"title": "Version 2"}, "versions": {"index": 2, "is_latest": True}}
        responses.add(responses.GET, latest_url, json=latest_response, status=200)

        # Mock get individual records to check parent relationships
        responses.add(
            responses.GET,
            f"{base_url}/api/records/{old_version_id}",
            json={"id": "v1", "parent": {"id": "parent-123"}, "versions": {"index": 1}},
            status=200,
        )

        responses.add(
            responses.GET,
            f"{base_url}/api/records/{new_version_id}",
            json={"id": "v2", "parent": {"id": "parent-123"}, "versions": {"index": 2}},
            status=200,
        )

        # Execute Phase 5
        # Get all versions from new ID
        all_versions_new = invenio_client.get_all_versions(new_version_id)
        assert all_versions_new["hits"]["total"] == 2

        # Get all versions from old ID
        all_versions_old = invenio_client.get_all_versions(old_version_id)
        assert all_versions_old["hits"]["total"] == 2

        # Get latest version
        latest = invenio_client.get_latest_version(old_version_id)
        assert latest["id"] == "v2"
        assert latest["versions"]["index"] == 2

        # Check parent relationships
        original = invenio_client.get_record(old_version_id)
        new_version = invenio_client.get_record(new_version_id)

        assert original["parent"]["id"] == "parent-123"
        assert new_version["parent"]["id"] == "parent-123"
        assert original["parent"]["id"] == new_version["parent"]["id"]


def test_transform_example_schema_org():
    """Test the transformation with the exact schema from the example."""
    schema_org_data = {
        "@context": "https://schema.org",
        "@type": "Dataset",
        "name": "Application Deployment Metadata",
        "description": "Structured metadata for applications, users, and projects deployed on the SciLifeLab Serve platform.",
        "dateCreated": "2025-12-11T10:53:26.264196+00:00",
        "creator": {"@type": "Organization", "name": "SciLifeLab Data Centre", "url": "https://www.scilifelab.se/data"},
        "hasPart": [
            {
                "@type": "SoftwareApplication",
                "name": "test",
                "description": "desc",
                "url": "https://test.example.com",
                "softwareVersion": "1.0.0",
                "applicationCategory": "Cloud Application",
                "operatingSystem": "Kubernetes",
                "additionalProperty": [{"name": "cpuRequest", "value": "100m"}, {"name": "cpuLimit", "value": "2000m"}],
                "hasPart": {"@type": "SoftwareSourceCode", "codeRepository": "https://source.org"},
            }
        ],
        "about": {
            "@type": "Project",
            "name": "test",
            "description": "",
            "additionalProperty": [{"name": "minio", "value": "1"}, {"name": "mlflow", "value": "1"}],
        },
    }

    result = transform_to_invenio_metadata(schema_org_data)

    # Verify title includes both names
    title = result["metadata"]["title"]
    assert "Application Deployment Metadata" in title
    assert "test" in title

    # Verify description
    assert (
        result["metadata"]["description"]
        == "Structured metadata for applications, users, and projects deployed on the SciLifeLab Serve platform."
    )

    # Verify publication date extraction
    assert result["metadata"]["publication_date"] == "2025-12-11"

    # Verify creator
    assert result["metadata"]["creators"][0]["person_or_org"]["name"] == "SciLifeLab Data Centre"

    # Verify custom fields
    assert "custom_fields" in result["metadata"]
    custom_fields = result["metadata"]["custom_fields"]

    # Verify application deployment structure
    assert "kcr:application_deployment" in custom_fields
    deployment = custom_fields["kcr:application_deployment"]

    # Verify resource requirements
    assert deployment["resource_requirements"]["cpuRequest"] == "100m"
    assert deployment["resource_requirements"]["cpuLimit"] == "2000m"

    # Verify project metadata
    assert deployment["project_metadata"]["services"]["minio"] == "1"
    assert deployment["project_metadata"]["services"]["mlflow"] == "1"
