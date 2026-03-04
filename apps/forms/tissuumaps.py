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

        self.fields["creators"] = forms.CharField(
            required=False,
            label="Creators",
            help_text=(
                "Manage the creators of this app. You are included as the primary creator by default. "
                "You can add, edit, remove, and reorder creators as needed."
            ),
            widget=forms.HiddenInput(),  # Will be handled by custom template
        )

        # Initialize creators with current user if available
        self._initialize_creators()

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
            mark_safe("<h3>Description</h3>"),
            SRVCommonDivField("name", required=True),
            SRVCommonDivField("description", rows=4, required=True),
            SRVCommonDivField("invenio_tags"),
            Div(
                HTML(
                    '<label class="form-label">Creators '
                    '<span class="bi bi-question-circle text-muted ms-2" '
                    'data-bs-toggle="tooltip" data-bs-placement="right" '
                    'data-bs-original-title="Manage the creators and contributors for this application.">'
                    "</span></label>"
                ),
                "creators",  # Hidden field
                HTML(
                    '<div class="mt-2">'
                    '<button type="button" class="btn btn-outline-secondary btn-sm" onclick="openCreatorsModal()">'
                    '<span class="fas fa-users text-muted"></span> Manage Creators'
                    "</button></div>"
                ),
                css_class="mb-3",
            ),
            SRVCommonDivField("access"),
            SRVCommonDivField(
                "note_on_linkonly_privacy",
            ),
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
        model = TissuumapsInstance
        fields = ["name", "description", "volume", "flavor", "access", "note_on_linkonly_privacy", "tags"]
        labels = {
            "tags": "Subjects and keywords",
            "note_on_linkonly_privacy": "Reason for choosing the link only option",
        }
