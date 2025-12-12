"""
Tests for the main InvenioClient class.
"""
import pytest
import json
from unittest.mock import Mock, patch, call
import responses
from invenio_client import InvenioClient, InvenioClientError, transform_to_invenio_metadata


class TestInvenioClientInitialization:
    """Test InvenioClient initialization and configuration."""
    
    def test_client_initialization(self, base_url, token):
        """Test basic client initialization."""
        client = InvenioClient(base_url=base_url, token=token)
        
        assert client.base_url == base_url
        assert client.token == token
        assert client.auth_scheme == "Bearer"
        assert client.timeout == (3.05, 20.0)
        assert client.session is not None
        
    def test_client_with_auth_scheme(self, base_url, token):
        """Test client with different authentication schemes."""
        # Test with Token scheme
        client = InvenioClient(base_url=base_url, token=token, auth_scheme="Token")
        assert client.auth_scheme == "Token"
        assert client.session.headers["Authorization"] == f"Token {token}"
        
        # Test with Bearer scheme
        client = InvenioClient(base_url=base_url, token=token, auth_scheme="Bearer")
        assert client.auth_scheme == "Bearer"
        assert client.session.headers["Authorization"] == f"Bearer {token}"
    
    def test_client_with_custom_timeout(self, base_url, token):
        """Test client with custom timeout."""
        client = InvenioClient(
            base_url=base_url,
            token=token,
            timeout=(5.0, 30.0)
        )
        
        assert client.timeout == (5.0, 30.0)
    
    def test_client_url_building(self, invenio_client):
        """Test URL building method."""
        # Test with endpoint starting with slash
        url = invenio_client._build_url("/api/records")
        assert url == "https://invenio.example.com/api/records"
        
        # Test with endpoint without slash
        url = invenio_client._build_url("api/records")
        assert url == "https://invenio.example.com/api/records"
        
        # Test with nested endpoint
        url = invenio_client._build_url("/api/records/123/draft")
        assert url == "https://invenio.example.com/api/records/123/draft"


class TestResponseHandling:
    """Test response handling methods."""
    
    def test_handle_response_success(self, invenio_client):
        """Test successful response handling."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": "test"}
        
        result = invenio_client._handle_response(mock_response)
        assert result == {"data": "test"}
    
    def test_handle_response_204_no_content(self, invenio_client):
        """Test handling 204 No Content response."""
        mock_response = Mock()
        mock_response.status_code = 204
        
        result = invenio_client._handle_response(mock_response)
        assert result == {}
    
    def test_handle_response_error_with_message(self, invenio_client):
        """Test error response with message field."""
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.json.return_value = {
            "message": "Validation error",
            "errors": [{"field": "title", "message": "Required"}]
        }
        mock_response.text = json.dumps(mock_response.json.return_value)
        
        with pytest.raises(InvenioClientError) as exc_info:
            invenio_client._handle_response(mock_response)
        
        assert "Validation error" in str(exc_info.value)
        assert "Errors:" in str(exc_info.value)
    
    def test_handle_response_error_no_json(self, invenio_client):
        """Test error response that's not JSON."""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.json.side_effect = json.JSONDecodeError("Error", "", 0)
        mock_response.text = "Internal Server Error"
        
        with pytest.raises(InvenioClientError) as exc_info:
            invenio_client._handle_response(mock_response)
        
        assert "500" in str(exc_info.value)
        assert "Internal Server Error" in str(exc_info.value)
    
    def test_handle_response_custom_success_codes(self, invenio_client):
        """Test response handling with custom success codes."""
        mock_response = Mock()
        mock_response.status_code = 202  # Accepted
        mock_response.json.return_value = {"status": "processing"}
        
        result = invenio_client._handle_response(mock_response, success_codes=[200, 202])
        assert result == {"status": "processing"}
        
        # Test with failure when code not in success codes
        mock_response.status_code = 400
        with pytest.raises(InvenioClientError):
            invenio_client._handle_response(mock_response, success_codes=[200, 202])


class TestDraftOperations:
    """Test draft record operations."""
    
    @responses.activate
    def test_create_draft(self, invenio_client):
        """Test creating a draft record."""
        url = "https://invenio.example.com/api/records"
        expected_response = {
            "id": "draft-123",
            "metadata": {"title": "Test Draft"}
        }
        
        responses.add(
            responses.POST,
            url,
            json=expected_response,
            status=201
        )
        
        metadata = {"title": "Test Draft"}
        result = invenio_client.create_draft(metadata=metadata)
        
        assert result == expected_response
        
        # Check request
        request = responses.calls[0].request
        assert request.headers["Content-Type"] == "application/json"
        assert request.headers["Authorization"] == "Bearer test-token-12345"
        
        request_body = json.loads(request.body)
        assert request_body["metadata"] == metadata
        assert request_body["access"]["record"] == "public"
        assert request_body["files"]["enabled"] is False
    
    @responses.activate
    def test_create_draft_with_custom_fields(self, invenio_client):
        """Test creating a draft with custom fields and PIDs."""
        url = "https://invenio.example.com/api/records"
        expected_response = {"id": "draft-456"}
        
        responses.add(
            responses.POST,
            url,
            json=expected_response,
            status=201
        )
        
        metadata = {"title": "Test"}
        custom_fields = {"custom": "value"}
        pids = {"doi": {"identifier": "10.1234/test", "provider": "external"}}
        
        result = invenio_client.create_draft(
            metadata=metadata,
            custom_fields=custom_fields,
            pids=pids
        )
        
        assert result == expected_response
        
        request_body = json.loads(responses.calls[0].request.body)
        assert request_body["custom_fields"] == custom_fields
        assert request_body["pids"] == pids
    
    @responses.activate
    def test_get_draft(self, invenio_client):
        """Test getting a draft record."""
        record_id = "draft-123"
        url = f"https://invenio.example.com/api/records/{record_id}/draft"
        expected_response = {
            "id": record_id,
            "metadata": {"title": "Draft Title"}
        }
        
        responses.add(
            responses.GET,
            url,
            json=expected_response,
            status=200
        )
        
        result = invenio_client.get_draft(record_id)
        assert result == expected_response
    
    @responses.activate
    def test_update_draft(self, invenio_client):
        """Test updating a draft record."""
        record_id = "draft-123"
        url = f"https://invenio.example.com/api/records/{record_id}/draft"
        expected_response = {
            "id": record_id,
            "metadata": {"title": "Updated Title"}
        }
        
        responses.add(
            responses.PUT,
            url,
            json=expected_response,
            status=200
        )
        
        metadata = {"title": "Updated Title"}
        result = invenio_client.update_draft(record_id, metadata=metadata)
        
        assert result == expected_response
        
        request_body = json.loads(responses.calls[0].request.body)
        assert request_body["metadata"] == metadata
    
    @responses.activate
    def test_publish_draft(self, invenio_client):
        """Test publishing a draft record."""
        record_id = "draft-123"
        url = f"https://invenio.example.com/api/records/{record_id}/draft/actions/publish"
        expected_response = {
            "id": "published-123",
            "metadata": {"title": "Published Title"}
        }
        
        responses.add(
            responses.POST,
            url,
            json=expected_response,
            status=202
        )
        
        result = invenio_client.publish_draft(record_id)
        assert result == expected_response
    
    @responses.activate
    def test_delete_draft(self, invenio_client):
        """Test deleting a draft record."""
        record_id = "draft-123"
        url = f"https://invenio.example.com/api/records/{record_id}/draft"
        
        responses.add(
            responses.DELETE,
            url,
            status=204
        )
        
        result = invenio_client.delete_draft(record_id)
        assert result is True


class TestPublishedRecordOperations:
    """Test published record operations."""
    
    @responses.activate
    def test_get_record(self, invenio_client):
        """Test getting a published record."""
        record_id = "published-123"
        url = f"https://invenio.example.com/api/records/{record_id}"
        expected_response = {
            "id": record_id,
            "metadata": {"title": "Published Record"}
        }
        
        responses.add(
            responses.GET,
            url,
            json=expected_response,
            status=200
        )
        
        result = invenio_client.get_record(record_id)
        assert result == expected_response
    
    @responses.activate
    def test_search_records(self, invenio_client):
        """Test searching published records."""
        url = "https://invenio.example.com/api/records"
        expected_response = {
            "hits": {
                "total": 2,
                "hits": [
                    {"id": "1", "metadata": {"title": "Record 1"}},
                    {"id": "2", "metadata": {"title": "Record 2"}}
                ]
            }
        }
        
        responses.add(
            responses.GET,
            url,
            json=expected_response,
            status=200
        )
        
        result = invenio_client.search_records(
            query="test",
            sort="newest",
            size=10,
            page=1,
            allversions=False
        )
        
        assert result == expected_response
        
        # Check query parameters
        request = responses.calls[0].request
        assert "q=test" in request.url
        assert "sort=newest" in request.url
        assert "size=10" in request.url
        assert "page=1" in request.url
        assert "allversions=false" in request.url
    
    @responses.activate
    def test_edit_published_record(self, invenio_client):
        """Test creating a draft from a published record."""
        record_id = "published-123"
        url = f"https://invenio.example.com/api/records/{record_id}/draft"
        expected_response = {
            "id": "draft-from-published-123",
            "metadata": {"title": "Draft from Published"}
        }
        
        responses.add(
            responses.POST,
            url,
            json=expected_response,
            status=201
        )
        
        result = invenio_client.edit_published_record(record_id)
        assert result == expected_response


class TestUserRecords:
    """Test user record operations."""
    
    @responses.activate
    def test_list_user_records(self, invenio_client):
        """Test listing user's records."""
        url = "https://invenio.example.com/api/user/records"
        expected_response = {
            "hits": {
                "total": 5,
                "hits": [
                    {"id": "user-record-1", "metadata": {"title": "User Record 1"}}
                ]
            }
        }
        
        responses.add(
            responses.GET,
            url,
            json=expected_response,
            status=200
        )
        
        result = invenio_client.list_user_records(
            query="user query",
            sort="oldest",
            size=5,
            page=2
        )
        
        assert result == expected_response
        
        request = responses.calls[0].request
        assert "q=user+query" in request.url
        assert "sort=oldest" in request.url
        assert "size=5" in request.url
        assert "page=2" in request.url


class TestVersionManagement:
    """Test version management operations."""
    
    @responses.activate
    def test_create_new_version(self, invenio_client):
        """Test creating a new version of a record."""
        record_id = "record-123"
        url = f"https://invenio.example.com/api/records/{record_id}/versions"
        expected_response = {
            "id": "new-version-123",
            "metadata": {"title": "New Version"}
        }
        
        responses.add(
            responses.POST,
            url,
            json=expected_response,
            status=201
        )
        
        result = invenio_client.create_new_version(record_id)
        assert result == expected_response
    
    @responses.activate
    def test_get_all_versions(self, invenio_client):
        """Test getting all versions of a record."""
        record_id = "record-123"
        url = f"https://invenio.example.com/api/records/{record_id}/versions"
        expected_response = {
            "hits": {
                "total": 3,
                "hits": [
                    {"id": "v1", "versions": {"index": 1}},
                    {"id": "v2", "versions": {"index": 2}},
                    {"id": "v3", "versions": {"index": 3}}
                ]
            }
        }
        
        responses.add(
            responses.GET,
            url,
            json=expected_response,
            status=200
        )
        
        result = invenio_client.get_all_versions(record_id)
        assert result == expected_response
    
    @responses.activate
    def test_get_latest_version(self, invenio_client):
        """Test getting the latest version of a record."""
        record_id = "record-123"
        url = f"https://invenio.example.com/api/records/{record_id}/versions/latest"
        expected_response = {
            "id": "latest-version",
            "versions": {"index": 3, "is_latest": True}
        }
        
        responses.add(
            responses.GET,
            url,
            json=expected_response,
            status=200
        )
        
        result = invenio_client.get_latest_version(record_id)
        assert result == expected_response


class TestDOIManagement:
    """Test DOI management operations."""
    
    @responses.activate
    def test_reserve_doi(self, invenio_client):
        """Test reserving a DOI for a draft record."""
        record_id = "draft-123"
        url = f"https://invenio.example.com/api/records/{record_id}/draft/pids/doi"
        expected_response = {
            "doi": "10.1234/test.doi",
            "status": "reserved"
        }
        
        responses.add(
            responses.POST,
            url,
            json=expected_response,
            status=201
        )
        
        result = invenio_client.reserve_doi(record_id)
        assert result == expected_response
    
    @responses.activate
    def test_delete_doi(self, invenio_client):
        """Test deleting a DOI from a draft record."""
        record_id = "draft-123"
        url = f"https://invenio.example.com/api/records/{record_id}/draft/pids/doi"
        
        responses.add(
            responses.DELETE,
            url,
            status=204
        )
        
        result = invenio_client.delete_doi(record_id)
        assert result is True

'''
class TestMetadataTransformation:
    """Test metadata transformation functions."""
    
    def test_transform_to_invenio_metadata_basic(self, sample_schema_org_data):
        """Test basic metadata transformation."""
        result = transform_to_invenio_metadata(sample_schema_org_data)
        
        # Check basic structure
        assert "access" in result
        assert "files" in result
        assert "metadata" in result
        
        # Check metadata fields
        metadata = result["metadata"]
        assert metadata["title"] == "Serve Test Dataset of the App: 'Test App'"
        assert metadata["description"] == "Test description"
        assert metadata["publication_date"] == "2025-12-11"  # Only date part
        assert metadata["publisher"] == "Test Org"
        assert metadata["resource_type"]["id"] == "dataset"
        
        # Check creators
        assert len(metadata["creators"]) == 1
        assert metadata["creators"][0]["person_or_org"]["name"] == "Test Org"
        assert metadata["creators"][0]["person_or_org"]["type"] == "organizational"
        
        # Check license
        assert len(metadata["rights"]) == 1
        assert metadata["rights"][0]["id"] == "cc-by-4.0"
    
    def test_transform_to_invenio_metadata_custom_fields(self, sample_schema_org_data):
        """Test that custom fields are properly included."""
        result = transform_to_invenio_metadata(sample_schema_org_data)
        metadata = result["metadata"]
        
        # Check custom fields exist
        assert "custom_fields" in metadata
        custom_fields = metadata["custom_fields"]
        
        # Check application deployment structure
        assert "kcr:application_deployment" in custom_fields
        deployment = custom_fields["kcr:application_deployment"]
        
        # Check software application data
        assert "software_application" in deployment
        app = deployment["software_application"]
        assert app["name"] == "Test App"
        assert app["description"] == "App description"
        assert app["version"] == "1.0.0"
        assert app["url"] == "https://example.com"
        assert app["application_category"] == "Cloud Application"
        assert app["operating_system"] == "Kubernetes"
        assert app["code_repository"] == "https://github.com/test"
        
        # Check resource requirements
        assert "resource_requirements" in deployment
        resources = deployment["resource_requirements"]
        assert resources["cpuRequest"] == "100m"
        assert resources["memoryRequest"] == "1Gi"
        
        # Check project metadata
        assert "project_metadata" in deployment
        project = deployment["project_metadata"]
        assert project["project_name"] == "Test Project"
        assert project["project_description"] == "Project description"
        assert project["services"]["service1"] == "2"
        assert project["services"]["service2"] == "3"
    
    def test_transform_to_invenio_metadata_missing_fields(self):
        """Test transformation with minimal data."""
        minimal_data = {
            "@context": "https://schema.org",
            "@type": "Dataset",
            "name": "Minimal Dataset",
            "description": "Minimal description",
            "dateCreated": "2025-01-01T00:00:00Z",
            "creator": {"@type": "Organization", "name": "Test Org"}
        }
        
        result = transform_to_invenio_metadata(minimal_data)
        metadata = result["metadata"]
        
        # Should still have all required fields
        assert metadata["title"] == "Serve Minimal Dataset of the App: ''"
        assert metadata["description"] == "Minimal description"
        assert metadata["publication_date"] == "2025-01-01"
        assert metadata["publisher"] == "Test Org"
        
        # Custom fields should not exist without hasPart
        assert "custom_fields" not in metadata
'''

def test_invenio_client_error():
    """Test InvenioClientError exception."""
    error = InvenioClientError("Test error message")
    assert str(error) == "Test error message"