"""
ORCID OAuth utilities for SciLifeLab Serve.

Uses ORCID Public API v3.0 with OAuth 2.0 /authenticate scope.
Users connect their ORCID iD from the Profile Edit page.

Setup:
    Add to Django settings (via env vars):
        ORCID_CLIENT_ID
        ORCID_CLIENT_SECRET
        ORCID_REDIRECT_URI       # e.g. https://serve.scilifelab.se/orcid/callback/
        ORCID_BASE_URL           # https://orcid.org (prod) or https://sandbox.orcid.org (test)
"""

import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


def get_orcid_config():
    """Return ORCID configuration from Django settings."""
    return {
        "client_id": getattr(settings, "ORCID_CLIENT_ID", ""),
        "client_secret": getattr(settings, "ORCID_CLIENT_SECRET", ""),
        "redirect_uri": getattr(settings, "ORCID_REDIRECT_URI", ""),
        "base_url": getattr(settings, "ORCID_BASE_URL", "https://orcid.org"),
    }


def is_orcid_configured():
    """Check if ORCID integration is properly configured."""
    cfg = get_orcid_config()
    return bool(cfg["client_id"] and cfg["client_secret"] and cfg["redirect_uri"])


def get_authorization_url(state):
    """
    Build the ORCID OAuth authorization URL.

    Args:
        state: Random string for CSRF protection (store in session).

    Returns:
        Full authorization URL to redirect the user to.
    """
    cfg = get_orcid_config()
    return (
        f"{cfg['base_url']}/oauth/authorize"
        f"?client_id={cfg['client_id']}"
        f"&response_type=code"
        f"&scope=/authenticate"
        f"&redirect_uri={cfg['redirect_uri']}"
        f"&state={state}"
    )


def exchange_code_for_token(authorization_code):
    """
    Exchange the authorization code for an access token and ORCID iD.

    Args:
        authorization_code: The code returned by ORCID after user authorization.

    Returns:
        Dict with keys: access_token, orcid, token_type, scope, etc.
        Or None on failure.

        Example response from ORCID:
        {
            "access_token": "f5af9f51-07e6-4332-8f1a-c0c11c1e3728",
            "token_type": "bearer",
            "refresh_token": "f725f747-3a65-49f6-a231-3e8944ce464d",
            "expires_in": 631138518,
            "scope": "/authenticate",
            "name": "Maria Andersson",
            "orcid": "0000-0002-1234-5678"
        }
    """
    cfg = get_orcid_config()

    try:
        response = requests.post(
            f"{cfg['base_url']}/oauth/token",
            data={
                "client_id": cfg["client_id"],
                "client_secret": cfg["client_secret"],
                "grant_type": "authorization_code",
                "code": authorization_code,
                "redirect_uri": cfg["redirect_uri"],
            },
            headers={"Accept": "application/json"},
            timeout=10,
        )
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        logger.error(f"ORCID token exchange failed: {e}")
        return None
