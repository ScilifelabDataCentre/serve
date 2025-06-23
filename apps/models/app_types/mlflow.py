from django.db import models
from django.utils.crypto import get_random_string

from apps.models import AppInstanceManager, BaseAppInstance


class MlflowAppManager(AppInstanceManager):
    model_type = "mlflow"


class MLFlowInstance(BaseAppInstance):
    objects = MlflowAppManager()
    ACCESS_TYPES = (("project", "Project"),)
    access = models.CharField(max_length=20, default="project", choices=ACCESS_TYPES)
    upload_size = 1000  # MB

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
                "clientMaxBodySize": f"{self.upload_size}M",
            },
            "podLabels": {
                "type": "app",
            },
            "resources": {
                "requests": {"cpu": "1", "memory": "1Gi", "ephemeral-storage": "1Gi"},
                "limits": {"cpu": "8", "memory": "16Gi", "ephemeral-storage": "30Gi"},
            },
            "pdb": {"create": False},
            # This fixes this issue:
            # https://mlflow.org/docs/2.21.3/tracking/server#handling-timeout-when-uploadingdownloading-large-artifacts
            "extraArgs": {'--gunicorn-opts="--timeout=360"'},
        }
        k8s_values["run"] = {
            "resources": {
                "requests": {"cpu": "1", "memory": "1Gi", "ephemeral-storage": "1Gi"},
                "limits": {"cpu": "8", "memory": "16Gi", "ephemeral-storage": "30Gi"},
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
