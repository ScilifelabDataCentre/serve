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
            volumeK8s_dict["volumeK8s"][object.name] = dict(
                release=object.subdomain.subdomain
            )
        self.k8s_values["apps"] = volumeK8s_dict
        # This is just do fix a legacy. 
        #TODO: Change the jupyter chart to fetch port from appconfig as other apps
        self.k8s_values["service"]["targetport"] = 8888
        
    class Meta:
        verbose_name = "JupyterLab Instance"
        verbose_name_plural = "JupyterLab Instances"
        permissions = [("can_access_app", "Can access app service")]



from django.dispatch import receiver
from guardian.shortcuts import assign_perm, remove_perm
from django.db.models.signals import post_save




@receiver(
    post_save,
    sender=JupyterInstance,
    dispatch_uid="app_instance_update_permission",
)
def update_permission(sender, instance, created, **kwargs):
    owner = instance.owner

    if instance.access == "private":
        if created or not owner.has_perm("can_access_app", instance):
            assign_perm("can_access_app", owner, instance)

    else:
        if owner.has_perm("can_access_app", instance):
            remove_perm("can_access_app", owner, instance)

