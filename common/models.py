from django.conf import settings
from django.contrib.auth.models import AbstractUser, User
from django.db import models

from studio.utils import get_logger

logger = get_logger(__name__)


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    affiliation = models.CharField(max_length=100, blank=True)
    department = models.CharField(max_length=100, blank=True)
    deleted_on = models.DateTimeField(null=True, blank=True)
    why_account_needed = models.TextField(max_length=1000, blank=True)

    is_approved = models.BooleanField(default=False)
    """This field marks if the user is affiliated with the university or not"""

    note = models.TextField(max_length=1000, blank=True)

    def __str__(self):
        return f"{self.user.email}"


class EmailVerificationTable(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    token = models.CharField(max_length=100)

    def send_verification_email(self):
        from .tasks import send_verification_email_task

        send_verification_email_task(self.user.email, self.token)


class FixtureVersion(models.Model):
    filename = models.CharField(max_length=255, unique=True)
    hash = models.CharField(max_length=64)  # Length of a SHA-256 hash

    def __str__(self):
        return f"{self.filename} - {self.hash}"


class MaintenanceMode(models.Model):
    login_and_signup_disabled = models.BooleanField(default=False)
    message_in_header = models.TextField(max_length=1000, blank=True)
    message_in_footer = models.TextField(max_length=1000, blank=True)
