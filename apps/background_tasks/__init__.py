"""
Background task framework for app instance operations.

This module provides a registry-based system for running validation,
external API calls, and other async operations before/after app deployment.
"""

from .base import BaseBackgroundTask
from .registry import TASK_REGISTRY

__all__ = ["BaseBackgroundTask", "TASK_REGISTRY"]
