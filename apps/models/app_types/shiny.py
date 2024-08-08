from django.db import models

from apps.models import (
    AppInstanceManager,
    BaseAppInstance,
    LogsEnabledMixin,
    SocialMixin,
)


class ShinyInstanceManager(AppInstanceManager):
    model_type = "shinyinstance"


class ShinyInstance(BaseAppInstance, SocialMixin, LogsEnabledMixin):
    objects = ShinyInstanceManager()
    ACCESS_TYPES = (
        ("project", "Project"),
        (
            "private",
            "Private",
        ),
        ("public", "Public"),
        ("link", "Link"),
    )

    volume = models.ForeignKey(
        "VolumeInstance", blank=True, null=True, related_name="%(class)s", on_delete=models.CASCADE
    )
    access = models.CharField(max_length=20, default="project", choices=ACCESS_TYPES)
    port = models.IntegerField(default=3838)
    image = models.CharField(max_length=255)
    path = models.CharField(max_length=255, default="/")
    proxy = models.BooleanField(default=True)
    container_waittime = models.IntegerField(default=20000)
    heartbeat_timeout = models.IntegerField(default=60000)
    heartbeat_rate = models.IntegerField(default=10000)
    minimum_seats_available = models.IntegerField(default=2)
    seats_per_container = models.IntegerField(default=3)
    allow_container_reuse = models.BooleanField(default=True)

    def get_k8s_values(self):
        k8s_values = super().get_k8s_values()

        k8s_values["permission"] = str(self.access)
        k8s_values["appconfig"] = dict(
            port=self.port,
            image=self.image,
            path=self.path,
            proxyheartbeatrate=self.heartbeat_rate,
            proxyheartbeattimeout=self.heartbeat_timeout,
            proxycontainerwaittime=self.container_waittime,
            minimumSeatsAvailable=self.minimum_seats_available,
            seatsPerContainer=self.seats_per_container,
            allowContainerReuse=self.allow_container_reuse,
        )
        volumeK8s_dict = {"volumeK8s": {}}
        if self.volume:
            volumeK8s_dict["volumeK8s"][self.volume.name] = dict(release=self.volume.subdomain.subdomain)
        k8s_values["apps"] = volumeK8s_dict
        return k8s_values

    class Meta:
        verbose_name = "Shiny App Instance"
        verbose_name_plural = "Shiny App Instances"
        permissions = [("can_access_app", "Can access app service")]
