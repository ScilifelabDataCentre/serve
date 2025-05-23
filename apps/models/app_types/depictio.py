from django.db import models

from apps.models import AppInstanceManager, BaseAppInstance, SocialMixin


class DepictioAppManager(AppInstanceManager):
    model_type = "depictio"


class DepictioInstance(BaseAppInstance, SocialMixin):
    objects = DepictioAppManager()
    ACCESS_TYPES = (("public", "Public"),)
    access = models.CharField(max_length=20, default="project", choices=ACCESS_TYPES)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def get_k8s_values(self):
        k8s_values = super().get_k8s_values()
        k8s_values["commonLabels"] = {
            "release": self.subdomain.subdomain,
            "app": "depictio",
            "project": self.project.slug,
        }
        k8s_values["tracking"] = {
            "ingress": {
                "enabled": True,
                "ingressClassName": "nginx",
                "hostname": self.url.split("://")[1] if self.url is not None else self.url,
            },
            "podLabels": {
                "type": "app",
            },
            "resources": {
                "requests": {"cpu": "1", "memory": "1Gi", "ephemeral-storage": "1Gi"},
                "limits": {"cpu": "2", "memory": "2Gi", "ephemeral-storage": "2Gi"},
            },
            "pdb": {"create": False},
        }
        k8s_values["run"] = {
            "resources": {
                "requests": {"cpu": "1", "memory": "1Gi", "ephemeral-storage": "1Gi"},
                "limits": {"cpu": "2", "memory": "2Gi", "ephemeral-storage": "2Gi"},
            }
        }

        k8s_values["permission"] = str(self.access)
        return k8s_values

    class Meta:
        verbose_name = "Depictio App Instance"
        verbose_name_plural = "Depictio App Instances"
        permissions = [("can_access_app", "Can access app service")]
