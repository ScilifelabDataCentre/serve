from django.conf import settings
from django.contrib.auth.models import Group, User
from django.core.mail import EmailMessage, send_mail
from django.template.loader import render_to_string
from django.utils import timezone

from studio.celery import app
from studio.helpers import do_pause_account
from studio.settings import DOMAIN
from studio.utils import get_logger

from .models import EmailVerificationTable

logger = get_logger(__name__)

ADMIN_EMAIL = "serve@scilifelab.se"


@app.task
def handle_deleted_users() -> None:
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

            send_email_task(
                "Remove deleted user from SciLifeLab Serve",
                f"The user with id {user.id} deleted their account over {threshold_days} days ago. "
                "Please permanently remove the user from SciLifeLab Serve according to the routines.",
                [ADMIN_EMAIL],
            )

        else:
            # The user was deleted too recently to be handled. Simply log and exit.
            logger.info(f"User {user.id} was deleted less than {threshold_days} days ago. Exiting.")


@app.task
def alert_pause_dormant_users() -> None:
    """
    Handles dormant user accounts.
    The term dormant is used rather than inactive because of the overuse of the term inactive.

    Dormant user means that the user has not logged into Serve for 2 years.
    Two weeks before this duration, the user is sent an email with instructions to login.
    After the 2 year duration has passed, the user account is deactivated.

    TODO: Make threshold_days a variable in settings.py
    """

    threshold_days = 2 * 365
    threshold_alert_days = threshold_days - 14

    # The cutoff date for pausing dormant users
    threshold_pause = timezone.now() - timezone.timedelta(days=threshold_days)

    # The cutoff date for emailing and warning dormant users
    threshold_alert = timezone.now() - timezone.timedelta(days=threshold_alert_days)

    logger.info(
        f"Running task alert_pause_dormant_users using thresholds alert after {threshold_alert_days} days, pause after \
        {threshold_days} days"
    )

    # Get users set as active and who have not logged in since threshold_alert
    # Because new registered users who have verified their emails are set to active but without
    # a last login date, we do this by excluding users who have logged in after threshold_alert
    # We also exclude staff members
    dormant_users = (
        User.objects.filter(is_active=True)
        .exclude(last_login__gte=threshold_alert)
        .exclude(date_joined__gte=threshold_alert)
        .exclude(is_staff=True)
    )

    logger.info(f"Found {len(dormant_users)} dormant users to process")

    for user in dormant_users:
        email_verification_table = EmailVerificationTable.objects.filter(user_id=user.id).first()

        if email_verification_table is not None:
            # This user has not verified their email. Skip.
            logger.debug(f"Skipping user {user.id} who has not verified their email")
            continue

        # Now check if this user should be sent a warning email or be deactivated

        if user.groups.filter(name="pending_dormant_users").exists():
            # The user has been added to the pending_dormant_users group
            # The user has been warned, so if the full threshold duration has passed,
            # then pause the user account
            logger.info(f"User {user.id} has previously been warned (belongs to the pending_dormant_users group)")

            if user.last_login is None or user.last_login < threshold_pause:
                # This user has been warned and has not logged in since threshold_pause (or never logged in)
                # so pause the account
                logger.info(
                    f"User {user.id} has been warned but not logged in since {threshold_pause=}, so pausing the user."
                )
                do_pause_account(user.id)

        else:
            # The user has not been sent a warning email. Sending it now
            logger.info(
                f"User {user.id} has not logged in since the limit {threshold_alert_days} days ago \
                    ({threshold_alert}). Sending a warning email."
            )

            send_email_task(
                "Please sign in to SciLifeLab Serve to keep your account active",
                "Your user account at SciLifeLab Serve (https://serve.scilifelab.se) has not been signed into for "
                "a long time. Please sign in to SciLifeLab Serve to keep your user account active. Otherwise your "
                "account will be paused after 2 weeks. If you want to access it again, you will need to get in touch "
                "with our support team to reactivate it.",
                [user.email],
                fail_silently=False,
            )

            # Add the user to the group
            group = Group.objects.get(name="pending_dormant_users")
            user.groups.add(group)


@app.task(ignore_result=True)
def send_email_task(
    subject: str,
    message: str,
    recipient_list: list[str],
    html_message: str | None = None,
    fail_silently: bool = False,
    from_email: str = settings.EMAIL_FROM,
) -> None:
    """
    Send message content if html_message is None, otherwise send html_message.
    """
    logger.info("Sending email to %s", recipient_list)
    mail_subject = subject
    mail_message = message if html_message is None else html_message
    email = EmailMessage(mail_subject, mail_message, from_email, to=recipient_list)
    email.content_subtype = "html" if html_message else "plain"
    email.send(fail_silently=fail_silently)


def send_verification_email_task(email: str, token: str) -> None:
    html_message = render_to_string(
        "registration/verify_email.html",
        {
            "token": token,
        },
    )
    logger.info("Sending verification email %s", email)
    send_email_task(
        subject="Verify your email address on SciLifeLab Serve",
        message=(
            f"You registered an account on SciLifeLab Serve ({DOMAIN}).\n"
            "Please click this link to verify your email address:"
            f" https://{DOMAIN}/verify/?token={token}"
            "\n\n"
            "SciLifeLab Serve team"
        ),
        html_message=html_message,
        recipient_list=[email],
    )
