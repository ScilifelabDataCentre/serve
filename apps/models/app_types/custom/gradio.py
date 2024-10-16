from ... import AppInstanceManager, BaseAppInstance
from .base import AbstractCustomAppInstance


class GradioAppInstanceManager(AppInstanceManager):
    model_type = "gradioappinstance"


class GradioInstance(AbstractCustomAppInstance, BaseAppInstance):
    objects = GradioAppInstanceManager()

    def get_k8s_values(self):
        k8s_values = super().get_k8s_values()
        # TODO Change this to actual command to run gradio app
        k8s_values["appconfig"]["startupCommand"] = "python /app/main.py"
        return k8s_values

    class Meta:
        verbose_name = "Gradio App Instance"
        verbose_name_plural = "Gradio App Instances"
        permissions = [("can_access_app", "Can access app service")]
