from django.db import models

from apps.helpers import validate_path_k8s_label_compatible
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
        "VolumeInstance", blank=True, null=True, related_name="%(class)s", on_delete=models.SET_NULL
    )
    access = models.CharField(max_length=20, default="project", choices=ACCESS_TYPES)
    port = models.IntegerField(default=3838)
    image = models.CharField(max_length=255)
    path = models.CharField(max_length=255, default="/", blank=True)
    proxy = models.BooleanField(default=True)
    container_waittime = models.IntegerField(default=20000)
    heartbeat_timeout = models.IntegerField(default=60000)
    heartbeat_rate = models.IntegerField(default=10000)
    shiny_site_dir = models.CharField(
        validators=[validate_path_k8s_label_compatible], max_length=255, default="", blank=True
    )

    # The following three settings control the pre-init and seats behaviour (see documentation)
    # These settings override the Helm chart default values
    minimum_seats_available = models.IntegerField(default=1)
    seats_per_container = models.IntegerField(default=1)
    allow_container_reuse = models.BooleanField(default=False)

    def get_k8s_values(self):
        k8s_values = super().get_k8s_values()

        k8s_values["permission"] = str(self.access)
        k8s_values["appconfig"] = dict(
            port=self.port,
            image=self.image,
            path=self.path,
            site_dir="/srv/shiny-server/" + self.shiny_site_dir,
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
