from django.db import models

from apps.models import AppInstanceManager, BaseAppInstance, Social


class ShinyInstanceManager(AppInstanceManager):
    model_type = "shinyinstance"


class ShinyInstance(BaseAppInstance, Social):
    objects = ShinyInstanceManager()
    ACCESS_TYPES = (
        ("project", "Project"),
        ("private", "Private",),
        ("public", "Public"),
        ("link", "Link"),
    )
    access = models.CharField(max_length=20, default="private", choices=ACCESS_TYPES)
    port = models.IntegerField(default=3838)
    image = models.CharField(max_length=255)
    proxy = models.BooleanField(default=True)
    container_waittime = models.IntegerField(default=20000)
    heartbeat_timeout = models.IntegerField(default=60000)
    heartbeat_rate = models.IntegerField(default=10000)
    
    def set_k8s_values(self):
        super().set_k8s_values()

        self.k8s_values["permission"] = str(self.access)
        self.k8s_values["appconfig"] = dict(
            port = self.port,
            image = self.image,
            proxyheartbeatrate = self.heartbeat_rate,
            proxyheartbeattimeout = self.heartbeat_timeout,
            proxycontainerwaittime = self.container_waittime
        )
    
    class Meta:
        verbose_name = "Shiny App Instance"
        verbose_name_plural = "Shiny App Instances"
        permissions = [("can_access_app", "Can access app service")]