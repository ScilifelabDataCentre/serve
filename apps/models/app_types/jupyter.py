from django.db import models

from apps.models import AppInstanceManager, BaseAppInstance, Social


class JupyterInstanceManager(AppInstanceManager):
    model_type = "jupyterinstance"


class JupyterInstance(BaseAppInstance):
    objects = JupyterInstanceManager()
    ACCESS_TYPES = (
        ("project", "Project"),
        ("private", "Private"),
    )
    volume = models.ManyToManyField("VolumeInstance", blank=True)
    access = models.CharField(max_length=20, default="private", choices=ACCESS_TYPES)

    def set_k8s_values(self):
        super().set_k8s_values()

        self.k8s_values["permission"] = str(self.access)

        # Not the nicest perhaps, but it works since the charts assume that the volumes are on this form
        # {apps:
        #   {volumeK8s:
        #       {project-vol:
        #           {release: r1582t9h9

        volumeK8s_dict = {"volumeK8s": {}}
        for object in self.volume.all():
            volumeK8s_dict["volumeK8s"][object.name] = dict(release=object.subdomain.subdomain)
        self.k8s_values["apps"] = volumeK8s_dict
        # This is just do fix a legacy.
        # TODO: Change the jupyter chart to fetch port from appconfig as other apps
        self.k8s_values["service"]["targetport"] = 8888

    class Meta:
        verbose_name = "JupyterLab Instance"
        verbose_name_plural = "JupyterLab Instances"
        permissions = [("can_access_app", "Can access app service")]
