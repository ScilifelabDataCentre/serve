from django.db import models
from django_tagulous.models import TagField


class SocialMixin(models.Model):
    tags = TagField(blank=True, help_text="Add keywords to help categorize your app", force_lowercase=True)
    subjects_keywords = models.JSONField(
        blank=True,
        default=list,
        help_text=("Select research field(s) and keyword(s) to help categorize your app."),
    )
    note_on_linkonly_privacy = models.TextField(
        blank=True,
        null=True,
        default="",
        help_text="Note that this option can be used only for a limited amount of time. For example, while the app is under development or while an accompanying article is under peer review. Describe why you need to choose the Link only permission level.",
    )
    reminder_date_linkonly_privacy = models.DateField(null=True, blank=True)
    collections = models.ManyToManyField("portal.Collection", blank=True, related_name="%(class)s")
    source_code_url = models.URLField(
        "Source code URL",
        blank=True,
        null=True,
        help_text="Provide a link to the public source code of the application. For example, https://github.com/ScilifelabDataCentre/streamlit-image-to-smiles.",
    )
    description = models.TextField(
        default="",
        help_text="Provide a detailed description of your app. Think of it as the abstract of a research article.",
    )

    invenio_record_id = models.CharField(
        max_length=255, blank=True, null=True, help_text="Invenio record identifier for published apps"
    )
    app_doi = models.CharField(
        max_length=255, blank=True, null=True, help_text="Digital Object Identifier for the published app"
    )
    made_public_on = models.DateTimeField(blank=True, null=True)

    class Meta:
        abstract = True
