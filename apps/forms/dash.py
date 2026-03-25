from crispy_bootstrap5.bootstrap5 import BS5Accordion
from crispy_forms.bootstrap import Accordion, AccordionGroup, PrependedText
from crispy_forms.layout import HTML, Div, Field, Layout
from django import forms
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils.safestring import mark_safe

from apps.forms.base import AppBaseForm
from apps.forms.field.common import SRVCommonDivField
from apps.forms.mixins import ContainerImageMixin, KeywordTagsValidationMixin
from apps.models import DashInstance
from projects.models import Flavor

__all__ = ["DashForm"]


class DashForm(ContainerImageMixin, KeywordTagsValidationMixin, AppBaseForm):
    flavor = forms.ModelChoiceField(queryset=Flavor.objects.none(), required=False, empty_label=None)
    port = forms.IntegerField(min_value=3000, max_value=9999, required=True)
    default_url_subpath = forms.CharField(max_length=255, required=False, label="Custom URL subpath")
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
        keyword_tags_data = self.clean_keyword_tags()
        cleaned_data["tags"] = keyword_tags_data
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
            "tags",
            "default_url_subpath",
        ]
        labels = {
            "tags": "Subjects and keywords",
            "note_on_linkonly_privacy": "Reason for choosing the link only option",
        }
