import requests

"""
InvenioRDM Client Module
Provides a comprehensive client for interacting with InvenioRDM API
"""

import json
from typing import Any, Dict, List, Optional, Union
from urllib.parse import urljoin

from .http_client import delete, get, post, put
from .session import make_session
from .tls import tls_verify_from_env


class InvenioClientError(Exception):
    """Base exception for InvenioRDM client errors"""

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
        timeout: tuple = (3.05, 20.0),
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

    def _handle_response(self, response, success_codes: List[int] = None) -> Dict[str, Any]:
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
            except:
                error_msg = f"{error_msg}: {response.text}"

            raise InvenioClientError(error_msg)

        # For 204 No Content responses, return empty dict
        if response.status_code == 204:
            return {}

        # Try to parse JSON response
        try:
            return response.json()
        except json.JSONDecodeError:
            raise InvenioClientError(f"Failed to parse JSON response: {response.text}")

    # ==================== DRAFT RECORDS ====================

    def create_draft(
        self,
        metadata: Dict[str, Any],
        access: Optional[Dict[str, Any]] = None,
        files: Optional[Dict[str, Any]] = None,
        custom_fields: Optional[Dict[str, Any]] = None,
        pids: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Create a draft record

        Args:
            metadata: Record metadata
            access: Access options (record, files, embargo), "public" or "restricted"
            files: Files options (enabled, default_preview, order)
            custom_fields: Custom fields metadata (v10 and newer)
            pids: Persistent identifiers (e.g., custom DOI)

        Returns:
            Created draft record data

        Note:
            To provide your own DOI, include in pids field:
            {"doi": {"identifier": "10.1234/your.doi", "provider": "external"}}
        """
        url = self._build_url("/api/records")

        # Build request body
        data = {"metadata": metadata}

        if access:
            data["access"] = access
        else:
            data["access"] = {"record": "public", "files": "public"}

        if files:
            data["files"] = files
        else:
            data["files"] = {"enabled": False}

        if custom_fields:
            data["custom_fields"] = custom_fields

        if pids:
            data["pids"] = pids

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
        **additional_params,
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
        **additional_params,
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
        There is a common issue with Elasticsearch, called 'eventual consistency.'
        Read more: https://medium.com/@zvardhan26/the-sneaky-elasticsearch-surprise-that-broke-my-workflows-and-how-i-fixed-it-a704486b482e

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


# temporary. will be in a different validation class later
def transform_to_invenio_metadata(schema_org_data):
    """Transform Schema.org JSON-LD to InvenioRDM metadata format"""

    # Extract data from Schema.org format
    metadata = {
        "access": {"record": "public", "files": "public"},
        "files": {"enabled": False},
        "metadata": {
            "title": "Serve "
            + schema_org_data["name"]
            + " of the App: '"
            + schema_org_data["hasPart"][0]["name"]
            + "'",
            "description": schema_org_data["description"],
            "publication_date": schema_org_data["dateCreated"][:10],  # Extract YYYY-MM-DD
            "publisher": schema_org_data["creator"]["name"],
            "resource_type": {"id": "dataset"},
            "creators": [{"person_or_org": {"name": schema_org_data["creator"]["name"], "type": "organizational"}}],
            "contributors": [],
            "rights": [
                {
                    "id": "cc-by-4.0",
                    "title": {"en": "Creative Commons Attribution 4.0 International"},
                    "description": {
                        "en": "The Creative Commons Attribution license allows re-distribution and re-use of a licensed work on the condition that the creator is appropriately credited."
                    },
                    "link": "https://creativecommons.org/licenses/by/4.0/",
                }
            ],
            "additional_descriptions": [
                {
                    "description": f"Application deployment metadata for SciLifeLab Serve platform. Contains details about software applications and project configuration.",
                    "type": {"id": "technical-info"},
                }
            ],
            "subjects": [
                {"subject": "Scientific Computing"},
                {"subject": "Cloud Deployment"},
                {"subject": "Kubernetes"},
            ],
        },
    }

    # Add software application details as custom fields
    if "hasPart" in schema_org_data and len(schema_org_data["hasPart"]) > 0:
        app_data = schema_org_data["hasPart"][0]

        metadata["metadata"]["custom_fields"] = {
            "kcr:application_deployment": {
                "software_application": {
                    "name": app_data.get("name", ""),
                    "description": app_data.get("description", ""),
                    "version": app_data.get("softwareVersion", ""),
                    "url": app_data.get("url", ""),
                    "application_category": app_data.get("applicationCategory", ""),
                    "operating_system": app_data.get("operatingSystem", ""),
                    "code_repository": app_data.get("hasPart", {}).get("codeRepository", ""),
                },
                "resource_requirements": {},
                "project_metadata": {},
            }
        }

        # Extract resource requirements from additionalProperty
        if "additionalProperty" in app_data:
            for prop in app_data["additionalProperty"]:
                prop_name = prop.get("name", "")
                prop_value = prop.get("value", "")
                if "cpu" in prop_name.lower():
                    metadata["metadata"]["custom_fields"]["kcr:application_deployment"]["resource_requirements"][
                        prop_name
                    ] = prop_value
                elif "memory" in prop_name.lower():
                    metadata["metadata"]["custom_fields"]["kcr:application_deployment"]["resource_requirements"][
                        prop_name
                    ] = prop_value
                elif "storage" in prop_name.lower():
                    metadata["metadata"]["custom_fields"]["kcr:application_deployment"]["resource_requirements"][
                        prop_name
                    ] = prop_value
                elif "app" in prop_name.lower():
                    metadata["metadata"]["custom_fields"]["kcr:application_deployment"]["resource_requirements"][
                        prop_name
                    ] = prop_value

        # Add project metadata
        if "about" in schema_org_data:
            project_data = schema_org_data["about"]
            metadata["metadata"]["custom_fields"]["kcr:application_deployment"]["project_metadata"] = {
                "project_name": project_data.get("name", ""),
                "project_description": project_data.get("description", ""),
                "services": {},
            }

            # Extract service counts
            if "additionalProperty" in project_data:
                for prop in project_data["additionalProperty"]:
                    service_name = prop.get("name", "")
                    service_count = prop.get("value", "0")
                    metadata["metadata"]["custom_fields"]["kcr:application_deployment"]["project_metadata"]["services"][
                        service_name
                    ] = service_count

    return metadata
