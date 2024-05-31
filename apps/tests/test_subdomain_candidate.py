import pytest
from django.core.exceptions import ValidationError

from ..types_.subdomain import SubdomainCandidateName


@pytest.mark.django_db
def test_is_available_for_available_subdomains():
    """Tests for available subdomains"""
    candidate = SubdomainCandidateName("test-name-is-unique")
    assert candidate.is_available()

    candidate = SubdomainCandidateName("test-name-999-is-unique")
    assert candidate.is_available()


def test_is_available_for_unavailable_subdomains():
    """Tests for unavailable subdomains"""

    # Test using the reserved word serve
    candidate = SubdomainCandidateName("serve")
    assert not candidate.is_available()


@pytest.mark.parametrize("name", [("test-with-hyphens"), ("0n9"), ("z-a"), ("01234567890")])
def test_is_valid_for_valid_names(name):
    """Tests for valid subdomain names"""
    candidate = SubdomainCandidateName(name)
    assert candidate.is_valid()


@pytest.mark.parametrize("name", [("a"), ("Test-Uppercase"), ("-test-starthyphen"), ("test-endhyphen-")])
def test_is_valid_for_invalid_names(name):
    """Tests for invalid subdomain names"""
    candidate = SubdomainCandidateName(name)
    assert not candidate.is_valid()


def test_validate_subdomain():
    """
    Tests validity of subdomain names.
    Expects a raised ValidationError exception for invalid names.
    """

    # Test with valid subdomain
    candidate = SubdomainCandidateName("test-subdomain")
    candidate.validate_subdomain()

    # Test with invalid subdomain (too short)
    candidate = SubdomainCandidateName("a")
    with pytest.raises(ValidationError):
        candidate.validate_subdomain()

    # Test with invalid subdomain (contains uppercase)
    candidate = SubdomainCandidateName("Test-Subdomain")
    with pytest.raises(ValidationError):
        candidate.validate_subdomain()

    # Test with invalid subdomain (starts with hyphen)
    candidate = SubdomainCandidateName("-test-subdomain")
    with pytest.raises(ValidationError):
        candidate.validate_subdomain()
