from django.db import models

from apps.models import LogsEnabledMixin, SocialMixin


class AbstractCustomAppInstance(SocialMixin, LogsEnabledMixin):
    """
    This class is intended to be used with ``BaseAppInstance`` the following way:

    ```python
    class CustomAppInstance(AbstractCustomAppInstance, BaseAppInstance):
        pass
    ```

    This is because of how ``get_k8s_values`` method works. It depends on in this case
     the ``CustomAppInstance`` to be already a child class of a ``BaseAppInstance``. That way,
     when this classes ``super().get_k8s_values()`` is called, it will call ``get_k8s_values()``
     of ``BaseAppInstance``.
    """

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
    port = models.IntegerField(default=8000)
    image = models.CharField(max_length=255)
    path = models.CharField(max_length=255, default="/", blank=True)
    user_id = models.IntegerField(default=1000)

    def get_k8s_values(self):
        k8s_values = super().get_k8s_values()

        k8s_values["permission"] = str(self.access)
        k8s_values["appconfig"] = dict(port=self.port, image=self.image, path=self.path, userid=self.user_id)
        volumeK8s_dict = {"volumeK8s": {}}
        if self.volume:
            volumeK8s_dict["volumeK8s"][self.volume.name] = dict(release=self.volume.subdomain.subdomain)
        k8s_values["apps"] = volumeK8s_dict
        return k8s_values

    class Meta:
        verbose_name = "Custom App Instance"
        verbose_name_plural = "Custom App Instances"
        permissions = [("can_access_app", "Can access app service")]
        abstract = True
