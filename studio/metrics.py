from importlib import import_module
from typing import Any

from django.conf import settings
from django.http import HttpRequest, HttpResponse

from studio.middleware import get_db_pool_stats

prometheus_client = import_module("prometheus_client")
CONTENT_TYPE_LATEST = prometheus_client.CONTENT_TYPE_LATEST
Gauge = prometheus_client.Gauge
generate_latest = prometheus_client.generate_latest

DB_POOL_ENABLED = Gauge(
    "django_db_pool_enabled",
    "Whether Django database connection pooling is enabled.",
    ["alias", "pod", "pid", "pool_id"],
)
DB_POOL_OPENED = Gauge(
    "django_db_pool_opened",
    "Whether the Django database connection pool has been opened in this process.",
    ["alias", "pod", "pid", "pool_id"],
)
DB_POOL_SIZE = Gauge(
    "django_db_pool_size",
    "Current number of connections in the Django database connection pool.",
    ["alias", "pod", "pid", "pool_id"],
)
DB_POOL_AVAILABLE = Gauge(
    "django_db_pool_available",
    "Current number of available connections in the Django database connection pool.",
    ["alias", "pod", "pid", "pool_id"],
)
DB_POOL_MIN = Gauge(
    "django_db_pool_min",
    "Configured minimum number of connections in the Django database connection pool.",
    ["alias", "pod", "pid", "pool_id"],
)
DB_POOL_MAX = Gauge(
    "django_db_pool_max",
    "Configured maximum number of connections in the Django database connection pool.",
    ["alias", "pod", "pid", "pool_id"],
)
DB_POOL_REQUESTS_WAITING = Gauge(
    "django_db_pool_requests_waiting",
    "Current number of requests waiting for a Django database connection pool slot.",
    ["alias", "pod", "pid", "pool_id"],
)
DB_POOL_REQUESTS_NUM = Gauge(
    "django_db_pool_requests_total",
    "Total number of requests served by the Django database connection pool in this process.",
    ["alias", "pod", "pid", "pool_id"],
)
DB_POOL_REQUESTS_ERRORS = Gauge(
    "django_db_pool_requests_errors_total",
    "Total number of Django database connection pool request errors in this process.",
    ["alias", "pod", "pid", "pool_id"],
)


def _metric_value(stats: dict[str, Any], key: str) -> float:
    value = stats.get(key)
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, int | float):
        return float(value)
    return 0.0


def update_db_pool_metrics() -> None:
    stats = get_db_pool_stats()
    labels = {
        "alias": str(stats.get("alias", "")),
        "pod": str(stats.get("pod", "")),
        "pid": str(stats.get("pid", "")),
        "pool_id": str(stats.get("pool_id", "")),
    }

    DB_POOL_ENABLED.labels(**labels).set(_metric_value(stats, "enabled"))
    DB_POOL_OPENED.labels(**labels).set(_metric_value(stats, "opened"))
    DB_POOL_SIZE.labels(**labels).set(_metric_value(stats, "pool_size"))
    DB_POOL_AVAILABLE.labels(**labels).set(_metric_value(stats, "pool_available"))
    DB_POOL_MIN.labels(**labels).set(_metric_value(stats, "pool_min"))
    DB_POOL_MAX.labels(**labels).set(_metric_value(stats, "pool_max"))
    DB_POOL_REQUESTS_WAITING.labels(**labels).set(_metric_value(stats, "requests_waiting"))
    DB_POOL_REQUESTS_NUM.labels(**labels).set(_metric_value(stats, "requests_num"))
    DB_POOL_REQUESTS_ERRORS.labels(**labels).set(_metric_value(stats, "requests_errors"))


def metrics_view(request: HttpRequest) -> HttpResponse:
    if not settings.PROMETHEUS_METRICS_ENABLED:
        return HttpResponse(status=404)

    update_db_pool_metrics()
    return HttpResponse(generate_latest(), content_type=CONTENT_TYPE_LATEST)
