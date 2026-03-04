from crispy_bootstrap5.bootstrap5 import BS5Accordion
from crispy_forms.bootstrap import AccordionGroup
from crispy_forms.layout import HTML, Div, Layout
from django import forms
from django.utils.safestring import mark_safe

from apps.forms.base import BaseForm
from apps.forms.field.common import SRVCommonDivField
from apps.forms.mixins import CreatorsMixin, KeywordTagsValidationMixin
from apps.models import DepictioInstance

__all__ = ["DepictioForm"]


class DepictioForm(KeywordTagsValidationMixin, CreatorsMixin, BaseForm):
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
        # Define AccordionGroups
        general = AccordionGroup(
            mark_safe("<h3>About</h3>"),
            SRVCommonDivField("name", required=True),
            SRVCommonDivField("description", rows=4, required=True),
            SRVCommonDivField("invenio_tags"),
            Div(
                self.get_creators_field_layout(),
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
