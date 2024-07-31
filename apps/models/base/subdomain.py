from django.conf import settings
from django.db import models


class Subdomain(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    subdomain = models.CharField(max_length=53, unique=True)
    project = models.ForeignKey(settings.PROJECTS_MODEL, on_delete=models.CASCADE, null=True, blank=True)

    def __str__(self):
        return str(self.subdomain) + " ({})".format(self.project.name)

    def to_dict(self):
        return {
            "subdomain": self.subdomain,
        }

    class Meta:
        verbose_name = "Subdomain"
        verbose_name_plural = "Subdomains"
