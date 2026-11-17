from datetime import timedelta

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from common.models import MaintenanceMode
from studio.utils import get_logger

from .models import MaintenanceWindow

logger = get_logger(__name__)

ACTIVE_STATUSES = [
    MaintenanceWindow.Status.SCHEDULED,
    MaintenanceWindow.Status.IN_PROGRESS,
]

AUTO_MESSAGE_TEMPLATE = (
    "On {date} we will perform a planned upgrade of the cluster. "
    "Apps and other services may be temporarily unavailable during this day. "
    "We start maintenance at the beginning of the day, and it could last all day."
)


def build_auto_message(window):
    return AUTO_MESSAGE_TEMPLATE.format(date=window.date.strftime("%Y-%m-%d"))


@shared_task
def sync_maintenance_messages():
    """
    Shows an automatic maintenance message the day before a scheduled maintenance
    window, and removes it and marks the window as completed once the window has passed.
    Only removes messages that exactly match the automatically generated text and other properties,
    so manually added or modified messages are preserved.
    """
    today = timezone.localdate()
    tomorrow = today + timedelta(days=1)

    # Clean up MaintenanceWindow finished
    # Fetch MaintenanceWindows regardless of their status to check for leftover auto-generated messages
    finished = MaintenanceWindow.objects.filter(date__lt=today)

    for window in finished:
        try:
            _complete_window(window)
        except Exception:
            logger.exception("Failed to clean up message for maintenance window %s", window.pk)

    # create MaintenanceMode if the maintenance is happening tomorrow
    upcoming = MaintenanceWindow.objects.filter(date=tomorrow, status=MaintenanceWindow.Status.SCHEDULED)

    for window in upcoming:
        try:
            _announce_window(window)
        except Exception:
            logger.exception("Failed to create message for maintenance window %s", window.pk)


def _complete_window(window):
    """
    Removes the message with exactly matching properties and marks the window as completed.
    Also marks MaintenanceWindows which have been left unchanged.
    """
    text = build_auto_message(window)
    with transaction.atomic():
        deleted, _ = MaintenanceMode.objects.filter(
            login_and_signup_disabled=False,
            message_in_header=text,
            message_in_footer="",
            message_in_project_dashboard="",
        ).delete()
        if deleted:
            logger.info("Deleted MaintenanceMode for window %s", window.pk)
        if window.status in ACTIVE_STATUSES:
            _mark_completed(window)
            logger.info("Marked MaintenanceWindow %s as completed.", window.pk)


def _announce_window(window):
    """
    Create a message for tomorrow's scheduled maintenance.
    Does not create it if there are already messages.
    """
    with transaction.atomic():
        # no new message added if there is already maintenance messages
        if MaintenanceMode.objects.exists():
            logger.info(
                "A maintenance message already exists; skipped window date:%s start time:%s",
                window.date.strftime("%Y-%m-%d"),
                window.start_time,
            )
            return
        text = build_auto_message(window)
        MaintenanceMode.objects.create(message_in_header=text)


def _mark_completed(window):
    window.status = MaintenanceWindow.Status.COMPLETED
    window.save(update_fields=["status"])
