"""
Base class for background tasks.
"""

from abc import ABC, abstractmethod
from typing import Any, ClassVar, Dict, Optional

from studio.utils import get_logger

logger = get_logger(__name__)


class BaseBackgroundTask(ABC):
    """
    Abstract base class for all background tasks.

    Subclasses must implement the execute() method and can optionally
    override other methods for custom behavior.
    """

    # Registration metadata (set by @TASK_REGISTRY.register)
    task_name: ClassVar[str] = ""
    is_critical: ClassVar[bool] = False
    execution_order: ClassVar[int] = 0
    app_types: ClassVar[tuple[str, ...] | None] = None

    # Default configuration
    max_retries = 3
    task_type = "validation"  # Options: validation, external_api, post_deploy
    timeout_seconds = 300  # 5 minutes default timeout

    @abstractmethod
    def execute(self, app_instance, **kwargs) -> dict[str, Any]:
        """
        Execute the task logic.

        Args:
            app_instance: The BaseAppInstance object
            **kwargs: Additional parameters passed to the task

        Returns:
            Dict containing task results/output data

        Raises:
            Exception: If task execution fails
        """
        raise NotImplementedError("Subclasses must implement execute()")

    def on_failure(self, app_instance, error: Exception) -> None:
        """
        Called when task execution fails.

        Can be overridden to implement custom error handling,
        cleanup, or notification logic.

        Args:
            app_instance: The BaseAppInstance object
            error: The exception that caused the failure
        """
        logger.error(
            f"Task {self.__class__.__name__} failed for app {app_instance.id}: {error}",
            exc_info=True,
        )

    def on_success(self, app_instance, result: dict[str, Any]) -> None:
        """
        Called when task execution succeeds.

        Can be overridden to implement custom success handling
        or post-processing logic.

        Args:
            app_instance: The BaseAppInstance object
            result: The result data returned by execute()
        """
        logger.info(f"Task {self.__class__.__name__} succeeded for app {app_instance.id}")

    def should_retry(self, error: Exception, retry_count: int) -> bool:
        """
        Determine if the task should be retried after a failure.

        Args:
            error: The exception that caused the failure
            retry_count: Number of times task has already been retried

        Returns:
            True if task should be retried, False otherwise
        """
        if retry_count >= self.max_retries:
            return False

        # Don't retry validation errors or permission errors
        from django.core.exceptions import PermissionDenied, ValidationError

        if isinstance(error, (ValidationError, PermissionDenied)):
            return False

        return True

    def get_retry_delay(self, retry_count: int) -> int:
        """
        Calculate delay before next retry (exponential backoff).

        Args:
            retry_count: Number of times task has been retried

        Returns:
            Delay in seconds
        """
        # Exponential backoff (capped at 5 minutes): 15s, 75s, 300s...
        return min(15 * (5**retry_count), 300)

    def validate_inputs(self, app_instance, **kwargs) -> None:
        """
        Validate inputs before execution.

        Can be overridden to implement custom validation logic.

        Args:
            app_instance: The BaseAppInstance object
            **kwargs: Additional parameters

        Raises:
            ValidationError: If validation fails
        """
        if not app_instance:
            from django.core.exceptions import ValidationError

            raise ValidationError("app_instance is required")
