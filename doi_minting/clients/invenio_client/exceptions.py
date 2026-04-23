"""
InvenioRDM Client Exceptions

This module contains all exception classes for the InvenioRDM client.
"""
from typing import Any, Dict, Optional


class InvenioClientError(Exception):
    """Base exception for InvenioRDM client errors"""

    pass


class InvenioClientRequestError(InvenioClientError):
    """Raised for client request errors (4xx status codes)"""

    pass


class InvenioServerError(InvenioClientError):
    """Raised for server errors (5xx status codes)"""

    pass


class RecordDeletedError(InvenioClientError):
    """Raised when a requested record has been removed and a tombstone is returned"""

    def __init__(self, message: str, tombstone_data: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.tombstone_data = tombstone_data or {}
