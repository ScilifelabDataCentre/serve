from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator

from apps.models import AppInstanceManager, AbstractAppInstance



class VolumeInstanceManager(AppInstanceManager):
    model_type = "volumeinstance"


class VolumeInstance(AbstractAppInstance):
    objects = VolumeInstanceManager()
    size = models.IntegerField(default=1, help_text="Size in GB",
                               validators=[MinValueValidator(1), MaxValueValidator(100)])

    def __str__(self):
        return str(self.name)

    def set_k8s_values(self):
        super().set_k8s_values()
        self.k8s_values["volume"] = dict(size=f"{str(self.size)}Gi")