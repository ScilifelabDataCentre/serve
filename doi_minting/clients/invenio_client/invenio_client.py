"""InvenioRDM Client Module
Provides a comprehensive client for interacting with InvenioRDM API
"""

import json
import logging
from typing import Any, Dict, List, Optional, Tuple, Union, cast
from urllib.parse import urljoin

import requests

from .http_client import delete, get, post, put
from .session import make_session
from .tls import tls_verify_from_env

logger = logging.getLogger(__name__)


class InvenioClientError(Exception):
    """Base exception for InvenioRDM client errors"""

    pass


class InvenioRecordNotFoundError(InvenioClientError):
    """Raised when a requested record does not exist"""

    pass


class InvenioClient:
    """
    Client for interacting with InvenioRDM API

    Provides methods for:
    1. Creating draft records (with custom PIDs)
    2. Listing records (published and drafts)
    3. Getting records (published and drafts)
    4. Searching records
    5. Updating draft records
    6. Publishing draft records
    7. Editing published records (creating draft from published)
    8. Deleting/discarding draft records
    9. Versioning records
    """

    def __init__(
        self,
        base_url: str,
        token: str,
        auth_scheme: str = "Bearer",
        verify: Optional[Union[bool, str]] = None,
        timeout: Tuple[float, float] = (3.05, 20.0),
    ):
        """
        Initialize the InvenioRDM client

        Args:
            base_url: Base URL of the InvenioRDM instance (e.g., https://invenio.example.com)
            token: Authentication token
            auth_scheme: Authentication scheme ('Bearer' or 'Token')
            verify: SSL verification (True, False, or path to CA bundle)
            timeout: Request timeout in seconds (connect, read)
        """
        if not isinstance(base_url, str) or not base_url.strip():
            raise InvenioClientError("Invenio client misconfigured: 'base_url' is missing.")
        if not isinstance(token, str) or not token.strip():
            raise InvenioClientError("Invenio client misconfigured: 'token' is missing.")

        self.base_url = base_url.rstrip("/")
        self.token = token
        self.auth_scheme = auth_scheme
        self.timeout = timeout

        # Use environment variable for TLS verification if not specified
        if verify is None:
            verify = tls_verify_from_env()

        # Create session with authentication
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

        self.session = make_session(
            default_headers=headers,
            token=token,
            verify=verify,
        )

        # Override Authorization header with specified scheme
        self.session.headers["Authorization"] = f"{auth_scheme} {token}"

    def _build_url(self, endpoint: str) -> str:
        """Build full URL from endpoint path"""
        return urljoin(self.base_url + "/", endpoint.lstrip("/"))

    def _handle_response(
        self, response: Optional[requests.Response], success_codes: Optional[List[int]] = None
    ) -> Dict[str, Any]:
        """
        Handle API response, raising exceptions for errors

        Args:
            response: requests.Response object
            success_codes: List of HTTP status codes considered successful

        Returns:
            Parsed JSON response if available

        Raises:
            InvenioClientError: For API errors
        """
        if success_codes is None:
            success_codes = [200, 201, 202, 204]

        if response is None:
            raise InvenioClientError("Request failed - no response received")

        if response.status_code not in success_codes:
            error_msg = f"API request failed with status {response.status_code}"
            try:
                error_data = response.json()
                if "message" in error_data:
                    error_msg = f"{error_msg}: {error_data['message']}"
                if "errors" in error_data:
                    error_msg = f"{error_msg}\nErrors: {json.dumps(error_data['errors'], indent=2)}"
            except (json.JSONDecodeError, ValueError):
                error_msg = f"{error_msg}: {response.text}"

            if response.status_code == 404:
                raise InvenioRecordNotFoundError(error_msg)

            raise InvenioClientError(error_msg)

        # For 204 No Content responses, return empty dict
        if response.status_code == 204:
            return {}

        # Try to parse JSON response
        try:
            return cast(Dict[str, Any], response.json())
        except json.JSONDecodeError:
            raise InvenioClientError(f"Failed to parse JSON response: {response.text}")

    # ==================== DRAFT RECORDS ====================

    def create_draft(self, record_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a draft record

        Args:
            record_data: Complete record data including metadata, access, files, and custom_fields

        Returns:
            Created draft record data

        Note:
            To provide your own DOI, include in pids field:
            {"pids": {"doi": {"identifier": "10.1234/your.doi", "provider": "external"}}}
        """
        url = self._build_url("/api/records")

        # Use the complete record data directly
        data = record_data.copy()

        # Ensure required fields have defaults if not present
        if "access" not in data:
            data["access"] = {"record": "public", "files": "public"}
        if "files" not in data:
            data["files"] = {"enabled": False}

        response = post(self.session, url, data=data, timeout=self.timeout)
        return self._handle_response(response, success_codes=[201])

    def get_draft(self, record_id: str) -> Dict[str, Any]:
        """
        Get a draft record

        Args:
            record_id: Identifier of the draft record

        Returns:
            Draft record data
        """
        url = self._build_url(f"/api/records/{record_id}/draft")
        response = get(self.session, url, timeout=self.timeout)
        return self._handle_response(response)

    def update_draft(
        self,
        record_id: str,
        metadata: Optional[Dict[str, Any]] = None,
        access: Optional[Dict[str, Any]] = None,
        files: Optional[Dict[str, Any]] = None,
        custom_fields: Optional[Dict[str, Any]] = None,
        pids: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Update a draft record

        Args:
            record_id: Identifier of the draft record
            metadata: Updated metadata (partial updates allowed)
            access: Updated access options
            files: Updated files options
            custom_fields: Updated custom fields

        Returns:
            Updated draft record data

        Note:
            This is a PUT request, so provide complete record data.
            For partial updates, you might need to GET first, then update.
        """
        url = self._build_url(f"/api/records/{record_id}/draft")

        # Build update data
        data = {}
        if metadata:
            data["metadata"] = metadata
        if access:
            data["access"] = access
        if files:
            data["files"] = files
        if custom_fields:
            data["custom_fields"] = custom_fields
        if pids:
            data["pids"] = pids

        response = put(self.session, url, data=data, timeout=self.timeout)
        return self._handle_response(response)

    def publish_draft(self, record_id: str) -> Dict[str, Any]:
        """
        Publish a draft record

        Args:
            record_id: Identifier of the draft record

        Returns:
            Published record data
        """
        url = self._build_url(f"/api/records/{record_id}/draft/actions/publish")
        response = post(self.session, url, timeout=self.timeout)
        return self._handle_response(response, success_codes=[202])

    def delete_draft(self, record_id: str) -> bool:
        """
        Delete/discard a draft record

        Args:
            record_id: Identifier of the draft record

        Returns:
            True if successfully deleted

        Note:
            - For unpublished records: removes draft and associated files
            - For published records: removes draft but not the published record
        """
        url = self._build_url(f"/api/records/{record_id}/draft")
        response = delete(self.session, url, timeout=self.timeout)
        self._handle_response(response, success_codes=[204])
        return True

    # ==================== RECORDS (PUBLISHED) ====================

    def get_record(self, record_id: str) -> Dict[str, Any]:
        """
        Get a published record

        Args:
            record_id: Identifier of the record

        Returns:
            Published record data
        """
        url = self._build_url(f"/api/records/{record_id}")
        response = get(self.session, url, timeout=self.timeout)
        return self._handle_response(response)

    def search_records(
        self,
        query: Optional[str] = None,
        sort: str = "newest",
        size: int = 10,
        page: int = 1,
        allversions: bool = False,
        **additional_params: Any,
    ) -> Dict[str, Any]:
        """
        Search published records

        Args:
            query: Search query (ElasticSearch query string syntax)
            sort: Sort option (bestmatch, newest, oldest, updated-desc, updated-asc,
                  version, mostviewed, mostdownloaded)
            size: Number of items per page
            page: Page number
            allversions: Include all versions (default: False)
            **additional_params: Additional query parameters

        Returns:
            Search results with hits, aggregations, and links
        """
        url = self._build_url("/api/records")

        # Build query parameters
        params = {"sort": sort, "size": size, "page": page, "allversions": str(allversions).lower()}

        if query:
            params["q"] = query

        # Add any additional parameters
        params.update(additional_params)

        response = get(self.session, url, params=params, timeout=self.timeout)
        return self._handle_response(response)

    def edit_published_record(self, record_id: str) -> Dict[str, Any]:
        """
        Edit a published record (create a draft from published record)

        Args:
            record_id: Identifier of the published record

        Returns:
            Created draft record data
        """
        url = self._build_url(f"/api/records/{record_id}/draft")
        response = post(self.session, url, timeout=self.timeout)
        return self._handle_response(response, success_codes=[201])

    # ==================== USER RECORDS ====================

    def list_user_records(
        self,
        query: Optional[str] = None,
        sort: str = "newest",
        size: int = 10,
        page: int = 1,
        allversions: bool = False,
        **additional_params: Any,
    ) -> Dict[str, Any]:
        """
        List user's draft and published records

        Args:
            query: Search query
            sort: Sort option
            size: Number of items per page
            page: Page number
            allversions: Include all versions
            **additional_params: Additional query parameters

        Returns:
            User's records with hits, aggregations, and links
        """
        url = self._build_url("/api/user/records")

        # Build query parameters
        params = {"sort": sort, "size": size, "page": page, "allversions": str(allversions).lower()}

        if query:
            params["q"] = query

        # Add any additional parameters
        params.update(additional_params)

        response = get(self.session, url, params=params, timeout=self.timeout)
        return self._handle_response(response)

    # ==================== VERSION MANAGEMENT ====================

    def create_new_version(self, record_id: str) -> Dict[str, Any]:
        """
        Create a new version of a record

        Args:
            record_id: Identifier of the record

        Returns:
            New draft version record data
        """
        url = self._build_url(f"/api/records/{record_id}/versions")
        response = post(self.session, url, timeout=self.timeout)
        return self._handle_response(response, success_codes=[201])

    def get_all_versions(self, record_id: str) -> Dict[str, Any]:
        """
        Get all versions of a record

        Invenio uses Elasticsearch.
        There is a common issue with Elasticsearch,
        called 'eventual consistency.'
        Read more: https://medium.com/@zvardhan26/the-sneaky-elasticsearch-surprise-that-broke-my-work
        flows-and-how-i-fixed-it-a704486b482e

        Because of this 'eventual consistency', there might be a delay in indexing this new version.
        This means, this method can provide incorrect answer if we try
        to get all versions just right after creating it.

        We need to keep this in mind in case we expect something like this.
        A little delay is a good idea to ensure it works correctly.

        Args:
            record_id: Identifier of the record (any version)

        Returns:
            All versions of the record
        """
        url = self._build_url(f"/api/records/{record_id}/versions")
        response = get(self.session, url, timeout=self.timeout)
        return self._handle_response(response)

    def get_latest_version(self, record_id: str) -> Dict[str, Any]:
        """
        Get the latest version of a record

        Args:
            record_id: Identifier of the record (any version)

        Returns:
            Latest version record data
        """
        url = self._build_url(f"/api/records/{record_id}/versions/latest")
        response = get(self.session, url, timeout=self.timeout)
        return self._handle_response(response)

    # ==================== DOI MANAGEMENT ====================

    def reserve_doi(self, record_id: str) -> Dict[str, Any]:
        """
        Reserve a DOI for a draft record

        Args:
            record_id: Identifier of the draft record

        Returns:
            Record data with reserved DOI

        Note:
            The DOI will be registered when the record is published
        """
        url = self._build_url(f"/api/records/{record_id}/draft/pids/doi")
        response = post(self.session, url, timeout=self.timeout)
        return self._handle_response(response, success_codes=[201])

    def delete_doi(self, record_id: str) -> bool:
        """
        Delete a DOI from a draft record

        Args:
            record_id: Identifier of the draft record

        Returns:
            True if successfully deleted

        Note:
            Only deletes DOIs reserved via the API, not external DOIs
        """
        url = self._build_url(f"/api/records/{record_id}/draft/pids/doi")
        response = delete(self.session, url, timeout=self.timeout)
        self._handle_response(response, success_codes=[204])
        return True

    def search_funders(self, query: str, size: int = 10) -> List[Dict[str, str]]:
        """
        Search Invenio funders.

        Returns a simplified list:
        [
          {"id": "00k4n6c32", "name": "European Commission"},
          ...
        ]
        """
        if not query:
            return []

        params: Dict[str, Any] = {"q": query, "size": size}
        endpoints = [
            "/api/funders",
            "/api/vocabularies/funders",
        ]

        for endpoint in endpoints:
            response = self.session.get(f"{self.base_url}{endpoint}", params=params)

            if response.status_code == 404:
                continue

            data = self._handle_response(response)
            hits = data.get("hits", {}).get("hits", []) or []
            results: List[Dict[str, str]] = []
            for hit in hits:
                funder_id = hit.get("id")
                title = hit.get("title") or {}
                if isinstance(title, dict):
                    funder_name = title.get("en")
                    if not funder_name and title:
                        funder_name = next(iter(title.values()))
                else:
                    funder_name = None

                if funder_id and funder_name:
                    results.append({"id": funder_id, "name": funder_name})

            if results:
                return results

        return []
