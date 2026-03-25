from crispy_bootstrap5.bootstrap5 import BS5Accordion
from crispy_forms.bootstrap import Accordion, AccordionGroup, PrependedText
from crispy_forms.layout import Div, Field, Layout
from django import forms
from django.utils.safestring import mark_safe

from apps.forms.base import AppBaseForm
from apps.forms.field.common import SRVCommonDivField
from apps.forms.mixins import (
    ContainerImageMixin,
    KeywordTagsValidationMixin,
    StorageMixin,
)
from apps.models import GradioInstance
from projects.models import Flavor

__all__ = ["GradioForm"]


class GradioForm(StorageMixin, ContainerImageMixin, KeywordTagsValidationMixin, AppBaseForm):
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
            help_text="Select research field(s) and keyword(s) to help categorize your app."
            "We allow keywords from MeSH, EuroSciVoc, and GEMET.",
            widget=forms.TextInput(attrs={"class": "form-control"}),
        )

    def _setup_form_fields(self):
        # Handle Volume field
        super()._setup_form_fields()
        self.fields["volume"].initial = None

        # Setup container image field from mixin
        self._setup_container_image_field()
        self._set_up_mount_path_field()

    def _setup_form_helper(self):
        super()._setup_form_helper()

        general_fields = [
            SRVCommonDivField("name", required=True),
            SRVCommonDivField("description", rows=4, required=True),
            SRVCommonDivField("invenio_tags"),
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
            mark_safe("<h3>Description</h3>"),
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
        # Validate invenio_tags and store valid tags
        cleaned_data["tags"] = self.clean_keyword_tags()
        return cleaned_data

    class Meta:
        model = GradioInstance
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
