"""
Pytest configuration and fixtures for Invenio client tests.
"""
import json
from unittest.mock import Mock, patch

import pytest
import responses  # type: ignore

from doi_minting.clients.invenio_client.invenio_client import InvenioClient


@pytest.fixture
def base_url():
    return "https://invenio.example.com"


@pytest.fixture
def token():
    return "test-token-12345"


@pytest.fixture
def invenio_client(base_url, token):
    """Create an InvenioClient instance for testing."""
    return InvenioClient(
        base_url=base_url, token=token, auth_scheme="Bearer", verify=False  # Disable SSL verification for tests
    )


@pytest.fixture
def sample_schema_org_data():
    """Sample Schema.org data for testing."""
    return {
        "@context": "https://schema.org",
        "@type": "Dataset",
        "name": "Test Dataset",
        "description": "Test description",
        "dateCreated": "2025-12-11T10:53:26.264196+00:00",
        "creator": {"@type": "Organization", "name": "Test Org"},
        "hasPart": [
            {
                "@type": "SoftwareApplication",
                "name": "Test App",
                "description": "App description",
                "softwareVersion": "1.0.0",
                "url": "https://example.com",
                "applicationCategory": "Cloud Application",
                "operatingSystem": "Kubernetes",
                "additionalProperty": [
                    {"name": "cpuRequest", "value": "100m"},
                    {"name": "memoryRequest", "value": "1Gi"},
                ],
                "hasPart": {"@type": "SoftwareSourceCode", "codeRepository": "https://github.com/test"},
            }
        ],
        "about": {
            "@type": "Project",
            "name": "Test Project",
            "description": "Project description",
            "additionalProperty": [{"name": "service1", "value": "2"}, {"name": "service2", "value": "3"}],
        },
    }


@pytest.fixture
def sample_record_data():
    """Sample record data returned by the API."""
    return {
        "id": "abc123",
        "metadata": {
            "title": "Test Record",
            "description": "Test description",
            "publication_date": "2025-12-11",
            "resource_type": {"id": "dataset"},
        },
        "access": {"record": "public", "files": "public"},
        "files": {"enabled": False},
        "versions": {"index": 1, "is_latest": True},
    }


@pytest.fixture
def sample_draft_data():
    """Sample draft record data."""
    return {
        "id": "draft-123",
        "metadata": {"title": "Draft Record", "description": "Draft description"},
        "links": {"self": "/api/records/draft-123/draft", "publish": "/api/records/draft-123/draft/actions/publish"},
    }


@pytest.fixture
def sample_search_results():
    """Sample search results."""
    return {
        "hits": {
            "total": 2,
            "hits": [
                {"id": "record-1", "metadata": {"title": "Record 1"}},
                {"id": "record-2", "metadata": {"title": "Record 2"}},
            ],
        },
        "links": {"self": "/api/records?page=1"},
    }


@pytest.fixture
def mock_response():
    """Create a mock response object."""
    response = Mock()
    response.status_code = 200
    response.json.return_value = {"status": "success"}
    response.text = '{"status": "success"}'
    return response
