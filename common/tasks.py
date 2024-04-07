from django.core.mail import send_mail
from django.template.loader import render_to_string

from studio import settings
from studio.celery import app
from studio.settings import DOMAIN
from studio.utils import get_logger

logger = get_logger(__name__)


@app.task(ignore_result=True)
def send_email_task(subject, message, html_message, recipient_list):
    logger.info("Sending email to %s", recipient_list)
    send_mail(
        subject,
        message,
        settings.EMAIL_HOST_USER,
        recipient_list,
        html_message=html_message,
        fail_silently=False,
    )


def send_verification_email(email, token):
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
