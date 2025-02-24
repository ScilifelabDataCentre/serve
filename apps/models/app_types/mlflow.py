from django.db import models
from django.utils.crypto import get_random_string

from apps.models import AppInstanceManager, BaseAppInstance


class MlflowAppManager(AppInstanceManager):
    model_type = "mlflow"


class MLFlowInstance(BaseAppInstance):
    objects = MlflowAppManager()
    ACCESS_TYPES = (("project", "Project"),)
    access = models.CharField(max_length=20, default="project", choices=ACCESS_TYPES)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def get_k8s_values(self):
        k8s_values = super().get_k8s_values()
        k8s_values["commonLabels"] = {
            "release": self.subdomain.subdomain,
            "app": "mlflow",
            "project": self.project.slug,
        }
        k8s_values["tracking"] = {
            "auth": {"enabled": True, "username": get_random_string(10), "password": get_random_string(20)},
            "ingress": {
                "enabled": True,
                "ingressClassName": "nginx",
                "hostname": self.url.split("://")[1] if self.url is not None else self.url,
            },
            "podLabels": {
                "type": "app",
            },
            "resources": {
                "requests": {"cpu": "1", "memory": "512Mi", "ephemeral-storage": "512Mi"},
                "limits": {"cpu": "2", "memory": "1Gi", "ephemeral-storage": "1Gi"},
            },
            "pdb": {"create": False},
        }
        k8s_values["run"] = {
            "resources": {
                "requests": {"cpu": "1", "memory": "512Mi", "ephemeral-storage": "512Mi"},
                "limits": {"cpu": "2", "memory": "1Gi", "ephemeral-storage": "1Gi"},
            }
        }
        k8s_values["minio"] = {"pdb": {"create": False}}
        k8s_values["postgresql"] = {
            "primary": {
                "pdb": {"create": False},
            },
            "readReplicas": {
                "pdb": {"create": False},
            },
        }
        return k8s_values

    class Meta:
        verbose_name = "MLFlow App Instance"
        verbose_name_plural = "MLFlow App Instances"
        permissions = [("can_access_app", "Can access app service")]
