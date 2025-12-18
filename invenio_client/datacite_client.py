"""
DataCite DOI Management Module
Provides functions for managing DOI states in DataCite registry
"""

import json
from typing import Any, Dict, Optional, Union

from .http_client import get, put
from .session import make_session
from .tls import tls_verify_from_env


class DataCiteError(Exception):
    """Base exception for DataCite client errors"""

    pass


class DataCiteClient:
    """
    Client for interacting with DataCite DOI Management API
    
    Provides methods for:
    1. Changing DOI state from 'findable' to 'registered'
    2. Changing DOI state from 'registered' to 'findable'
    3. Checking DOI registration status
    
    DataCite API Documentation: https://support.datacite.org/docs/api
    """

    def __init__(
        self,
        username: str,
        password: str,
        test_mode: bool = True,
        verify: Optional[Union[bool, str]] = None,
        timeout: tuple = (3.05, 20.0),
    ):
        """
        Initialize the DataCite client
        
        Args:
            username: DataCite repository account username
            password: DataCite repository account password
            test_mode: Use test API (True) or production API (False)
            verify: SSL verification (True, False, or path to CA bundle)
            timeout: Request timeout in seconds (connect, read)
        """
        self.username = username
        self.password = password
        self.test_mode = test_mode
        self.timeout = timeout
        
        # Determine base URL based on environment
        if test_mode:
            self.base_url = "https://api.test.datacite.org"
        else:
            self.base_url = "https://api.datacite.org"
        
        # Use environment variable for TLS verification if not specified
        if verify is None:
            verify = tls_verify_from_env()
        
        # Create session with authentication and required headers
        headers = {
            "Accept": "application/vnd.api+json",
            "Content-Type": "application/vnd.api+json",
            "User-Agent": f"SciLifeLab-Serve/1.0 (mailto:{username})"
        }
        
        self.session = make_session(
            default_headers=headers,
            verify=verify,
        )
        
        # Set up basic authentication for DataCite
        self.session.auth = (username, password)

    def _build_url(self, endpoint: str) -> str:
        """Build full URL from endpoint path"""
        if endpoint.startswith("http"):
            return endpoint
        return f"{self.base_url}{endpoint}"

    def _handle_response(self, response, success_codes: list = None) -> Dict[str, Any]:
        """
        Handle API response, raising exceptions for errors
        
        Args:
            response: requests.Response object
            success_codes: List of HTTP status codes considered successful
            
        Returns:
            Parsed JSON response if available
            
        Raises:
            DataCiteError: For API errors
        """
        if success_codes is None:
            success_codes = [200, 201, 202]
        
        if response is None:
            raise DataCiteError("Request failed - no response received")
        
        if response.status_code not in success_codes:
            error_msg = f"DataCite API request failed with status {response.status_code}"
            
            # Try to extract error details from response
            try:
                error_data = response.json()
                
                # DataCite returns errors in JSON:API format
                if "errors" in error_data:
                    errors = []
                    for err in error_data["errors"]:
                        error_detail = {
                            "status": err.get("status", "unknown"),
                            "title": err.get("title", "Unknown error"),
                            "detail": err.get("detail", ""),
                        }
                        if "source" in err:
                            error_detail["source"] = err["source"]
                        errors.append(error_detail)
                    
                    error_msg = f"{error_msg}\nErrors: {json.dumps(errors, indent=2)}"
                elif "message" in error_data:
                    error_msg = f"{error_msg}: {error_data['message']}"
            except json.JSONDecodeError:
                error_msg = f"{error_msg}: {response.text}"
            
            raise DataCiteError(error_msg)
        
        # For 204 No Content responses, return empty dict
        if response.status_code == 204:
            return {}
        
        # Try to parse JSON response
        try:
            return response.json()
        except json.JSONDecodeError:
            raise DataCiteError(f"Failed to parse JSON response: {response.text}")

    def _update_doi_state(self, doi: str, event: str, target_state: str) -> Dict[str, Any]:
        """
        Update DOI state using DataCite API
        
        Args:
            doi: The DOI to update (with or without URL)
            event: The event to trigger ('hide' or 'publish')
            target_state: The target state ('registered' or 'findable')
            
        Returns:
            Updated DOI information
            
        Raises:
            DataCiteError: If the update fails
            ValueError: If DOI format is invalid
        """
        # Clean DOI (remove URL prefix if present)
        clean_doi = doi.replace("https://doi.org/", "").strip()
        
        if not clean_doi.startswith("10."):
            raise ValueError(f"Invalid DOI format: {doi}")
        
        # Build the update payload
        update_data = {
            "data": {
                "type": "dois",
                "id": clean_doi,
                "attributes": {
                    "event": event,
                    "state": target_state
                }
            }
        }
        
        # Make the API call
        url = self._build_url(f"/dois/{clean_doi}")
        response = put(
            self.session,
            url,
            data=update_data,
            timeout=self.timeout
        )
        
        return self._handle_response(response, success_codes=[200])

    def switch_to_register_doi(self, doi: str) -> Dict[str, Any]:
        """
        Change DOI state from 'findable' to 'registered'
        
        This makes the DOI non-findable in public searches.
        Use case: Temporarily hide a DOI from public view.
        
        IMPORTANT: For findable -> registered, use event='hide' not 'register'
        
        Args:
            doi: The DOI to register (e.g., "10.1234/example" or full URL)
            
        Returns:
            Dictionary containing:
                - status: "success" or "error"
                - message: Human-readable message
                - data: Full API response
                - state: New state of the DOI
                - actual_state: Actual state from API response (for verification)
            
        Example:
            >>> client = DataCiteClient(username, password)
            >>> result = client.switch_to_register_doi("10.1234/example")
            >>> print(result["state"])  # "registered"
        """
        try:
            # CORRECTION: Use 'hide' event for findable -> registered transition
            result = self._update_doi_state(doi, "hide", "registered")
            
            # Extract the new state from response
            new_state = result.get("data", {}).get("attributes", {}).get("state", "unknown")
            
            # Verify the state change was successful
            if new_state == "registered":
                return {
                    "status": "success",
                    "message": f"DOI {doi} successfully updated to 'registered' state",
                    "data": result,
                    "state": new_state,
                    "actual_state": new_state
                }
            else:
                # The API accepted the request but state didn't change as expected
                return {
                    "status": "partial_success",
                    "message": f"Request accepted but DOI state is '{new_state}' (expected 'registered')",
                    "data": result,
                    "state": new_state,
                    "actual_state": new_state,
                    "warning": f"State mismatch: requested 'registered', got '{new_state}'. "
                              f"Check DOI workflow rules."
                }
            
        except DataCiteError as e:
            # Extract more details from the exception if available
            error_msg = str(e)
            if "event: is not a valid event" in error_msg:
                error_msg += "\nNote: The event might be incorrect for the current DOI state. " \
                           "For findable -> registered, use event='hide'."
            
            return {
                "status": "error",
                "message": f"Failed to register DOI: {error_msg}",
                "doi": doi
            }
        except ValueError as e:
            return {
                "status": "error",
                "message": f"Invalid DOI format: {str(e)}",
                "doi": doi
            }

    def switch_to_findable_doi(self, doi: str) -> Dict[str, Any]:
        """
        Change DOI state from 'registered' to 'findable'
        
        This makes the DOI publicly findable and searchable.
        Use case: Make a previously registered DOI publicly available.
        
        Args:
            doi: The DOI to publish (e.g., "10.1234/example" or full URL)
            
        Returns:
            Dictionary containing:
                - status: "success" or "error"
                - message: Human-readable message
                - data: Full API response
                - state: New state of the DOI
                - actual_state: Actual state from API response
            
        Example:
            >>> client = DataCiteClient(username, password)
            >>> result = client.switch_to_findable_doi("10.1234/example")
            >>> print(result["state"])  # "findable"
        """
        try:
            result = self._update_doi_state(doi, "publish", "findable")
            
            # Extract the new state from response
            new_state = result.get("data", {}).get("attributes", {}).get("state", "unknown")
            
            # Verify the state change was successful
            if new_state == "findable":
                return {
                    "status": "success",
                    "message": f"DOI {doi} successfully published to 'findable' state",
                    "data": result,
                    "state": new_state,
                    "actual_state": new_state
                }
            else:
                return {
                    "status": "partial_success",
                    "message": f"Request accepted but DOI state is '{new_state}' (expected 'findable')",
                    "data": result,
                    "state": new_state,
                    "actual_state": new_state,
                    "warning": f"State mismatch: requested 'findable', got '{new_state}'"
                }
            
        except DataCiteError as e:
            error_msg = str(e)
            if "event: is not a valid event" in error_msg:
                error_msg += "\nNote: The event might be incorrect for the current DOI state. " \
                           "For registered -> findable, use event='publish'."
            
            return {
                "status": "error",
                "message": f"Failed to publish DOI: {error_msg}",
                "doi": doi
            }
        except ValueError as e:
            return {
                "status": "error",
                "message": f"Invalid DOI format: {str(e)}",
                "doi": doi
            }

    def check_doi_status(self, doi: str, include_metadata: bool = False) -> Dict[str, Any]:
        """
        Check the status of a DOI
        
        Args:
            doi: The DOI to check (e.g., "10.1234/example" or full URL)
            include_metadata: If True, include full metadata in response
            
        Returns:
            Dictionary containing:
                - status: "success", "error", or "not_found"
                - state: Current state of the DOI
                - doi: The checked DOI
                - data: Full API response (if include_metadata=True)
                - message: Human-readable message
                - allowed_events: List of allowed events for current state (if available)
            
        Example:
            >>> client = DataCiteClient(username, password)
            >>> result = client.check_doi_status("10.1234/example")
            >>> print(result["state"])  # "findable", "registered", or "draft"
        """
        # Clean DOI (remove URL prefix if present)
        clean_doi = doi.replace("https://doi.org/", "").strip()
        
        if not clean_doi.startswith("10."):
            return {
                "status": "error",
                "message": f"Invalid DOI format: {doi}",
                "doi": doi,
                "state": "invalid"
            }
        
        try:
            url = self._build_url(f"/dois/{clean_doi}")
            response = get(self.session, url, timeout=self.timeout)
            
            if response is None:
                return {
                    "status": "error",
                    "message": "No response received from DataCite API",
                    "doi": doi,
                    "state": "unknown"
                }
            
            # Handle 404 - DOI not found
            if response.status_code == 404:
                return {
                    "status": "not_found",
                    "message": f"DOI {doi} not found in DataCite registry",
                    "doi": doi,
                    "state": "not_found"
                }
            
            # Handle successful response
            if response.status_code == 200:
                result = response.json()
                state = result.get("data", {}).get("attributes", {}).get("state", "unknown")
                
                response_data = {
                    "status": "success",
                    "state": state,
                    "doi": doi,
                    "message": f"DOI is currently in '{state}' state"
                }
                
                # Extract allowed events if available in the response
                # Note: DataCite API doesn't return allowed events directly, but we can infer
                allowed_events = self._get_allowed_events_for_state(state)
                if allowed_events:
                    response_data["allowed_events"] = allowed_events
                    response_data["message"] += f". Allowed events: {', '.join(allowed_events)}"
                
                if include_metadata:
                    response_data["data"] = result
                
                return response_data
            
            # Handle other error responses
            error_msg = f"API returned status {response.status_code}"
            try:
                error_data = response.json()
                if "errors" in error_data:
                    error_msg = f"{error_msg}: {error_data['errors'][0].get('title', 'Unknown error')}"
            except:
                error_msg = f"{error_msg}: {response.text}"
            
            return {
                "status": "error",
                "message": error_msg,
                "doi": doi,
                "state": "unknown"
            }
            
        except Exception as e:
            return {
                "status": "error",
                "message": f"Failed to check DOI status: {str(e)}",
                "doi": doi,
                "state": "unknown"
            }

    def _get_allowed_events_for_state(self, state: str) -> list:
        """
        Get allowed events for a given DOI state based on DataCite workflow
        
        Args:
            state: Current DOI state
            
        Returns:
            List of allowed events for the state
        """
        # DataCite state machine rules:
        # draft -> register -> registered
        # draft -> publish -> findable
        # registered -> publish -> findable
        # findable -> hide -> registered
        
        state_event_map = {
            "draft": ["register", "publish"],
            "registered": ["publish"],
            "findable": ["hide"],
        }
        
        return state_event_map.get(state, [])

    def verify_credentials(self) -> Dict[str, Any]:
        """
        Verify that the provided credentials are valid
        
        Returns:
            Dictionary with verification result
        """
        try:
            # Try to access a simple endpoint that requires authentication
            url = self._build_url("/dois")
            response = get(
                self.session,
                url,
                params={"page[size]": 1},
                timeout=self.timeout
            )
            
            if response is None:
                return {
                    "status": "error",
                    "message": "No response received from DataCite API",
                    "valid": False
                }
            
            if response.status_code == 200:
                return {
                    "status": "success",
                    "message": "Credentials are valid",
                    "valid": True,
                    "environment": "test" if self.test_mode else "production"
                }
            elif response.status_code == 401:
                return {
                    "status": "error",
                    "message": "Invalid credentials (401 Unauthorized)",
                    "valid": False
                }
            elif response.status_code == 403:
                return {
                    "status": "error",
                    "message": "Insufficient permissions (403 Forbidden)",
                    "valid": False
                }
            else:
                return {
                    "status": "error",
                    "message": f"Unexpected response: {response.status_code}",
                    "valid": False,
                    "response_code": response.status_code
                }
            
        except Exception as e:
            return {
                "status": "error",
                "message": f"Failed to verify credentials: {str(e)}",
                "valid": False
            }

    def get_doi_workflow_info(self, doi: str) -> Dict[str, Any]:
        """
        Get detailed workflow information for a DOI
        
        Args:
            doi: The DOI to analyze
            
        Returns:
            Dictionary with workflow analysis
        """
        # First get current status
        status_result = self.check_doi_status(doi, include_metadata=True)
        
        if status_result["status"] != "success":
            return status_result
        
        current_state = status_result["state"]
        allowed_events = self._get_allowed_events_for_state(current_state)
        
        workflow_info = {
            "current_state": current_state,
            "allowed_events": allowed_events,
            "possible_transitions": []
        }
        
        # Define possible transitions based on current state
        if current_state == "findable":
            workflow_info["possible_transitions"].append({
                "from": "findable",
                "to": "registered",
                "event": "hide",
                "description": "Hide DOI from public search (temporarily)"
            })
        elif current_state == "registered":
            workflow_info["possible_transitions"].append({
                "from": "registered",
                "to": "findable",
                "event": "publish",
                "description": "Make DOI publicly findable"
            })
        elif current_state == "draft":
            workflow_info["possible_transitions"].extend([
                {
                    "from": "draft",
                    "to": "registered",
                    "event": "register",
                    "description": "Register DOI without making it findable"
                },
                {
                    "from": "draft",
                    "to": "findable",
                    "event": "publish",
                    "description": "Publish DOI and make it findable"
                }
            ])
        
        return {
            "status": "success",
            "workflow": workflow_info,
            "doi": doi
        }