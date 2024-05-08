from django.db import models

from apps.models import AppInstanceManager, AbstractAppInstance, Social


class CustomAppInstanceManager(AppInstanceManager):
    model_type = "jupyterinstance"


class CustomAppInstance(AbstractAppInstance, Social):
    objects = CustomAppInstanceManager()
    ACCESS_TYPES = (
        ("project", "Project"),
        ("private", "Private",),
        ("public", "Public"),
        ("link", "Link"),
    )
    access = models.CharField(max_length=20, default="private", choices=ACCESS_TYPES)
    port = models.IntegerField(default=8000)
    image = models.CharField(max_length=255)
    path = models.CharField(max_length=255, default="/")
    user_id = models.IntegerField(default=1000)

    def set_k8s_values(self):
        super().set_k8s_values()

        self.k8s_values["permission"] = str(self.access)
        self.k8s_values["appconfig"] = dict(
            port = self.port,
            image = self.image,
            path = self.path,
            userid = self.user_id
        )
    
    class Meta:
        verbose_name = "Custom App Instance"
        verbose_name_plural = "Custom App Instances"
        permissions = [("can_access_app", "Can access app service")]