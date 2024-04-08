import time

from django.conf import settings
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.utils import timezone

from studio.celery import app
from studio.helpers import do_pause_account
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
    threshold_alert_days = threshold_days - 30

    # The cutoff date for pausing dormant users
    threshold_pause = timezone.now() - timezone.timedelta(days=threshold_days)

    # The cutoff date for emailing and warning dormant users
    threshold_alert = timezone.now() - timezone.timedelta(days=threshold_alert_days)

    logger.info(f"Running task alert_pause_dormant_users using threshold {threshold_days} days")

    # Get users set as active and who have not logged in since threshold_alert
    dormant_users = User.objects.filter(last_login__lte=threshold_alert, is_active=True)

    for user in dormant_users:
        if user.email_verification_table is not None:
            # This user has not verified their email. Skip.
            logger.debug(f"Skipping user {user.id} who has not verified their email")
            continue

        # Now check if this user should be sent a warning email or be deactivated

        if user.groups.filter(name="pending_dormant_users").exists():
            # The user has been added to the pending_dormant_users group
            # The user has been warned, so if the full threshold duration has passed,
            # then pause the user account
            logger.debug(f"User {user.id} has previously been warned (belongs to the pending_dormant_users group).")

            if user.last_login < threshold_pause:
                # This user has not logged in since threshold_pause so pause the account
                logger.info(
                    f"User {user.id} has been warned but not logged in since threshold_pause, so pausing the account."
                )
                do_pause_account(user.id)

        else:
            # The user has not been sent a warning email
            # Send it now
            logger.info(
                f"User {user.id} has not logged in since {threshold_alert_days} days ago. Warning the user by email."
            )

            send_mail(
                "Please sign in to SciLifeLab Serve to keep your account active",
                "Your user account at SciLifeLab Serve has not been signed into for a long time. "
                "Please sign in to SciLifeLab Serve to keep your user account active.",
                settings.EMAIL_HOST_USER,
                [user.email],
                fail_silently=False,
            )
