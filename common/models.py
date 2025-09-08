from django.conf import settings
from django.contrib.auth.models import AbstractUser, User
from django.core.mail import send_mail
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
    EMAIL_TEMPLATES = {file_path: file_path for file_path in settings.EMAIL_TEMPLATES}
    from_email = models.EmailField(
        choices=[
            (settings.DEFAULT_FROM_EMAIL, settings.DEFAULT_FROM_EMAIL),
            (settings.EMAIL_FROM, settings.EMAIL_FROM),
        ]
    )
    to_user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    to_email = models.EmailField()
    subject = models.CharField(
        max_length=255,
        help_text="Subject of the email."
        "If there is already exists a ticket on Edge, you can use it's subject"
        " to track email history through it.",
    )
    message = models.TextField(
        help_text="Email message to be sent. If base template is selected, "
        "this will be rendered using the template. You can use HTML tags here.",
        blank=True,
        null=True,
        default="",
    )
    template = models.CharField(max_length=100, choices=EMAIL_TEMPLATES, null=True, blank=True)
    status = models.CharField(choices=[("sent", "Sent"), ("failed", "Failed")], default="pending", max_length=10)
    created_at = models.DateTimeField(auto_now_add=True)

    def send_email(self):
        message = self.message
        html_message = None
        if self.template:
            # If a template is selected, render the message using the template

            html_message = render_to_string(self.template, {"message": self.message, "user": self.to_user})
            message = html_message  # Use the rendered HTML message as the plain text message
        else:
            if not message:
                raise ValueError("Message cannot be empty if no template is selected.")
        send_mail(
            subject=self.subject,
            message=message,
            from_email=self.from_email,
            recipient_list=[self.to_email, settings.DEFAULT_FROM_EMAIL],
            html_message=html_message,
            fail_silently=False,
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
