from apps.models import AppInstanceManager, BaseAppInstance

from .base import AbstractCustomAppInstance


class CustomAppInstanceManager(AppInstanceManager):
    model_type = "customappinstance"


class CustomAppInstance(AbstractCustomAppInstance, BaseAppInstance):
    objects = CustomAppInstanceManager()
