from crispy_bootstrap5.bootstrap5 import BS5Accordion
from crispy_forms.bootstrap import Accordion, AccordionGroup, PrependedText
from crispy_forms.layout import HTML, Div, Layout
from django import forms
from django.utils.safestring import mark_safe

from apps.forms.base import AppBaseForm
from apps.forms.field.common import SRVCommonDivField
from apps.forms.mixins import (
    ContainerImageMixin,
    CreatorsMixin,
    KeywordTagsValidationMixin,
    StorageMixin,
)
from apps.models import StreamlitInstance
from projects.models import Flavor

__all__ = ["StreamlitForm"]


class StreamlitForm(StorageMixin, ContainerImageMixin, KeywordTagsValidationMixin, CreatorsMixin, AppBaseForm):
    flavor = forms.ModelChoiceField(queryset=Flavor.objects.none(), required=False, empty_label=None)
    port = forms.IntegerField(min_value=3000, max_value=9999, required=True)
    path = forms.CharField(max_length=255, required=False)
    funding_sources_json = forms.CharField(required=False, widget=forms.HiddenInput(), label="Funding sources")
    language = forms.ChoiceField(
        choices=AppBaseForm.LANGUAGE_CHOICES,
        required=False,
        initial="eng",
        label="Language of the application interface",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Add invenio_tags as a form-only field for vocabulary input
        self.fields["invenio_tags"] = forms.CharField(
            required=False,
            label="Subjects and keywords",
            help_text="Select research field(s) and keyword(s) to help categorize your app. "
            "We allow keywords from MeSH, EuroSciVoc, and GEMET.",
            widget=forms.TextInput(attrs={"class": "form-control"}),
        )

        # Load existing tags into the invenio_tags field after creating it
        self._load_existing_tags_to_invenio_field()

    def _load_existing_tags_to_invenio_field(self):
        """Load existing database tags into the invenio_tags field"""
        if self.instance and self.instance.pk and hasattr(self.instance, "tags"):
            existing_tags = list(self.instance.tags.all())
            if existing_tags:
                # Convert tag objects to pipe-separated format for template
                tag_names = [str(tag) for tag in existing_tags]
                tag_string = " | ".join(tag_names)
                self.fields["invenio_tags"].initial = tag_string
            else:
                self.fields["invenio_tags"].initial = ""

    def _setup_form_fields(self):
        # Handle Volume field
        super()._setup_form_fields()
        self.fields["volume"].initial = None

        # Setup container image field from mixin
        self._setup_container_image_field()
        self._set_up_mount_path_field()

    def _setup_form_helper(self):
        super()._setup_form_helper()

        # Define AccordionGroups
        general_fields = [
            SRVCommonDivField("name", required=True),
            SRVCommonDivField("description", rows=4, required=True),
            SRVCommonDivField("invenio_tags", template="apps/invenio_tags_field.html"),
            self.get_creators_field_layout(),
            SRVCommonDivField("access"),
            SRVCommonDivField(
                "note_on_linkonly_privacy",
                rows=1,
            ),
        ]

        if "language" in self.fields:
            general_fields.append(SRVCommonDivField("language", tooltip=False))
        if "funding_sources_json" in self.fields:
            general_fields.append(
                SRVCommonDivField(
                    "funding_sources_json",
                    tooltip=False,
                    label="Funding sources",
                    template="apps/funding_sources_field.html",
                )
            )

        general_fields += [
            SRVCommonDivField("source_code_url", placeholder="https://..."),
        ]

        general = AccordionGroup(
            mark_safe("<h3>About</h3>"),
            *general_fields,
            active=True,
        )

        configuration = AccordionGroup(
            mark_safe("<h3>Configuration</h3>"),
            SRVCommonDivField("subdomain", placeholder="Enter a subdomain or leave blank for a random one."),
            self._set_up_mount_path_helper(),
            SRVCommonDivField("flavor"),
            SRVCommonDivField("port", placeholder="8000"),
            self._setup_container_image_helper(),
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
                cleaned_data["tags"] = self.clean_keyword_tags()
            elif self.instance and self.instance.pk and hasattr(self.instance, "tags"):
                # If no tags in form but instance has existing tags, preserve them
                existing_tags = list(self.instance.tags.all())
                if existing_tags:
                    # Keep existing tags as they are
                    cleaned_data["tags"] = existing_tags
        return cleaned_data

    class Meta:
        model = StreamlitInstance
        fields = [
            "name",
            "description",
            "volume",
            "path",
            "flavor",
            "access",
            "note_on_linkonly_privacy",
            "source_code_url",
            "port",
            "image",
            "tags",
            "mount_path",
        ]
        labels = {
            "note_on_linkonly_privacy": "Reason for choosing the link only option",
            "tags": "Subjects and keywords",
        }
