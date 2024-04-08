import time

from django.conf import settings
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.utils import timezone

from studio.celery import app
from studio.utils import get_logger

logger = get_logger(__name__)

ADMIN_EMAIL = "serve@scilifelab.se"


@app.task
def handle_deleted_users():
    """
    Handles deleted user accounts.

    Using a threshold of 12 months. If the user deleted their account longer ago, then it is handled.
    Initially, user accounts deleted more than 12 months ago will trigger an email to Serve admins
    for manual processing.

    TODO: Make threshold_days a variable in settings.py
    """

    threshold_days = 365
    threshold_time = timezone.now() - timezone.timedelta(days=threshold_days)

    logger.info(f"Running task handle_deleted_users using threshold {threshold_days} days")

    # Get all inactive users
    inactive_users = User.objects.filter(is_active=False)

    for user in inactive_users:
        if user.userprofile.deleted_on is None:
            # This user was not deleted. It is inactive for another reason.
            continue

        if user.userprofile.deleted_on <= threshold_time:
            # The user was deleted over threshold days ago
            # Send an email to Serve admins
            logger.warn(
                f"User {user.id} was deleted over {threshold_days} days ago. Now sending email to Serve admins."
            )

            send_mail(
                "Remove deleted user from SciLifeLab Serve",
                f"The user with id {user.id} deleted their account over {threshold_days} days ago. "
                "Please permanently remove the user from SciLifeLab Serve according to the routines.",
                settings.EMAIL_HOST_USER,
                [ADMIN_EMAIL],
                fail_silently=False,
            )

        else:
            # The user was deleted too recently to be handled. Simply log and exit.
            logger.info(f"User {user.id} was deleted less than {threshold_days} days ago. Exiting.")


@app.task
def alert_pause_dormant_users():
    """
    Handles dormant user accounts.
    The term dormant is used rather than inactive because of the overuse of the term inactive.

    Dormant user means that the user has not logged into Serve for 2 years.
    One month before this duration, the user is sent an email with instructions to login.
    After the 2 year duration has passed, the user account is deactivated.

    TODO: Make threshold_days a variable in settings.py
    """

    threshold_days = 2 * 365

    # The cutoff date for pausing dormant users
    threshold_pause = timezone.now() - timezone.timedelta(days=threshold_days + 30)

    # The cutoff date for emailing and warning dormant users
    # threshold_alert = timezone.now() - timezone.timedelta(days=threshold_days)

    logger.info(f"Running task alert_pause_dormant_users using threshold {threshold_days} days")

    # Get users set as active and who have not logged in since threshold_alert
    dormant_users = User.objects.filter(last_login__lte=threshold_pause, is_active=True)

    for user in dormant_users:
        if user.email_verification_table is not None:
            # This user has not verified their email. Skip.
            logger.debug(f"Skipping user {user.id} who has not verified their email")
            continue

        if user.last_login > threshold_pause:
            # This user has logged in since threshold_pause
            # TODO: consider instead adding a group and using it to track alerts to users
            # Users pending being paused
            # Group: PendingPausing
            pass
