"""
Background task framework for app instance operations.

This module provides a registry-based system for running validation,
external API calls, and other async operations before/after app deployment.
"""

from .base import BaseBackgroundTask
from .feature_flags import (
    BACKGROUND_TASKS_NONBLOCKING_DEPLOY_SWITCH,
    background_tasks_nonblocking_deploy,
)
from .registry import TASK_REGISTRY

__all__ = [
    "BACKGROUND_TASKS_NONBLOCKING_DEPLOY_SWITCH",
    "BaseBackgroundTask",
    "TASK_REGISTRY",
    "background_tasks_nonblocking_deploy",
]
