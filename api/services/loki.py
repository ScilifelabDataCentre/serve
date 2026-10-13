import re

import requests
from django.conf import settings

from studio.utils import get_logger

logger = get_logger(__name__)


def build_unique_ip_count_query(app_subdomain: str, days: int) -> str:
    r"""
    Build the LogQL query counting unique client IPs of requests to an app subdomain from the gateway access logs.

    Example for app_subdomain="my-subdomain" and days=7 (on one line):
        count(sum by (remote_addr) (count_over_time({namespace="gateway", container="nginx"}
            |~ `"https?://my\-subdomain\.`
            | regexp `^(?:\S+ (?:stdout|stderr) [FP] )?(?P<remote_addr>\S+) ` [7d])))

    Args:
        app_subdomain (str): The subdomain of the app to query for.
        days (int): Number of days to look back for data.
    """
    referer_regex = '"https?://' + re.escape(app_subdomain) + r"\."
    log_query = (
        '{namespace="gateway", container="nginx"}'
        + f" |~ `{referer_regex}`"
        + r" | regexp `^(?:\S+ (?:stdout|stderr) [FP] )?(?P<remote_addr>\S+) `"
    )
    return f"count(sum by (remote_addr) (count_over_time({log_query} [{days}d])))"


def query_unique_ip_count(app_subdomain: str = "", days: int = 30) -> int:
    """
    Query Loki for unique IP addresses accessing a specific app subdomain.

    Args:
        app_subdomain (str): The subdomain of the app to query for.
        days (int): Number of days to look back for data (default: 30).
    """
    if not app_subdomain:
        logger.error("app_subdomain must be provided")
        raise ValueError("app_subdomain must be provided")

    endpoint = f"{settings.LOKI_READER_ENDPOINT}/loki/api/v1/query"
    params = {"query": build_unique_ip_count_query(app_subdomain, days)}

    response = requests.get(endpoint, params=params)
    response.raise_for_status()
    results = response.json().get("data", {}).get("result", [])
    if not results:
        return 0
    return int(results[0]["value"][1])
