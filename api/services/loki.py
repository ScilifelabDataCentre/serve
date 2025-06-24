import time

import requests

from studio.utils import get_logger

logger = get_logger(__name__)

# TODO unfortunately for now we have to hardcode the loki reader endpoint
# This code is expected to be removed in the future as this is a temporary solution we have in place
LOKI_READER_ENDPOINT = "http://loki-read-headless.loki-stack.svc.cluster.local:3100"


def query_unique_ip_count(app_subdomain: str = "") -> int:
    """
    Discover the Loki reader pod in the given namespace and query it for the count of unique ingress client IPs.
    The app_subdomain parameter is used to filter logs for the specific app.
    Returns the count as an integer.
    """
    if not app_subdomain:
        logger.error("app_subdomain must be provided")
        raise ValueError("app_subdomain must be provided")

    endpoint = f"{LOKI_READER_ENDPOINT}/loki/api/v1/query_range"
    # Calculate time in nanoseconds for the start of the window (29 days ago)
    start_time = f"{int((time.time() - (29 * 24 * 60 * 60)) * 1_000_000_000)}"
    # Calculate current time in nanoseconds for the end of the 29-day window (end_time)
    end_time = f"{int(time.time() * 1_000_000_000)}"

    query = (
        r'{container="rke2-ingress-nginx-controller"} |= "'
        + app_subdomain
        + '" '
        + r'| regexp "(?P<client_ip>\\b\\d{1,3}\\.\\d{1,3}\\.\\d{1,3}\\.\\d{1,3}\\b)" '
        + r'| line_format "{{.client_ip}}"'
    )

    params = {
        "query": query,
    }

    response = requests.get(endpoint, params=params)
    response.raise_for_status()
    data = response.json()
    result = data["data"]["result"][0]["values"] if data["data"]["result"] else []
    unique_ips = set(item[1] for item in result)
    return len(unique_ips)
