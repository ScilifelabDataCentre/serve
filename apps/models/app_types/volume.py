from datetime import datetime, timedelta

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q

from apps.models import AppInstanceManager, BaseAppInstance


class VolumeInstanceManager(AppInstanceManager):
    model_type = "volumeinstance"


class VolumeInstance(BaseAppInstance):
    objects = VolumeInstanceManager()
    size = models.IntegerField(
        default=1, help_text="Size in GB", validators=[MinValueValidator(1), MaxValueValidator(100)]
    )

    def __str__(self):
        return f"{str(self.name)} ({self.project.name})"

    def get_k8s_values(self):
        k8s_values = super().get_k8s_values()
        k8s_values["volume"] = dict(size=f"{str(self.size)}Gi")
        return k8s_values

    class Meta:
        verbose_name = "Persistent Volume"
        verbose_name_plural = "Persistent Volumes"
        permissions = [("can_access_app", "Can access app service")]
