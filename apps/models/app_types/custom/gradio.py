from django.db import models

from ... import AppInstanceManager, BaseAppInstance
from .base import AbstractCustomAppInstance


class GradioAppInstanceManager(AppInstanceManager):
    model_type = "gradioappinstance"


class GradioInstance(AbstractCustomAppInstance, BaseAppInstance):
    objects = GradioAppInstanceManager()
    port = models.IntegerField(
        default=7860,
        help_text="Port that the Docker container exposes and the application runs on. This should be an integer between 3000-9999.",
    )

    def get_k8s_values(self):
        k8s_values = super().get_k8s_values()
        k8s_values["appconfig"]["startupCommand"] = "python main.py"
        return k8s_values

    class Meta:
        verbose_name = "Gradio App Instance"
        verbose_name_plural = "Gradio App Instances"
        permissions = [("can_access_app", "Can access app service")]
