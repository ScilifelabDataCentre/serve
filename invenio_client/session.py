"""Configure requests.Session with retries, adapters, and TLS settings."""

from typing import Mapping, Optional, Tuple, Union

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

Timeout = Tuple[float, float]
VerifyType = Union[bool, str]


def make_session(
    *,
    default_headers: Optional[Mapping[str, str]] = None,
    token: Optional[str] = None,
    total_retries: int = 3,
    verify: Optional[VerifyType] = None,
) -> requests.Session:
    """
    Create and configure a requests.Session with retry logic and optional headers.

    The returned session is preconfigured with:
      - Default headers (merged with any provided by the caller).
      - An optional Bearer/Token token in the Authorization header.
      - An HTTPAdapter mounted on both HTTP and HTTPS with a Retry policy.

    Args:
        default_headers (Mapping[str, str], optional): Extra headers to add to
            the session (e.g., {"Accept": "application/json"}).
        token (str, optional): Bearer/Token token to include in the Authorization header.
        total_retries (int, optional): Total number of retries for failed
            connections and retryable status codes (default is 3).

    Returns:
        requests.Session: A configured session ready for use with get/post wrappers.
    """
    s = requests.Session()
    s.headers.update({"Accept": "application/json"})
    if default_headers:
        s.headers.update(default_headers)

    if verify is not None:
        s.verify = verify

    if token:
        s.headers["Authorization"] = f"Token {token}"

    retry = Retry(
        total=total_retries,
        connect=total_retries,
        read=total_retries,
        backoff_factor=0.5,
        status_forcelist=[500, 502, 503, 504],
        allowed_methods=frozenset(
            [
                "HEAD",
                "GET",
                "PUT",
                "DELETE",
                "OPTIONS",
                "TRACE",
                "POST",
            ]
        ),
    )
    adapter = HTTPAdapter(max_retries=retry)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    return s
