import subprocess
from studio.utils import get_logger

logger = get_logger(__name__)

def get_loki_reader_pod(namespace: str = "loki-stack") -> str | None:
    """
    Uses kubectl to get the name of the headless Loki reader pod in the loki-stack namespace.
    Returns the pod name as a string, or None if not found or error.
    """
    label_selector = "app.kubernetes.io/name=loki,app.kubernetes.io/component=read"
    cmd = [
        "kubectl",
        "get",
        "pod",
        "-n",
        namespace,
        "-l",
        label_selector,
        "-o",
        "jsonpath={.items[0].metadata.name}"
    ]
    try:
        result = subprocess.check_output(cmd, text=True)
        pod_name = result.strip()
        if pod_name:
            return pod_name
        else:
            logger.warning(f"No Loki reader pod found in namespace {namespace}.")
            return None
    except subprocess.CalledProcessError as e:
        logger.error(f"Error running kubectl to get Loki reader pod: {e}")
        return None
