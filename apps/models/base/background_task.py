from django.db import models
from django.utils import timezone

from studio.utils import get_logger

logger = get_logger(__name__)


TASK_STATUS_CHOICES = [
    ("pending", "Pending"),
    ("running", "Running"),
    ("success", "Success"),
    ("failed", "Failed"),
    ("retrying", "Retrying"),
]

TASK_TYPE_CHOICES = [
    ("validation", "Validation"),
    ("external_api", "External API"),
    ("post_deploy", "Post Deploy"),
]


class BackgroundTask(models.Model):
    """
    Tracks execution of background tasks associated with app instances.
    Used for pre-deployment validations, external API calls, and other async operations.
    """

    # Relationship to app instance
    app_instance = models.ForeignKey(
        "BaseAppInstance",
        on_delete=models.CASCADE,
        related_name="background_tasks",
        help_text="The app instance this task is associated with",
    )

    # Task identification
    task_name = models.CharField(
        max_length=255,
        help_text="Registered task identifier (e.g., 'validate_docker_image')",
        db_index=True,
    )

    task_type = models.CharField(
        max_length=50,
        choices=TASK_TYPE_CHOICES,
        default="validation",
        help_text="Category of the task",
        db_index=True,
    )

    # Task execution metadata
    status = models.CharField(
        max_length=50,
        choices=TASK_STATUS_CHOICES,
        default="pending",
        help_text="Current status of the task",
        db_index=True,
    )

    is_critical = models.BooleanField(
        default=False,
        help_text="If True, failure of this task will block deployment",
    )

    execution_order = models.IntegerField(
        default=0,
        help_text="Order in which task should run. Lower numbers run first. Tasks with same order run in parallel.",
    )

    # Results and errors
    result_data = models.JSONField(
        null=True,
        blank=True,
        help_text="JSON data containing task output/results",
    )

    error_message = models.TextField(
        blank=True,
        default="",
        help_text="Error message if task failed",
    )

    # Retry configuration
    retry_count = models.IntegerField(
        default=0,
        help_text="Number of times this task has been retried",
    )

    max_retries = models.IntegerField(
        default=3,
        help_text="Maximum number of retry attempts",
    )

    # Timing information
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When the task was created",
    )

    started_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the task execution started",
    )

    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the task execution completed",
    )

    # Celery integration
    celery_task_id = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Celery task ID for tracking",
        db_index=True,
    )

    class Meta:
        ordering = ["execution_order", "created_at"]
        indexes = [
            models.Index(fields=["app_instance", "status"]),
            models.Index(fields=["task_name", "status"]),
            models.Index(fields=["created_at"]),
        ]
        verbose_name = "Background Task"
        verbose_name_plural = "Background Tasks"

    def __str__(self):
        return f"{self.task_name} ({self.status}) - App: {self.app_instance_id}"

    def mark_as_running(self, celery_task_id=None):
        """Mark task as running and record start time."""
        self.status = "running"
        self.started_at = timezone.now()
        if celery_task_id:
            self.celery_task_id = celery_task_id
        self.save(update_fields=["status", "started_at", "celery_task_id"])
        logger.info(f"BackgroundTask {self.id} ({self.task_name}) marked as running")

    def mark_as_success(self, result_data=None):
        """Mark task as successful and record completion time."""
        self.status = "success"
        self.completed_at = timezone.now()
        # Persist empty dicts/lists too (but keep None meaning "no data").
        if result_data is not None:
            self.result_data = result_data
        self.save(update_fields=["status", "completed_at", "result_data"])
        logger.info(f"BackgroundTask {self.id} ({self.task_name}) completed successfully")

    def mark_as_failed(self, error_message: str, result_data=None):
        """Mark task as failed and record error (optionally structured)."""
        self.status = "failed"
        self.completed_at = timezone.now()
        self.error_message = error_message
        if result_data is not None:
            self.result_data = result_data
            self.save(update_fields=["status", "completed_at", "error_message", "result_data"])
        else:
            self.save(update_fields=["status", "completed_at", "error_message"])
        logger.error(f"BackgroundTask {self.id} ({self.task_name}) failed: {error_message}")

    def mark_as_retrying(self):
        """Mark task as retrying and increment retry count."""
        self.status = "retrying"
        self.retry_count += 1
        self.save(update_fields=["status", "retry_count"])
        logger.info(f"BackgroundTask {self.id} ({self.task_name}) retrying (attempt {self.retry_count})")

    def can_retry(self):
        """Check if task can be retried."""
        return self.retry_count < self.max_retries

    def get_duration(self):
        """Calculate task execution duration."""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None

    def get_status_display_class(self):
        """Return CSS class for status display."""
        status_classes = {
            "pending": "secondary",
            "running": "primary",
            "success": "success",
            "failed": "danger",
            "retrying": "warning",
        }
        return status_classes.get(self.status, "secondary")
