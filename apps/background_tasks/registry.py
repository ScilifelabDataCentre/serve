"""
Task registry for managing background tasks.
"""

from collections.abc import Callable

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
        self._tasks: dict[str, type[BaseBackgroundTask]] = {}

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

            # Store the metadata on the class so configuration lives in one place.
            cls.task_name = name
            cls.is_critical = is_critical
            cls.execution_order = execution_order
            cls.app_types = tuple(app_types) if app_types else None

            self._tasks[name] = cls

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
        return self._tasks.get(name)

    def get_task_info(self, name: str) -> type[BaseBackgroundTask] | None:
        """
        Get complete task information by name.

        Args:
            name: Task name

        Returns:
            Task class or None if not found
        """
        return self._tasks.get(name)

    def get_all_tasks(self) -> dict[str, type[BaseBackgroundTask]]:
        """
        Get all registered tasks.

        Returns:
            Dict mapping task names to task info
        """
        return self._tasks.copy()

    def get_tasks_for_app(self, app_slug: str) -> list[type[BaseBackgroundTask]]:
        """
        Get all tasks applicable to a specific app type.

        Args:
            app_slug: App type slug (e.g., 'customapp', 'jupyter')

        Returns:
            List of task classes sorted by execution_order
        """
        applicable: list[type[BaseBackgroundTask]] = []

        for task_class in self._tasks.values():
            # If app_types is None, task applies to all apps
            # Otherwise, check if app_slug is in the list
            if task_class.app_types is None or app_slug in task_class.app_types:
                applicable.append(task_class)

        # Sort by execution order (and name for determinism)
        applicable.sort(key=lambda c: (c.execution_order, c.task_name))
        return applicable

    def get_tasks_by_order(self, app_slug: str) -> dict[int, list[type[BaseBackgroundTask]]]:
        """
        Get tasks grouped by execution order.

        Tasks with the same execution_order should run in parallel.

        Args:
            app_slug: App type slug

        Returns:
            Dict mapping execution_order to list of tasks
        """
        tasks = self.get_tasks_for_app(app_slug)
        grouped: dict[int, list[type[BaseBackgroundTask]]] = {}

        for task_class in tasks:
            order = task_class.execution_order
            if order not in grouped:
                grouped[order] = []
            grouped[order].append(task_class)

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
