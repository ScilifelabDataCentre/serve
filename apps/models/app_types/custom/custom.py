from django.db import models

from apps.models import AppInstanceManager, BaseAppInstance

from .base import AbstractCustomAppInstance


class CustomAppInstanceManager(AppInstanceManager):
    model_type = "customappinstance"


class CustomAppInstance(AbstractCustomAppInstance, BaseAppInstance):
    custom_default_url = models.CharField(max_length=255, default="", blank=True)
    objects = CustomAppInstanceManager()
