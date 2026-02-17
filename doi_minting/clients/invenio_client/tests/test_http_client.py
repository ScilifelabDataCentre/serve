"""
Tests for invenio_client.http_client.py module.
"""
from unittest.mock import MagicMock, Mock, patch

import pytest
import requests

from doi_minting.clients.invenio_client.http_client import (
    _request,
    delete,
    get,
    post,
    put,
)


@pytest.fixture
def mock_session():
    """Create a mock session."""
    session = Mock()
    session.headers = {"Accept": "application/json"}
    session.verify = True
    return session


@pytest.fixture
def mock_session_with_auth():
    """Create a mock session with initial auth."""
    session = Mock()
    session.headers = {"Accept": "application/json", "Authorization": "Token initial-token"}
    session.verify = True
    return session


def test_request_success(mock_session):
    """Test successful request."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"success": True}

    mock_session.request.return_value = mock_response

    response = _request(session=mock_session, method="GET", url="https://example.com/api/test")

    assert response == mock_response
    mock_session.request.assert_called_once_with(
        method="GET",
        url="https://example.com/api/test",
        params=None,
        json=None,
        headers=mock_session.headers,
        verify=True,
        timeout=(3.05, 20.0),
    )


def test_request_with_params_and_json(mock_session):
    """Test request with parameters and JSON body."""
    mock_response = Mock()
    mock_response.status_code = 201

    mock_session.request.return_value = mock_response

    _request(
        session=mock_session,
        method="POST",
        url="https://example.com/api/test",
        params={"page": 1, "size": 10},
        json={"data": "test"},
        headers={"X-Test": "value"},
        timeout=(5.0, 30.0),
        verify=False,
    )

    mock_session.request.assert_called_once_with(
        method="POST",
        url="https://example.com/api/test",
        params={"page": 1, "size": 10},
        json={"data": "test"},
        headers={"Accept": "application/json", "X-Test": "value"},
        verify=False,
        timeout=(5.0, 30.0),
    )


def test_request_retry_on_server_error(mock_session):
    """Test that request retries on server errors."""
    error_response = Mock()
    error_response.status_code = 500

    success_response = Mock()
    success_response.status_code = 200

    # First call fails, second succeeds
    mock_session.request.side_effect = [error_response, success_response]

    # Use a mock for sleep_fn instead of patching time.sleep
    mock_sleep = Mock()

    response = _request(
        session=mock_session,
        method="GET",
        url="https://example.com/api/test",
        backoff_seconds=(0.1, 0.2),
        sleep_fn=mock_sleep,  # Pass mock as sleep function
    )

    assert response == success_response
    assert mock_session.request.call_count == 2
    mock_sleep.assert_called_once_with(0.1)


def test_request_token_refresh(mock_session_with_auth):
    """Test token refresh on 401/403 responses."""
    # First response is 401
    unauthorized_response = Mock()
    unauthorized_response.status_code = 401

    # Second response is successful
    success_response = Mock()
    success_response.status_code = 200

    mock_session_with_auth.request.side_effect = [unauthorized_response, success_response]

    token_fetcher = Mock(return_value="new-token-123")

    # Use a mock for sleep_fn
    mock_sleep = Mock()

    response = _request(
        session=mock_session_with_auth,
        method="GET",
        url="https://example.com/api/test",
        token_fetcher=token_fetcher,
        backoff_seconds=(0.1, 0.2),  # Need at least 2 attempts for retry
        sleep_fn=mock_sleep,
    )

    assert response == success_response
    # token_fetcher should be called once for refresh (since we already have initial auth)
    token_fetcher.assert_called_once()
    mock_sleep.assert_called_once_with(0.1)

    # Check that Authorization header was updated
    assert mock_session_with_auth.request.call_count == 2
    # Second call should have new token
    call_args = mock_session_with_auth.request.call_args_list[1]
    headers = call_args[1]["headers"]
    # Note: In your implementation, it sets "Token {tok}" not "Bearer {tok}"
    assert headers["Authorization"] == "Token new-token-123"


def test_request_initial_token_fetch(mock_session):
    """Test initial token fetch when no Authorization header exists."""
    """This tests the scenario where token_fetcher is called initially because there's no auth header."""
    mock_response = Mock()
    mock_response.status_code = 200

    mock_session.request.return_value = mock_response
    mock_session.headers = {"Accept": "application/json"}  # No Authorization

    token_fetcher = Mock(return_value="initial-token-456")
    mock_sleep = Mock()

    response = _request(
        session=mock_session,
        method="GET",
        url="https://example.com/api/test",
        token_fetcher=token_fetcher,
        backoff_seconds=(0.1,),
        sleep_fn=mock_sleep,
    )

    assert response == mock_response
    # token_fetcher should be called once for initial fetch
    token_fetcher.assert_called_once()
    mock_sleep.assert_not_called()  # No sleep on success

    # Check that Authorization header was added
    call_args = mock_session.request.call_args
    headers = call_args[1]["headers"]
    assert headers["Authorization"] == "Token initial-token-456"


def test_request_client_errors_return_immediately(mock_session):
    """Test that 400/404 errors return immediately without retry."""
    error_response = Mock()
    error_response.status_code = 404

    mock_session.request.return_value = error_response

    response = _request(
        session=mock_session, method="GET", url="https://example.com/api/test", backoff_seconds=(0.1, 0.2)
    )

    assert response == error_response
    mock_session.request.assert_called_once()  # No retry


def test_request_connection_error_returns_none(mock_session):
    """Test that connection errors return None."""
    mock_session.request.side_effect = requests.exceptions.ConnectionError("Failed to connect")

    response = _request(session=mock_session, method="GET", url="https://example.com/api/test")

    assert response is None


def test_get_wrapper(mock_session):
    """Test GET wrapper function."""
    mock_response = Mock()
    mock_session.request.return_value = mock_response

    # Fix: patch the function in its module
    with patch("doi_minting.clients.invenio_client.http_client._request") as mock_request:
        mock_request.return_value = mock_response

        response = get(mock_session, "https://example.com/api/test", params={"test": "value"})

        mock_request.assert_called_once_with(
            mock_session, "GET", "https://example.com/api/test", params={"test": "value"}
        )
        assert response == mock_response


def test_post_wrapper(mock_session):
    """Test POST wrapper function."""
    with patch("doi_minting.clients.invenio_client.http_client._request") as mock_request:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_request.return_value = mock_response
        post(mock_session, "https://example.com/api/test", data={"key": "value"})

        mock_request.assert_called_once_with(
            mock_session, "POST", "https://example.com/api/test", json={"key": "value"}
        )


def test_put_wrapper(mock_session):
    """Test PUT wrapper function."""
    with patch("doi_minting.clients.invenio_client.http_client._request") as mock_request:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_request.return_value = mock_response
        put(mock_session, "https://example.com/api/test", data={"key": "value"})

        mock_request.assert_called_once_with(mock_session, "PUT", "https://example.com/api/test", json={"key": "value"})


def test_delete_wrapper(mock_session):
    """Test DELETE wrapper function."""
    with patch("doi_minting.clients.invenio_client.http_client._request") as mock_request:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_request.return_value = mock_response
        delete(mock_session, "https://example.com/api/test")

        mock_request.assert_called_once_with(mock_session, "DELETE", "https://example.com/api/test")


def test_request_with_custom_auth_scheme(mock_session):
    """Test request with custom authentication scheme."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_session.request.return_value = mock_response

    token_fetcher = Mock(return_value="bearer-token")

    _request(
        session=mock_session,
        method="GET",
        url="https://example.com/api/test",
        token_fetcher=token_fetcher,
        auth_scheme="Bearer",
    )

    # Check Authorization header
    call_args = mock_session.request.call_args
    headers = call_args[1]["headers"]
    # The implementation uses auth_scheme parameter correctly
    assert headers["Authorization"] == "Bearer bearer-token"
