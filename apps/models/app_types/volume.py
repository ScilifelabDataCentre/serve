from datetime import datetime, timedelta
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db.models import Q

from apps.models import AppInstanceManager, AbstractAppInstance



class VolumeInstanceManager(AppInstanceManager):
    model_type = "volumeinstance"
    
    def get_app_instances_of_project_filter(self, user, project, include_deleted=False, deleted_time_delta=None):
        q = Q()

        if not include_deleted:
            if deleted_time_delta is None:
                q &= ~Q(app_status__status="Deleted")
            else:
                time_threshold = datetime.now() - timedelta(minutes=deleted_time_delta)
                q &= ~Q(app_status__status="Deleted") | Q(deleted_on__gte=time_threshold)

        q &= Q(owner=user)
        q &= Q(project=project)

        return q


class VolumeInstance(AbstractAppInstance):
    objects = VolumeInstanceManager()
    size = models.IntegerField(default=1, help_text="Size in GB",
                               validators=[MinValueValidator(1), MaxValueValidator(100)])

    def __str__(self):
        return str(self.name)

    def set_k8s_values(self):
        super().set_k8s_values()
        self.k8s_values["volume"] = dict(size=f"{str(self.size)}Gi")
    
    class Meta:
        verbose_name = "Persistent Volume"
        verbose_name_plural = "Persistent Volumes"
        permissions = [("can_access_app", "Can access app service")]