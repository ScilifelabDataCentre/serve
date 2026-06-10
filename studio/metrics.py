import os
from importlib import import_module
from typing import Any

from django.conf import settings
from django.http import HttpRequest, HttpResponse

from studio.middleware import get_db_pool_stats

prometheus_client = import_module("prometheus_client")
CONTENT_TYPE_LATEST = prometheus_client.CONTENT_TYPE_LATEST
Gauge = prometheus_client.Gauge
Counter = prometheus_client.Counter
Histogram = prometheus_client.Histogram
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
HTTP_REQUESTS_TOTAL = Counter(
    "django_http_requests_total",
    "Total number of Django HTTP requests handled by this process.",
    ["method", "route", "status_code", "pod"],
)
HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "django_http_request_duration_seconds",
    "Django HTTP request duration in seconds for this process.",
    ["method", "route", "status_code", "pod"],
)
HTTP_REQUEST_EXCEPTIONS_TOTAL = Counter(
    "django_http_request_exceptions_total",
    "Total number of Django HTTP requests that raised an exception in this process.",
    ["method", "route", "exception", "pod"],
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


def get_http_route_label(request: HttpRequest) -> str:
    resolver_match = getattr(request, "resolver_match", None)
    if resolver_match is None:
        return "unknown"
    view_name = getattr(resolver_match, "view_name", "")
    if isinstance(view_name, str) and view_name:
        return view_name
    route = getattr(resolver_match, "route", "")
    if isinstance(route, str) and route:
        return route
    return "unknown"


def _pod_label() -> str:
    return os.environ.get("HOSTNAME", "")


def record_http_request_metrics(request: HttpRequest, response: HttpResponse, duration_seconds: float) -> None:
    labels = {
        "method": request.method,
        "route": get_http_route_label(request),
        "status_code": str(response.status_code),
        "pod": _pod_label(),
    }
    HTTP_REQUESTS_TOTAL.labels(**labels).inc()
    HTTP_REQUEST_DURATION_SECONDS.labels(**labels).observe(duration_seconds)


def record_http_exception_metrics(request: HttpRequest, exception: Exception, duration_seconds: float) -> None:
    HTTP_REQUEST_EXCEPTIONS_TOTAL.labels(
        method=request.method,
        route=get_http_route_label(request),
        exception=exception.__class__.__name__,
        pod=_pod_label(),
    ).inc()
    labels = {
        "method": request.method,
        "route": get_http_route_label(request),
        "status_code": "exception",
        "pod": _pod_label(),
    }
    HTTP_REQUEST_DURATION_SECONDS.labels(**labels).observe(duration_seconds)


def metrics_view(request: HttpRequest) -> HttpResponse:
    if not settings.PROMETHEUS_METRICS_ENABLED:
        return HttpResponse(status=404)

    update_db_pool_metrics()
    return HttpResponse(generate_latest(), content_type=CONTENT_TYPE_LATEST)
