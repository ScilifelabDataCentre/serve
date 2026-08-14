import os
from typing import Any

from celery.signals import (
    task_failure,
    task_postrun,
    task_prerun,
    worker_process_shutdown,
    worker_ready,
)
from django.conf import settings
from django.db import close_old_connections

from studio.db_pool import db_pool_stats_changed, get_db_pool_stats
from studio.utils import get_logger

logger = get_logger(__name__)
_last_celery_db_pool_stats: dict[str, Any] | None = None

CELERY_METRICS_PORT = int(os.environ.get("CELERY_METRICS_PORT", "8001"))


def _task_name(task: Any) -> str:
    return getattr(task, "name", "") or task.__class__.__name__


def _log_celery_db_pool_stats(event: str, task_id: str | None = None, task: Any = None) -> None:
    global _last_celery_db_pool_stats

    if not settings.DB_POOL_STATS_LOGGING_ENABLED:
        return

    pool_stats = get_db_pool_stats()
    changed, current_stats = db_pool_stats_changed(pool_stats, _last_celery_db_pool_stats)
    _last_celery_db_pool_stats = current_stats
    if not changed and event != "task_failure":
        return

    logger.info(
        "Celery DB pool stats event=%s task=%s task_id=%s pod=%s pid=%s pool_id=%s opened=%s "
        "pool_size=%s pool_available=%s requests_waiting=%s requests_num=%s requests_errors=%s stats=%s",
        event,
        _task_name(task) if task is not None else "",
        task_id,
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


def _multiprocess_dir() -> str | None:
    return os.environ.get("PROMETHEUS_MULTIPROC_DIR")


def _update_db_pool_metrics() -> None:
    """Runs in the prefork child processes: snapshot this process's DB pool state."""
    if not settings.PROMETHEUS_METRICS_ENABLED or not _multiprocess_dir():
        return

    from studio.metrics import update_db_pool_metrics

    update_db_pool_metrics()


@worker_ready.connect
def start_metrics_server(**kwargs: Any) -> None:
    """
    Starts the Prometheus metrics HTTP server in the worker parent process.

    Requires PROMETHEUS_MULTIPROC_DIR to be set: the prefork child processes own
    the DB pools and write their metric values to mmap files in that directory,
    which this server aggregates via MultiProcessCollector.
    """
    if not settings.PROMETHEUS_METRICS_ENABLED:
        return
    if not _multiprocess_dir():
        logger.warning(
            "Celery metrics server not started: PROMETHEUS_MULTIPROC_DIR is not set "
            "but PROMETHEUS_METRICS_ENABLED is true."
        )
        return

    from prometheus_client import CollectorRegistry, multiprocess, start_http_server

    registry = CollectorRegistry()
    multiprocess.MultiProcessCollector(registry)  # type: ignore[no-untyped-call]
    start_http_server(CELERY_METRICS_PORT, registry=registry)
    logger.info("Celery metrics server started on port %s", CELERY_METRICS_PORT)


@worker_process_shutdown.connect
def cleanup_dead_process_metrics(pid: int | None = None, **kwargs: Any) -> None:
    if not _multiprocess_dir() or pid is None:
        return

    from prometheus_client import multiprocess

    multiprocess.mark_process_dead(pid)  # type: ignore[no-untyped-call]


@task_prerun.connect
def close_db_connections_before_task(task_id: str | None = None, task: Any = None, **kwargs: Any) -> None:
    close_old_connections()
    _log_celery_db_pool_stats("task_prerun", task_id=task_id, task=task)
    _update_db_pool_metrics()


@task_postrun.connect
def close_db_connections_after_task(task_id: str | None = None, task: Any = None, **kwargs: Any) -> None:
    close_old_connections()
    _log_celery_db_pool_stats("task_postrun", task_id=task_id, task=task)
    _update_db_pool_metrics()


@task_failure.connect
def log_db_pool_stats_after_task_failure(task_id: str | None = None, sender: Any = None, **kwargs: Any) -> None:
    _log_celery_db_pool_stats("task_failure", task_id=task_id, task=sender)
    _update_db_pool_metrics()
