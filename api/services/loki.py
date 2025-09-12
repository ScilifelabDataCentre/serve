from typing import Any, Dict, Set

import requests

from studio.utils import get_logger
from django.conf import settings

logger = get_logger(__name__)


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
                if len(value) > 1:
                    ip_address = value[1].strip()
                    if ip_address:
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

    endpoint = f"{settings.LOKI_READER_ENDPOINT}/loki/api/v1/query_range"

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
        "since": "30d",
    }

    response = requests.get(endpoint, params=params)
    response.raise_for_status()
    data = response.json()
    unique_ips = process_loki_response(data)
    return len(unique_ips)
