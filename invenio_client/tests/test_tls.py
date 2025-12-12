"""
Tests for tls.py module.
"""
import os
from unittest.mock import patch

import pytest

from invenio_client.tls import parse_tls_verify, tls_verify_from_env


def test_parse_tls_verify_default():
    """Test parsing TLS verify with None/default."""
    assert parse_tls_verify(None) is True


@pytest.mark.parametrize(
    "value,expected",
    [
        ("", True),
        ("1", True),
        ("true", True),
        ("TRUE", True),
        ("yes", True),
        ("on", True),
    ],
)
def test_parse_tls_verify_true_values(value, expected):
    """Test parsing TLS verify with truthy values."""
    assert parse_tls_verify(value) is True


@pytest.mark.parametrize(
    "value,expected",
    [
        ("0", False),
        ("false", False),
        ("FALSE", False),
        ("no", False),
        ("off", False),
    ],
)
def test_parse_tls_verify_false_values(value, expected):
    """Test parsing TLS verify with falsy values."""
    assert parse_tls_verify(value) is False


def test_parse_tls_verify_path():
    """Test parsing TLS verify with file path."""
    # Test with tilde expansion
    result = parse_tls_verify("~/cert.pem")
    # The actual expanded path depends on the user's home directory
    assert isinstance(result, str)
    assert "cert.pem" in result

    # Test with absolute path
    result = parse_tls_verify("/path/to/cert.pem")
    assert result == "/path/to/cert.pem"


@patch.dict(os.environ, {"TLS_SSL_VERIFICATION": "false"})
def test_tls_verify_from_env_false():
    """Test getting TLS verify from environment variable (false)."""
    assert tls_verify_from_env() is False


@patch.dict(os.environ, {"TLS_SSL_VERIFICATION": "true"})
def test_tls_verify_from_env_true():
    """Test getting TLS verify from environment variable (true)."""
    assert tls_verify_from_env() is True


@patch.dict(os.environ, {"TLS_SSL_VERIFICATION": "/path/to/cert.pem"})
def test_tls_verify_from_env_path():
    """Test getting TLS verify from environment variable (path)."""
    assert tls_verify_from_env() == "/path/to/cert.pem"


@patch.dict(os.environ, {}, clear=True)
def test_tls_verify_from_env_not_set():
    """Test getting TLS verify when environment variable is not set."""
    assert tls_verify_from_env() is True


@patch.dict(os.environ, {"CUSTOM_VERIFY_VAR": "false"})
def test_tls_verify_from_env_custom_var():
    """Test getting TLS verify from custom environment variable."""
    result = tls_verify_from_env("CUSTOM_VERIFY_VAR")
    assert result is False
