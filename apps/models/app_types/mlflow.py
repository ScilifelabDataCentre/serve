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

    def save(self, *args, **kwargs):
        # Only for new instances
        if not self.pk:
            self.upload_size = 1000
        super().save(*args, **kwargs)

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
                "annotations": {"nginx.ingress.kubernetes.io/proxy-body-size": f"{self.upload_size}M"},
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
            "extraArgs": ['--gunicorn-opts="--timeout=360"'],
        }
        k8s_values["run"] = {
            "resources": {
                "requests": {"cpu": "1", "memory": "1Gi", "ephemeral-storage": "1Gi"},
                "limits": {"cpu": "8", "memory": "16Gi", "ephemeral-storage": "30Gi"},
            }
        }
        # https://github.com/bitnami/charts/tree/main/bitnami/minio#minio-parameters
        k8s_values["minio"] = {
            "pdb": {"create": False},
            "metrics": {"enabled": True},
            "image": {
                "repository": "bitnamilegacy/minio",
                "tag": "2025.6.13-debian-12-r0",
            },
        }
        k8s_values["postgresql"] = {
            "primary": {
                "pdb": {"create": False},
            },
            "readReplicas": {
                "pdb": {"create": False},
            },
            # https://github.com/bitnami/charts/tree/main/bitnami/postgresql#postgresql-common-parameters
            "image": {
                "repository": "bitnamilegacy/postgresql",
                "tag": "17.5.0-debian-12-r12",
            },
        }
        # 2025-08-15 We are forced to do this due to new bitnami policy
        # https://github.com/bitnami/containers/issues/83267
        k8s_values["image"] = {
            "repository": "bitnamilegacy/mlflow",
            "tag": "3.1.1-debian-12-r0",
        }
        k8s_values["gitImage"] = {"repository": "bitnamilegacy/git", "tag": "2.51.0"}
        k8s_values["volumePermissions"] = {
            "image": {
                "repository": "bitnamilegacy/os-shell",
                "tag": "12-debian-12-r47",
            }
        }
        k8s_values["waitContainer"] = {
            "image": {
                "repository": "bitnamilegacy/os-shell",
                "tag": "12-debian-12-r47",
            }
        }
        # This has to be done as we are overriding default images in the chart
        k8s_values["global"]["security"] = {"allowInsecureImages": True}
        return k8s_values

    class Meta:
        verbose_name = "MLFlow App Instance"
        verbose_name_plural = "MLFlow App Instances"
        permissions = [("can_access_app", "Can access app service")]
