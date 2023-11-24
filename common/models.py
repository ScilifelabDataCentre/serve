from django.conf import settings
from django.contrib.auth.models import AbstractUser, User
from django.core.mail import send_mail
from django.db import models


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    affiliation = models.CharField(max_length=100, blank=True)
    department = models.CharField(max_length=100, blank=True)
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
        send_mail(
            "Verify your email address",
            f"Please click the link below to verify your email address: http://localhost:8000/verify{self.token}",
            settings.EMAIL_HOST_USER,
            [self.user.email],
            fail_silently=False,
        )
