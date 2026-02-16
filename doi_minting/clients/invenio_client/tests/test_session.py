"""
Tests for invenio_client.session.py module.
"""
from unittest.mock import Mock, patch

import pytest
import requests

from doi_minting.clients.invenio_client.session import make_session


def test_make_session_default_headers():
    """Test creating session with default headers."""
    session = make_session()

    assert isinstance(session, requests.Session)
    assert session.headers["Accept"] == "application/json"
    assert "User-Agent" in session.headers
    assert "Authorization" not in session.headers


def test_make_session_with_custom_headers():
    """Test creating session with custom headers."""
    custom_headers = {"Accept": "application/xml", "X-Custom-Header": "test"}

    session = make_session(default_headers=custom_headers)

    # Custom headers should override defaults
    assert session.headers["Accept"] == "application/xml"
    assert session.headers["X-Custom-Header"] == "test"


def test_make_session_with_token():
    """Test creating session with token authentication."""
    session = make_session(token="test-token-123")

    assert session.headers["Authorization"] == "Token test-token-123"


def test_make_session_with_retries():
    """Test that retry configuration is properly set."""
    session = make_session(total_retries=5)

    # Check that adapters are mounted
    assert "https://" in session.adapters
    assert "http://" in session.adapters

    # Get the adapter
    adapter = session.adapters["https://"]
    assert adapter.max_retries.total == 5
    assert 500 in adapter.max_retries.status_forcelist


def test_make_session_verify_ssl():
    """Test SSL verification configuration."""
    # Test with verify=True
    session = make_session(verify=True)
    assert session.verify is True

    # Test with verify=False
    session = make_session(verify=False)
    assert session.verify is False

    # Test with custom CA bundle
    session = make_session(verify="/path/to/cert.pem")
    assert session.verify == "/path/to/cert.pem"


def test_make_session_allowed_methods():
    """Test that allowed methods are properly configured."""
    session = make_session()
    adapter = session.adapters["https://"]
    retry = adapter.max_retries

    expected_methods = {"HEAD", "GET", "PUT", "DELETE", "OPTIONS", "TRACE", "POST"}
    assert set(retry.allowed_methods) == expected_methods


def test_make_session_backoff_factor():
    """Test backoff factor configuration."""
    session = make_session()
    adapter = session.adapters["https://"]
    retry = adapter.max_retries

    assert retry.backoff_factor == 0.5


def test_make_session_mounts_adapters():
    """Test that adapters are mounted on both HTTP and HTTPS."""
    # Don't mock the entire session, create a real session and check adapters
    session = make_session()

    # Check that adapters are mounted
    assert "https://" in session.adapters
    assert "http://" in session.adapters

    # Check that the adapters have retry configuration
    https_adapter = session.adapters["https://"]
    http_adapter = session.adapters["http://"]

    # Both should be the same adapter instance
    assert https_adapter is http_adapter

    # Check retry configuration
    assert https_adapter.max_retries.total == 3  # default
    assert https_adapter.max_retries.backoff_factor == 0.5


def test_make_session_with_custom_retries():
    """Test session with custom retry count."""
    session = make_session(total_retries=7)

    adapter = session.adapters["https://"]
    assert adapter.max_retries.total == 7
    assert adapter.max_retries.connect == 7
    assert adapter.max_retries.read == 7
