from django.db import models

from apps.models import AppInstanceManager, BaseAppInstance


class MlflowAppManager(AppInstanceManager):
    model_type = "mlflow"


class MLFlowInstance(BaseAppInstance):
    objects = MlflowAppManager()
    ACCESS_TYPES = (("project", "Project"),)
    access = models.CharField(max_length=20, default="project", choices=ACCESS_TYPES)

    def get_k8s_values(self):
        k8s_values = super().get_k8s_values()
        k8s_values["tracking"] = {
            "auth": {"enabled": True},
            "ingress": {
                "enabled": True,
                "ingressClassName": "nginx",
                "hostname": self.url.split("://")[1] if self.url is not None else self.url,
            },
            "pdb": {"create": False},
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
