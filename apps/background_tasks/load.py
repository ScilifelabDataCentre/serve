"""
Explicit entrypoint for background task registration.

Background tasks are registered via decorators at import time, so we keep a
single deterministic import list here and call it from Django app startup.
"""

from __future__ import annotations

from importlib import import_module
from typing import Final

from studio.utils import get_logger

logger = get_logger(__name__)

# Deliberate, explicit list of task modules to import for registration.
_TASK_MODULES: Final[tuple[str, ...]] = ("apps.background_tasks.tasks.validation",)

_loaded = False


def register_tasks() -> None:
    """
    Import task modules to trigger decorator-based registration.

    This function is intentionally idempotent within a single process.
    """
    global _loaded
    if _loaded:
        return

    for module_path in _TASK_MODULES:
        import_module(module_path)

    _loaded = True
    logger.debug("Background tasks registered via %s", __name__)
