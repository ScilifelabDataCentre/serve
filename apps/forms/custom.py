import json

import waffle
from crispy_bootstrap5.bootstrap5 import BS5Accordion
from crispy_forms.bootstrap import Accordion, AccordionGroup, PrependedText
from crispy_forms.layout import Div, Layout
from django import forms
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils.safestring import mark_safe

from apps.forms.base import AppBaseForm
from apps.forms.field.common import SRVCommonDivField
from apps.forms.mixins import (
    ContainerImageMixin,
    KeywordTagsValidationMixin,
    StorageMixin,
)
from apps.models import CustomAppInstance
from projects.models import Flavor

__all__ = ["CustomAppForm"]


class CustomAppForm(StorageMixin, ContainerImageMixin, KeywordTagsValidationMixin, AppBaseForm):
    flavor = forms.ModelChoiceField(queryset=Flavor.objects.none(), required=False, empty_label=None)
    port = forms.IntegerField(min_value=3000, max_value=9999, required=True)
    path = forms.CharField(max_length=255, required=False)
    default_url_subpath = forms.CharField(max_length=255, required=False, label="Custom URL subpath")
    language = forms.ChoiceField(
        choices=AppBaseForm.LANGUAGE_CHOICES,
        required=False,
        initial="eng",
        label="Language of the application interface",
    )
    funding_sources_json = forms.CharField(required=False, widget=forms.HiddenInput(), label="Funding sources")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        super().add_metadata()

        # Add invenio_tags as a form-only field for vocabulary input
        self.fields["invenio_tags"] = forms.CharField(
            required=False,
            label="Subjects and keywords",
            help_text="Select research field(s) and keyword(s) to help categorize your app. "
            "We allow keywords from MeSH, EuroSciVoc, and GEMET.",
            widget=forms.TextInput(attrs={"class": "form-control"}),
        )

    def _setup_form_fields(self):
        # Handle Volume field
        super()._setup_form_fields()
        self.fields["volume"].initial = None

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
        self._set_up_mount_path_field()
        super()._restore_model_help_text()

        if not waffle.switch_is_active("doi_minting_using_invenio"):
            self.fields.pop("funding_sources_json", None)
        else:
            # Ensure a valid JSON default for the hidden field
            self.fields["funding_sources_json"].initial = self.fields["funding_sources_json"].initial or "[]"

    def clean_funding_sources_json(self):
        raw = self.cleaned_data.get("funding_sources_json") or "[]"

        try:
            data = json.loads(raw) if isinstance(raw, str) else raw
        except json.JSONDecodeError as e:
            raise ValidationError("Invalid funding sources data.") from e

        if not isinstance(data, list):
            raise ValidationError("Funding sources must be a list.")

        for item in data:
            if not isinstance(item, dict):
                raise ValidationError("Invalid funding source entry.")

            funder_name = (item.get("funder_name") or "").strip()
            funder_id = (item.get("funder_id") or "").strip()

            if not funder_name:
                raise ValidationError("Each funding source must have a funder name.")
            if not funder_id:
                # Enforces “no free text”
                raise ValidationError("Each funding source must be selected from the Invenio funders list.")

        return json.dumps(data)

    def _setup_form_helper(self):
        super()._setup_form_helper()

        # Define AccordionGroups
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

        advanced = AccordionGroup(
            mark_safe("<h3>Advanced settings</h3>"),
            PrependedText(
                "default_url_subpath",
                mark_safe("<span id='id_custom_default_url_prepend'>Subdomain/</span>"),
                template="apps/partials/srv_prepend_append_input_group.html",
                attrs={"aria-label": "Custom URL subpath"},
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

    def clean(self):
        cleaned_data = super().clean()
        keyword_tags_data = self.clean_keyword_tags()
        cleaned_data["tags"] = keyword_tags_data
        return cleaned_data

    class Meta:
        model = CustomAppInstance
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
            "default_url_subpath",
            "mount_path",
        ]
        labels = {
            "note_on_linkonly_privacy": "Reason for choosing the link only option",
            "tags": "Subjects and keywords",
        }
