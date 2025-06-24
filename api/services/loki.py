import time

import requests

from studio.utils import get_logger

from .kubectl import get_loki_reader_pod

logger = get_logger(__name__)


def query_unique_ip_count(namespace: str = "loki-stack", app_subdomain: str = "") -> int:
    """
    Discover the Loki reader pod in the given namespace and query it for the count of unique ingress client IPs.
    The app_subdomain parameter is used to filter logs for the specific app.
    Returns the count as an integer.
    
    if not app_subdomain:
        logger.error("app_subdomain must be provided")
        raise ValueError("app_subdomain must be provided")
    pod_name = get_loki_reader_pod(namespace)
    if not pod_name:
        logger.error(f"Could not find Loki reader pod in namespace {namespace}")
        raise ValueError(f"Could not find Loki reader pod in namespace {namespace}")
    """

    loki_reader_host = f"http://loki-read-headless.loki-stack.svc.cluster.local:3100"
    endpoint = f"{loki_reader_host}/loki/api/v1/query_range"

    end_time = f"{int(time.time() * 1_000_000_000)}"
    start_time = f"{int((time.time() - (29 * 24 * 60 * 60)) * 1_000_000_000)}"

    query = r'{container="rke2-ingress-nginx-controller"} |= "' + app_subdomain + '" ' + \
        r'| regexp "(?P<client_ip>\\b\\d{1,3}\\.\\d{1,3}\\.\\d{1,3}\\.\\d{1,3}\\b)" ' + \
        r'| line_format "{{.client_ip}}"'

    params = {
        "query": query,
        "start": start_time,
        "end": end_time,
    }

    response = requests.get(endpoint, params=params)
    response.raise_for_status()
    data = response.json()
    d = data["data"]["result"][0]["values"] if data["data"]["result"] else []
    unique_ips = set(item[1] for item in d)
    return len(unique_ips)
