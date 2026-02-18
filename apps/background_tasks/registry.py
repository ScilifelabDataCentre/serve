"""
Task registry for managing background tasks.
"""

from collections.abc import Callable
from typing import Any

from studio.utils import get_logger

from .base import BaseBackgroundTask

logger = get_logger(__name__)


class BackgroundTaskRegistry:
    """
    Registry for background tasks that can be executed for app instances.

    Tasks are registered using the @register decorator and can be
    retrieved by name or filtered by app type.
    """

    def __init__(self):
        self._tasks: dict[str, dict[str, Any]] = {}

    def register(
        self,
        name: str,
        is_critical: bool = False,
        execution_order: int = 0,
        app_types: list[str] | None = None,
    ) -> Callable[[type[BaseBackgroundTask]], type[BaseBackgroundTask]]:
        """
        Decorator to register a task class.

        Args:
            name: Unique identifier for the task
            is_critical: If True, task failure blocks deployment
            execution_order: Order of execution (lower runs first, same order runs parallel)
            app_types: List of app slugs this task applies to. None = all apps.

        Example:
            @TASK_REGISTRY.register(
                name='validate_docker_image',
                is_critical=True,
                execution_order=1,
                app_types=['customapp', 'jupyter']
            )
            class DockerImageValidator(BaseBackgroundTask):
                def execute(self, app_instance, **kwargs):
                    # validation logic here
                    return {"valid": True}
        """

        def decorator(cls: type[BaseBackgroundTask]) -> type[BaseBackgroundTask]:
            if name in self._tasks:
                logger.warning(f"Task '{name}' is already registered. Overwriting.")

            self._tasks[name] = {
                "class": cls,
                "is_critical": is_critical,
                "execution_order": execution_order,
                "app_types": app_types,  # None means all app types
            }

            logger.debug(f"Registered background task: {name}")
            return cls

        return decorator

    def get_task_class(self, name: str) -> type[BaseBackgroundTask] | None:
        """
        Get a task class by name.

        Args:
            name: Task name

        Returns:
            Task class or None if not found
        """
        task_info = self._tasks.get(name)
        return task_info["class"] if task_info else None

    def get_task_info(self, name: str) -> dict[str, Any] | None:
        """
        Get complete task information by name.

        Args:
            name: Task name

        Returns:
            Dict with task info or None if not found
        """
        return self._tasks.get(name)

    def get_all_tasks(self) -> dict[str, dict[str, Any]]:
        """
        Get all registered tasks.

        Returns:
            Dict mapping task names to task info
        """
        return self._tasks.copy()

    def get_tasks_for_app(self, app_slug: str) -> list[dict[str, Any]]:
        """
        Get all tasks applicable to a specific app type.

        Args:
            app_slug: App type slug (e.g., 'customapp', 'jupyter')

        Returns:
            List of task info dicts sorted by execution_order
        """
        applicable_tasks = []

        for name, task_info in self._tasks.items():
            app_types = task_info.get("app_types")

            # If app_types is None, task applies to all apps
            # Otherwise, check if app_slug is in the list
            if app_types is None or app_slug in app_types:
                applicable_tasks.append(
                    {
                        "name": name,
                        **task_info,
                    }
                )

        # Sort by execution order
        applicable_tasks.sort(key=lambda x: x["execution_order"])

        return applicable_tasks

    def get_tasks_by_order(self, app_slug: str) -> dict[int, list[dict[str, Any]]]:
        """
        Get tasks grouped by execution order.

        Tasks with the same execution_order should run in parallel.

        Args:
            app_slug: App type slug

        Returns:
            Dict mapping execution_order to list of tasks
        """
        tasks = self.get_tasks_for_app(app_slug)
        grouped: dict[int, list[dict[str, Any]]] = {}

        for task in tasks:
            order = task["execution_order"]
            if order not in grouped:
                grouped[order] = []
            grouped[order].append(task)

        return grouped

    def unregister(self, name: str) -> bool:
        """
        Unregister a task by name.

        Args:
            name: Task name

        Returns:
            True if task was unregistered, False if not found
        """
        if name in self._tasks:
            del self._tasks[name]
            logger.debug(f"Unregistered background task: {name}")
            return True
        return False

    def is_registered(self, name: str) -> bool:
        """
        Check if a task is registered.

        Args:
            name: Task name

        Returns:
            True if registered, False otherwise
        """
        return name in self._tasks


# Global registry instance
TASK_REGISTRY = BackgroundTaskRegistry()
