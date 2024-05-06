from django.db import models
from django.conf import settings


class Subdomain(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    subdomain = models.CharField(max_length=512, unique=True)
    project = models.ForeignKey(settings.PROJECTS_MODEL, on_delete=models.CASCADE, null=True)

    def __str__(self):
        return str(self.subdomain) + " ({})".format(self.project.name)

    def to_dict(self):
        return {
            "subdomain": self.subdomain,
        }