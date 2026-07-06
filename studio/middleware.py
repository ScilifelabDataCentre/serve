import sys
import time
import traceback
from typing import Any, Callable

from django.conf import settings
from django.http import HttpRequest, HttpResponse

from studio.db_pool import db_pool_stats_changed, get_db_pool_stats
from studio.utils import get_logger

logger = get_logger(__name__)
_last_db_pool_stats: dict[str, Any] | None = None
METRICS_PATHS = ("/metrics", "/metrics/")


class ExceptionLoggingMiddleware:
    """
    This middleware provides logging of exception in requests.
    """

    def __init__(self, get_response: Callable[[HttpRequest], Any]):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        response = self.get_response(request)
        return response

    def process_exception(self, request: HttpRequest, exception: Exception) -> None:
        """
        Processes exceptions during handling of a http request.
        Logs them with ERROR level.
        """
        _, _, stacktrace = sys.exc_info()
        msg = f"Processing exception {exception} at {request.path} | "
        msg += f"GET {request.GET} | "
        msg += "".join(traceback.format_tb(stacktrace)).replace("\n", "\\n")
        logger.error(msg)
        return None


class PrometheusHttpMetricsMiddleware:
    """
    Records Django HTTP request metrics for the Prometheus endpoint.
    """

    def __init__(self, get_response: Callable[[HttpRequest], Any]):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        if not settings.PROMETHEUS_METRICS_ENABLED or request.path in METRICS_PATHS:
            return self.get_response(request)

        start = time.perf_counter()
        try:
            response = self.get_response(request)
        except Exception as exception:
            from studio.metrics import record_http_exception_metrics

            record_http_exception_metrics(request, exception, time.perf_counter() - start)
            raise

        from studio.metrics import record_http_request_metrics

        record_http_request_metrics(request, response, time.perf_counter() - start)
        return response


class DatabasePoolStatsLoggingMiddleware:
    """
    Logs psycopg pool stats from the Django worker process that handled the request.
    """

    def __init__(self, get_response: Callable[[HttpRequest], Any]):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        response = self.get_response(request)

        if settings.DB_POOL_STATS_LOGGING_ENABLED:
            pool_stats = get_db_pool_stats()
            if _db_pool_stats_changed(pool_stats):
                logger.info(
                    "Django DB pool stats path=%s status=%s pod=%s pid=%s pool_id=%s opened=%s "
                    "pool_size=%s pool_available=%s requests_waiting=%s requests_num=%s requests_errors=%s stats=%s",
                    request.path,
                    response.status_code,
                    pool_stats.get("pod"),
                    pool_stats.get("pid"),
                    pool_stats.get("pool_id"),
                    pool_stats.get("opened"),
                    pool_stats.get("pool_size"),
                    pool_stats.get("pool_available"),
                    pool_stats.get("requests_waiting"),
                    pool_stats.get("requests_num"),
                    pool_stats.get("requests_errors"),
                    pool_stats,
                )

        return response


def _db_pool_stats_changed(stats: dict[str, Any]) -> bool:
    global _last_db_pool_stats

    changed, current_stats = db_pool_stats_changed(stats, _last_db_pool_stats)
    _last_db_pool_stats = current_stats
    return changed
