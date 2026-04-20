"""
InvenioRDM Client Exceptions

This module contains all exception classes for the InvenioRDM client.
"""


class InvenioClientError(Exception):
    """Base exception for InvenioRDM client errors"""

    pass


class InvenioClientRequestError(InvenioClientError):
    """Raised for client request errors (4xx status codes)"""

    pass


class InvenioServerError(InvenioClientError):
    """Raised for server errors (5xx status codes)"""

    pass
