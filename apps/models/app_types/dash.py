from django.db import models

from apps.models import (
    AppInstanceManager,
    BaseAppInstance,
    LogsEnabledMixin,
    SocialMixin,
)
from apps.models.app_types.custom.custom import validate_default_url_subpath


class DashInstanceManager(AppInstanceManager):
    model_type = "dashinstance"


class DashInstance(BaseAppInstance, SocialMixin, LogsEnabledMixin):
    default_url_subpath = models.CharField(
        validators=[validate_default_url_subpath], max_length=255, default="", blank=True
    )
    objects = DashInstanceManager()
    ACCESS_TYPES = (
        ("project", "Project"),
        (
            "private",
            "Private",
        ),
        ("public", "Public"),
        ("link", "Link"),
    )
    access = models.CharField(max_length=20, default="project", choices=ACCESS_TYPES)
    port = models.IntegerField(default=8000)
    image = models.CharField(max_length=255)

    def get_k8s_values(self):
        k8s_values = super().get_k8s_values()

        k8s_values["permission"] = str(self.access)
        k8s_values["appconfig"] = dict(port=self.port, image=self.image)
        return k8s_values

    class Meta:
        verbose_name = "Dash App Instance"
        verbose_name_plural = "Dash App Instances"
        permissions = [("can_access_app", "Can access app service")]
