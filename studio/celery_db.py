from __future__ import annotations

from typing import Any

from celery.signals import task_failure, task_postrun, task_prerun
from django.conf import settings
from django.db import close_old_connections

from studio.db_pool import db_pool_stats_changed, get_db_pool_stats
from studio.utils import get_logger

logger = get_logger(__name__)
_last_celery_db_pool_stats: dict[str, Any] | None = None


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


@task_prerun.connect
def close_db_connections_before_task(task_id: str | None = None, task: Any = None, **kwargs: Any) -> None:
    close_old_connections()
    _log_celery_db_pool_stats("task_prerun", task_id=task_id, task=task)


@task_postrun.connect
def close_db_connections_after_task(task_id: str | None = None, task: Any = None, **kwargs: Any) -> None:
    close_old_connections()
    _log_celery_db_pool_stats("task_postrun", task_id=task_id, task=task)


@task_failure.connect
def log_db_pool_stats_after_task_failure(task_id: str | None = None, sender: Any = None, **kwargs: Any) -> None:
    _log_celery_db_pool_stats("task_failure", task_id=task_id, task=sender)
