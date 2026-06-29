from crispy_bootstrap5.bootstrap5 import BS5Accordion
from crispy_forms.bootstrap import Accordion, AccordionGroup, PrependedText
from crispy_forms.layout import HTML, Div, Layout
from django import forms
from django.utils.safestring import mark_safe

from apps.forms.base import AppBaseForm
from apps.forms.field.common import SRVCommonDivField
from apps.forms.mixins import CreatorsMixin, KeywordTagsValidationMixin, VolumeMixin
from apps.models import TissuumapsInstance

__all__ = ["TissuumapsForm"]


class TissuumapsForm(VolumeMixin, KeywordTagsValidationMixin, CreatorsMixin, AppBaseForm):
    def _setup_form_fields(self):
        # Handle Volume field
        super()._setup_form_fields()
        volume_form_field = self.fields["volume"]
        volume_form_field.required = True
        volume_form_field.empty_label = None
        self._set_up_volume_field()

        # Add invenio_tags as a form-only field for vocabulary input
        self.fields["invenio_tags"] = forms.CharField(
            required=False,
            label="Subjects and keywords",
            help_text="Select research field(s) and keyword(s) to help categorize your app. "
            "We allow keywords from MeSH, EuroSciVoc, and GEMET.",
            widget=forms.TextInput(attrs={"class": "form-control"}),
        )

        # Load existing tags into the invenio_tags field
        if self.instance and self.instance.pk and hasattr(self.instance, "subjects_keywords"):
            existing_tags = self.instance.subjects_keywords or []
            if existing_tags:
                # Convert tag objects to pipe-separated format for template
                tag_names = [item.get("subject", "") for item in existing_tags if isinstance(item, dict)]
                tag_string = " | ".join(filter(None, tag_names))
                self.fields["invenio_tags"].initial = tag_string
            else:
                self.fields["invenio_tags"].initial = ""

    def _setup_form_helper(self):
        super()._setup_form_helper()

        configuration = AccordionGroup(
            mark_safe("<h3>Configuration</h3>"),
            SRVCommonDivField(
                "subdomain", placeholder="Enter a subdomain or leave blank for a random one", spinner=True
            ),
            self._set_up_volume_helper(),
            SRVCommonDivField("flavor"),
            active=True,
        )

        # Define AccordionGroups
        general = AccordionGroup(
            mark_safe("<h3>About</h3>"),
            SRVCommonDivField("name", required=True),
            SRVCommonDivField("description", rows=4, required=True),
            SRVCommonDivField("invenio_tags", template="apps/invenio_tags_field.html"),
            SRVCommonDivField("access"),
            SRVCommonDivField(
                "note_on_linkonly_privacy",
            ),
            self.get_creators_field_layout(),
            active=True,
        )

        accordion = BS5Accordion(
            configuration,
            general,
            always_open=True,
            css_class="form-accordion",
        )
        accordion.always_open = True  # Force property for Bootstrap 5.3+

        body = Div(accordion, css_class="card-body")
        body.always_open = True
        self.helper.layout = Layout(body, self.footer)

    def clean(self):
        cleaned_data = super().clean()
        # Always handle tags field - preserve existing tags even if not changed
        if "invenio_tags" in self.fields:
            # Get the current value from the invenio_tags field
            invenio_tags_value = cleaned_data.get("invenio_tags", "") or self.fields["invenio_tags"].initial or ""

            if invenio_tags_value:
                # Process the tags using the existing cleaning logic
                cleaned_data["subjects_keywords"] = self.clean_keyword_tags()
            elif self.instance and self.instance.pk and hasattr(self.instance, "subjects_keywords"):
                # If no tags in form but instance has existing tags, preserve them
                existing_tags = self.instance.subjects_keywords or []
                if existing_tags:
                    # Keep existing tags as they are
                    cleaned_data["subjects_keywords"] = existing_tags

        return cleaned_data

    class Meta:
        model = TissuumapsInstance
        fields = ["name", "description", "volume", "flavor", "access", "note_on_linkonly_privacy", "subjects_keywords"]
        labels = {
            "subjects_keywords": "Subjects and keywords",
            "note_on_linkonly_privacy": "Reason for choosing the link only option",
        }
