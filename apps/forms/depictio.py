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
        # Define AccordionGroups
        general = AccordionGroup(
            mark_safe("<h3>About</h3>"),
            SRVCommonDivField("name", required=True),
            SRVCommonDivField("description", rows=4, required=True),
            SRVCommonDivField("invenio_tags", template="apps/invenio_tags_field.html"),
            SRVCommonDivField("access"),
            self.get_creators_field_layout(),
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

    def clean_subdomain(self):
        # Depictio does not render the subdomain field, so edit POSTs omit it entirely.
        # Without this override, BaseForm.clean_subdomain() would treat that omission as
        # an empty value and generate a new random subdomain on every edit.
        if self.instance and self.instance.pk and "subdomain" not in self.data and self.instance.subdomain:
            return self.validate_subdomain(self.instance.subdomain.subdomain)

        return super().clean_subdomain()

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

    @property
    def changed_data(self):
        changed_data = super().changed_data

        # Keep helpers.create_instance_from_form() from treating an omitted, non-rendered
        # subdomain field as a user-initiated subdomain change that forces redeploy/delete.
        if self.instance and self.instance.pk and "subdomain" not in self.data and "subdomain" in changed_data:
            changed_data.remove("subdomain")

        return changed_data

    class Meta:
        model = DepictioInstance
        fields = ["name", "description", "access", "subjects_keywords"]
        labels = {
            "subjects_keywords": "Subjects and keywords",
        }
