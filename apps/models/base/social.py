from django.db import models
from tagulous.models import TagField


class Social(models.Model):
    tags = TagField(blank=True)
    note_on_linkonly_privacy = models.TextField(blank=True, null=True, default="")
    # collections = models.ManyToManyField("collections_module.Collection", blank=True, related_name="app_instances")
    source_code_url = models.URLField(blank=True, null=True)
    description = models.TextField(blank=True, null=True, default="")

    class Meta:
        abstract = True
