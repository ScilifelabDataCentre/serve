from typing import Any, Dict, Set

import requests

from studio.utils import get_logger

logger = get_logger(__name__)

# TODO unfortunately for now we have to hardcode the loki reader endpoint
# This code is expected to be removed in the future as this is a temporary solution we have in place
LOKI_READER_ENDPOINT = "http://loki-read-headless.loki-stack.svc.cluster.local:3100"


def process_loki_response(response_json: Dict[str, Any]) -> Set[str]:
    """
    Extract unique IP addresses from the Loki JSON response.

    Args:
        response_json (dict): The JSON response from a Loki query.
    """
    unique_ips = set()
    try:
        results = response_json.get("data", {}).get("result", [])
        for result in results:
            values = result.get("values", [])
            for value in values:
                ip_address = value[1].strip()
                unique_ips.add(ip_address)
    except Exception as e:
        logger.error(f"Error extracting IPs from Loki response: {e}")
    return unique_ips


def query_unique_ip_count(app_subdomain: str = "") -> int:
    """
    Query Loki for unique IP addresses accessing a specific app subdomain.

    Args:
        app_subdomain (str): The subdomain of the app to query for.
    """
    if not app_subdomain:
        logger.error("app_subdomain must be provided")
        raise ValueError("app_subdomain must be provided")

    endpoint = f"{LOKI_READER_ENDPOINT}/loki/api/v1/query_range"
    query = (
        r'{container="rke2-ingress-nginx-controller"} |= "'
        + app_subdomain
        + '" '
        + r'| regexp "(?P<client_ip>\\b\\d{1,3}\\.\\d{1,3}\\.\\d{1,3}\\.\\d{1,3}\\b)" '
        + r'| line_format "{{.client_ip}}"'
    )

    params = {
        "query": query,
        "limit": "1000",  # Line number limit
    }

    response = requests.get(endpoint, params=params)
    response.raise_for_status()
    data = response.json()
    unique_ips = process_loki_response(data)
    return len(unique_ips)
