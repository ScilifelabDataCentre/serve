import os
import sys
import traceback
from typing import Any, Callable

from django.conf import settings
from django.db import connections
from django.http import HttpRequest, HttpResponse

from studio.utils import get_logger

logger = get_logger(__name__)
_last_db_pool_stats: dict[str, Any] | None = None
DB_POOL_STATS_CHANGE_KEYS = (
    "enabled",
    "opened",
    "pool_size",
    "pool_available",
    "requests_waiting",
    "requests_errors",
)


def get_db_pool_stats(alias: str = "default") -> dict[str, Any]:
    connection = connections[alias]
    pool_enabled = bool(connection.settings_dict["OPTIONS"].get("pool"))
    pools = getattr(connection, "_connection_pools", {})
    pool = pools.get(alias)

    stats = {
        "alias": alias,
        "enabled": pool_enabled,
        "opened": pool is not None,
        "pid": os.getpid(),
    }
    if pool is not None:
        stats.update(pool.get_stats())
    return stats


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
                    "Django DB pool stats path=%s status=%s pid=%s opened=%s "
                    "pool_size=%s pool_available=%s requests_waiting=%s requests_num=%s requests_errors=%s stats=%s",
                    request.path,
                    response.status_code,
                    pool_stats.get("pid"),
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

    current_stats = {key: stats.get(key) for key in DB_POOL_STATS_CHANGE_KEYS}
    previous_stats = _last_db_pool_stats
    _last_db_pool_stats = current_stats
    return previous_stats != current_stats
