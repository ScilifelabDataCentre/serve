from django.contrib.auth.models import AbstractUser, User
from django.db import models


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    affiliation = models.CharField(max_length=100, blank=True)
    department = models.CharField(max_length=100, blank=True)
    why_account_needed = models.TextField(max_length=1000, blank=True)
    is_approved = models.BooleanField(default=False)
    note = models.TextField(max_length=1000, blank=True)

    def __str__(self):
        return f"{self.user.email}"
