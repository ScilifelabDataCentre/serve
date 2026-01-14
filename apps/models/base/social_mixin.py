from django.db import models
from tagulous.models import TagField


class SocialMixin(models.Model):
    tags = TagField(blank=True, help_text="Add keywords to help categorize your app", force_lowercase=True)
    note_on_linkonly_privacy = models.TextField(blank=True, null=True, default="")
    reminder_date_linkonly_privacy = models.DateField(null=True, blank=True)
    collections = models.ManyToManyField("portal.Collection", blank=True, related_name="%(class)s")
    source_code_url = models.URLField(blank=True, null=True)
    description = models.TextField(
        default="",
        help_text="Provide a detailed description of your app. Think of it as the abstract of a research article.",
    )

    class Meta:
        abstract = True
