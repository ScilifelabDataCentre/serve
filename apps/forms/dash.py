from crispy_bootstrap5.bootstrap5 import BS5Accordion
from crispy_forms.bootstrap import Accordion, AccordionGroup, PrependedText
from crispy_forms.layout import HTML, Div, Layout
from django import forms
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils.safestring import mark_safe

from apps.forms.base import AppBaseForm
from apps.forms.field.common import SRVCommonDivField
from apps.forms.field.widget import FlavorSelect
from apps.forms.mixins import (
    ContainerImageMixin,
    CreatorsMixin,
    KeywordTagsValidationMixin,
)
from apps.models import DashInstance
from projects.models import Flavor

__all__ = ["DashForm"]


class DashForm(ContainerImageMixin, CreatorsMixin, KeywordTagsValidationMixin, AppBaseForm):
    flavor = forms.ModelChoiceField(
        queryset=Flavor.objects.none(), required=False, empty_label=None, widget=FlavorSelect
    )
    port = forms.IntegerField(min_value=3000, max_value=9999, required=True)
    default_url_subpath = forms.CharField(max_length=255, required=False, label="Custom URL subpath")
    funding_sources_json = forms.CharField(required=False, widget=forms.HiddenInput(), label="Funding sources")
    related_publications_json = forms.CharField(
        required=False,
        widget=forms.HiddenInput(),
        label="Related publications and preprints",
    )
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
        if self.instance and self.instance.pk and hasattr(self.instance, "subjects_keywords"):
            existing_tags = self.instance.subjects_keywords or []
            if existing_tags:
                # Convert tag objects to pipe-separated format for template
                tag_names = [item.get("subject", "") for item in existing_tags if isinstance(item, dict)]
                tag_string = " | ".join(filter(None, tag_names))
                self.fields["invenio_tags"].initial = tag_string
            else:
                self.fields["invenio_tags"].initial = ""

    def _setup_form_fields(self):
        # Handle Volume field
        super()._setup_form_fields()

        self.fields["default_url_subpath"].widget.attrs.update({"class": "textinput form-control"})
        self.fields["default_url_subpath"].help_text = "Specify a non-default start URL if your app requires that."
        apps_url = reverse("portal:apps")
        self.fields["default_url_subpath"].bottom_help_text = mark_safe(
            (
                f"<span class='fw-bold' id='id_default_url_subpath_helptext'>Note:</span> "
                f"This changes the URL connected to the Open button for an app"
                f" on the Serve <a href='{apps_url}'>Apps & Models</a> page."
            )
        )

        # Setup container image field from mixin
        self._setup_container_image_field()
        super()._restore_model_help_text()

    def _setup_form_helper(self):
        super()._setup_form_helper()
        # Define AccordionGroups
        general_fields = [
            SRVCommonDivField("name", required=True),
            SRVCommonDivField("description", rows=4, required=True),
            SRVCommonDivField("invenio_tags", template="apps/invenio_tags_field.html"),
            SRVCommonDivField("access"),
            self.get_creators_field_layout(),
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

        if "related_publications_json" in self.fields:
            general_fields.append(
                SRVCommonDivField(
                    "related_publications_json",
                    tooltip=False,
                    label="Related publications and preprints",
                    template="apps/related_publications_field.html",
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
            SRVCommonDivField(
                "subdomain", placeholder="Enter a subdomain or leave blank for a random one", spinner=True
            ),
            SRVCommonDivField("flavor"),
            SRVCommonDivField("port", placeholder="8000"),
            # Container image field
            self._setup_container_image_helper(),
            active=True,
        )

        advanced = AccordionGroup(
            mark_safe("<h3>Advanced settings</h3>"),
            PrependedText(
                "default_url_subpath",
                mark_safe("<span id='id_custom_default_url_prepend'>Subdomain/</span>"),
                template="apps/partials/srv_prepend_append_input_group.html",
            ),
            active=True,
        )

        accordion = BS5Accordion(
            configuration,
            general,
            advanced,
            always_open=True,
            css_class="form-accordion",
        )
        accordion.always_open = True  # Force property for Bootstrap 5.3+

        body = Div(accordion, css_class="card-body")
        body.always_open = True
        self.helper.layout = Layout(body, self.footer)

    @property
    def changed_data(self):
        # Override the default changed_data to handle that volume not part of this app type.
        # Parent's changed_data attribute is also a @property.
        # TODO: Consider adding to all app forms that do not contain volume.
        changed_data = super().changed_data
        if "volume" in changed_data:
            changed_data.remove("volume")
        return changed_data

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
        model = DashInstance
        fields = [
            "name",
            "description",
            "flavor",
            "access",
            "note_on_linkonly_privacy",
            "source_code_url",
            "port",
            "image",
            "subjects_keywords",
            "default_url_subpath",
        ]
        labels = {
            "subjects_keywords": "Subjects and keywords",
            "note_on_linkonly_privacy": "Reason for choosing the link only option",
        }
