from django.conf import settings
from django.db import models

from apps.models import AppInstanceManager, BaseAppInstance, SocialMixin


class DepictioAppManager(AppInstanceManager):
    model_type = "depictio"


class DepictioInstance(BaseAppInstance, SocialMixin):
    objects = DepictioAppManager()
    ACCESS_TYPES = (("public", "Public"), ("project", "Project"), ("link", "Link"), ("private", "Private"))
    access = models.CharField(
        max_length=20,
        default="project",
        choices=ACCESS_TYPES,
        help_text="The chosen Permission level determines who can access the application.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def get_k8s_values(self):
        k8s_values = super().get_k8s_values()
        k8s_values["commonLabels"] = {
            "release": self.subdomain.subdomain,
            "app": "depictio",
            "project": self.project.slug,
        }
        k8s_values["permission"] = str(self.access)

        base_annotations = {
            "nginx.ingress.kubernetes.io/custom-http-errors": "503,502",
            "nginx.ingress.kubernetes.io/default-backend": "nginx-errors",
            "nginx.ingress.kubernetes.io/proxy-body-size": f"{self.upload_size}M",
        }

        if self.access in ("private", "project"):
            k8s_values["ingress"]["annotations"] = {
                **base_annotations,
                "nginx.ingress.kubernetes.io/auth-url": f"{settings.AUTH_PROTOCOL}://{settings.AUTH_DOMAIN}:8080/auth/?release={self.subdomain.subdomain}",
                "nginx.ingress.kubernetes.io/auth-signin": f"https://{settings.DOMAIN}/accounts/login/",
                "nginx.ingress.kubernetes.io/auth-signin-redirect-param": "next",
            }
        else:
            k8s_values["ingress"]["annotations"] = base_annotations

        k8s_values["backend"] = {
            "ingress": {
                "separateRoute": True,
                "inheritDefaultAnnotations": False,
                "annotations": base_annotations,
            }
        }
        k8s_values["minio"] = {
            "ingress": {
                "separateRoute": True,
                "inheritDefaultAnnotations": False,
                "annotations": base_annotations,
            }
        }

        if self.access in ("private", "project"):
            k8s_values["backend"].update({"env": {"DEPICTIO_AUTH_SINGLE_USER_MODE": "true"}})
            k8s_values["frontend"] = {"env": {"DEPICTIO_AUTH_SINGLE_USER_MODE": "true"}}
        else:
            k8s_values["backend"].update(
                {"env": {"DEPICTIO_AUTH_PUBLIC_MODE": "true", "DEPICTIO_AUTH_SINGLE_USER_MODE": "false"}}
            )
            k8s_values["frontend"] = {
                "env": {"DEPICTIO_AUTH_PUBLIC_MODE": "true", "DEPICTIO_AUTH_SINGLE_USER_MODE": "false"}
            }

        return k8s_values

    class Meta:
        verbose_name = "Depictio App Instance"
        verbose_name_plural = "Depictio App Instances"
        permissions = [("can_access_app", "Can access app service")]
