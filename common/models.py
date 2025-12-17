from django.conf import settings
from django.contrib.auth.models import AbstractUser, User
from django.db import models
from django.template.loader import render_to_string

from studio.utils import get_logger

logger = get_logger(__name__)


class UserProfileManager(models.Manager):
    def create_user_profile(self, user: User):
        user_profile = self.create(user=user)
        return user_profile


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    affiliation = models.CharField(max_length=100, blank=True)
    department = models.CharField(max_length=100, blank=True)
    deleted_on = models.DateTimeField(null=True, blank=True)
    why_account_needed = models.TextField(max_length=1000, blank=True)

    is_approved = models.BooleanField(default=False)
    """This field marks if the user is affiliated with the university or not"""

    note = models.TextField(max_length=1000, blank=True)

    objects = UserProfileManager()

    def __str__(self):
        return f"{self.user.email}"


class EmailVerificationTable(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    token = models.CharField(max_length=100)
    date_created = models.DateTimeField(auto_now_add=True)

    def send_verification_email(self):
        from .tasks import send_verification_email_task

        send_verification_email_task(self.user.email, self.token)


class EmailSendingTable(models.Model):
    class EmailTemplate(models.TextChoices):
        account_enabled = "admin/email/account-enabled-email.html", "Account approved/enabled"
        user_not_swedish_uni = "admin/email/user-not-from-a-swedish-uni.html", "User not from a Swedish uni"

    from_email = models.EmailField(
        choices=[
            (settings.EMAIL_FROM, settings.EMAIL_FROM),
            (settings.ADMIN_EMAIL, settings.ADMIN_EMAIL),
        ],
        default=settings.ADMIN_EMAIL,
    )
    to_user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    to_email = models.EmailField(
        help_text="This field will indicate the email to which the email was sent after you hit 'Save'."
    )
    subject = models.CharField(
        max_length=255,
        help_text="Subject of the email. "
        "If there already exists a ticket on Edge, you can use its subject"
        " to track email history through it.",
        blank=False,
        null=False,
    )
    message = models.TextField(
        help_text="Type your message here if you want to write it manually. Alternatively, "
        "choose one of the templates.",
        blank=True,
        default="Dear X,\n\nKind regards, \nSciLifeLab Serve team",
    )
    template = models.CharField(
        max_length=100,
        choices=EmailTemplate.choices,
        help_text="Select a template if you do not want to type a message "
        "manually. If selected, anything in the Message field will be ignored.",
        null=True,
        blank=True,
    )
    status = models.CharField(
        choices=[("sent", "Sent"), ("failed", "Failed")],
        help_text="This field will indicate whether the email was successfully sent after you hit 'Save'.",
        default="pending",
        max_length=10,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def send_email(self):
        from common.tasks import send_email_task

        logger.info(f"Sending an email to {self.to_email} fron the admin panel email sending form.")

        html_message = None
        if self.template:
            html_message = render_to_string(
                self.template,
                {
                    "user_firstname": self.to_user.first_name,
                },
            )

        send_email_task(
            subject=self.subject,
            message=self.message,
            html_message=html_message,
            recipient_list=[self.to_email, settings.ADMIN_EMAIL],
            fail_silently=False,
            from_email=self.from_email,
        )


class FixtureVersion(models.Model):
    filename = models.CharField(max_length=255, unique=True)
    hash = models.CharField(max_length=64)  # Length of a SHA-256 hash

    def __str__(self):
        return f"{self.filename} - {self.hash}"


class MaintenanceMode(models.Model):
    login_and_signup_disabled = models.BooleanField(default=False)
    message_in_header = models.TextField(max_length=1000, blank=True)
    message_in_footer = models.TextField(max_length=1000, blank=True)
