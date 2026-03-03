from crispy_bootstrap5.bootstrap5 import BS5Accordion
from crispy_forms.bootstrap import AccordionGroup
from crispy_forms.layout import HTML, Div, Layout
from django import forms
from django.utils.safestring import mark_safe

from apps.forms.base import BaseForm
from apps.forms.field.common import SRVCommonDivField
from apps.forms.mixins import KeywordTagsValidationMixin
from apps.models import DepictioInstance

__all__ = ["DepictioForm"]


class DepictioForm(KeywordTagsValidationMixin, BaseForm):
    def _setup_form_fields(self):
        super()._setup_form_fields()

        # Add invenio_tags as a form-only field for vocabulary input
        self.fields["invenio_tags"] = forms.CharField(
            required=False,
            label="Subjects and keywords",
            help_text="Select research field(s) and keyword(s) to help categorize your app. "
            "We allow keywords from MeSH, EuroSciVoc, and GEMET.",
            widget=forms.TextInput(attrs={"class": "form-control"}),
        )

    def _setup_form_helper(self):
        super()._setup_form_helper()
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
            active=True,
        )

        accordion = BS5Accordion(
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
        model = DepictioInstance
        fields = ["name", "description", "access", "tags"]
        labels = {
            "tags": "Subjects and keywords",
        }
