"""InvenioRDM Client Package

Provides a comprehensive client for interacting with InvenioRDM API.

Main exports:
- InvenioClient: The main client class
- Exception classes for error handling
"""

from .exceptions import (
    InvenioClientError,
    InvenioClientRequestError,
    InvenioServerError,
    RecordDeletedError,
)
from .http_client import _request, delete, get, post, put
from .invenio_client import InvenioClient
from .session import make_session
from .tls import tls_verify_from_env

__all__ = [
    # Main client
    "InvenioClient",
    # Exceptions
    "InvenioClientError",
    "InvenioClientRequestError",
    "InvenioServerError",
    "RecordDeletedError",
    # HTTP utilities
    "make_session",
    "_request",
    "get",
    "post",
    "put",
    "delete",
    "tls_verify_from_env",
]
