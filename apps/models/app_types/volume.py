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
        default=1, help_text="Size in GB", validators=[MinValueValidator(1), MaxValueValidator(100000)]
    )

    previous_size = models.IntegerField(
        null=True,
        blank=True,
        help_text="Size before the most recent resize, until the cluster confirms or refuses it.",
    )

    def __str__(self):
        return f"{str(self.name)} ({self.project.name})"

    def reconcile_resize(self) -> int | None:
        """Roll the size back if the cluster refused the last resize.

        Returns the restored size, or None if there was nothing to do or no verdict yet.
        """
        if self.previous_size is None:
            return None

        success = ((self.info or {}).get("helm") or {}).get("success")

        if success is None:
            return None

        if success:
            self.previous_size = None
            self.save(update_fields=["previous_size"])

            return None

        restored = self.previous_size
        self.size = restored
        self.previous_size = None
        self.save(update_fields=["size", "previous_size"])

        return restored

    def get_k8s_values(self):
        k8s_values = super().get_k8s_values()
        k8s_values["volume"] = dict(size=f"{str(self.size)}Gi")
        return k8s_values

    class Meta:
        verbose_name = "Persistent Volume"
        verbose_name_plural = "Persistent Volumes"
        permissions = [("can_access_app", "Can access app service")]
