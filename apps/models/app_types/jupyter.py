from django.db import models

from apps.models import AppInstanceManager, AbstractAppInstance
from apps.models.base import Social


class JupyterInstanceManager(AppInstanceManager):
    model_type = "jupyterinstance"


class JupyterInstance(AbstractAppInstance, Social):
    objects = JupyterInstanceManager()
    ACCESS_TYPES = (
        ("project", "Project"),
        ("private", "Private"),
    )
    volume = models.ManyToManyField("VolumeInstance", blank=True)
    access = models.CharField(max_length=20, default="private", choices=ACCESS_TYPES)

    def set_k8s_values(self):
        super().set_k8s_values()

        self.k8s_values["permission"] = self.access,

        # Not the nicest perhaps, but it works since the charts assume that the volumes are on this form
        # {apps:
        #   {volumeK8s:
        #       {project-vol:
        #           {release: r1582t9h9

        volumeK8s_dict = {"volumeK8s": {}}
        for object in self.volume.all():
            volumeK8s_dict["volumeK8s"][object.name] = dict(
                release=object.subdomain.subdomain
            )
        self.k8s_values["apps"] = volumeK8s_dict