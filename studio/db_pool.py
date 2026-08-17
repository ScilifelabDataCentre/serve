import os
from typing import Any

from django.db import connections

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
    pod_name = os.environ.get("HOSTNAME", "")
    pid = os.getpid()

    stats = {
        "alias": alias,
        "enabled": pool_enabled,
        "opened": pool is not None,
        "pid": pid,
        "pod": pod_name,
        "pool_id": f"{pod_name}:{pid}:{alias}",
    }
    if pool is not None:
        stats.update(pool.get_stats())
    return stats


def db_pool_stats_changed(
    stats: dict[str, Any],
    previous_stats: dict[str, Any] | None,
) -> tuple[bool, dict[str, Any]]:
    current_stats = {key: stats.get(key) for key in DB_POOL_STATS_CHANGE_KEYS}
    return previous_stats != current_stats, current_stats
