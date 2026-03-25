import json
import logging
import uuid

import waffle
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Button, Div, Submit
from django import forms
from django.conf import settings
from django.forms import Select, SelectMultiple
from django.shortcuts import get_object_or_404

from apps.forms.field.widget import SubdomainInputGroup
from apps.models import BaseAppInstance, Subdomain, VolumeInstance
from apps.types_.subdomain import SubdomainCandidateName, SubdomainTuple
from doi_minting.clients.invenio_client import InvenioClient
from projects.models import Flavor, Project

logger = logging.getLogger(__name__)

__all__ = ["BaseForm", "AppBaseForm"]


class BaseForm(forms.ModelForm):
    """The most generic form for apps running on serve. Current intended use is for VolumesK8S type apps"""

    subdomain = forms.CharField(
        required=False,
        min_length=3,
        max_length=53,
        widget=SubdomainInputGroup(base_widget=forms.TextInput, data={}),
    )
    LANGUAGE_CHOICES = [
        ("eng", "English"),
        ("swe", "Swedish"),
        ("", "Other"),
    ]

    def __init__(self, *args, **kwargs):
        self.project_pk = kwargs.pop("project_pk", None)
        self.request = kwargs.pop("request", None)  # Store request for mixins
        self.project = get_object_or_404(Project, pk=self.project_pk) if self.project_pk else None
        self.model_name = self._meta.model._meta.verbose_name.replace("Instance", "")

        super().__init__(*args, **kwargs)

        self._setup_form_fields()
        self.add_metadata()
        self._setup_form_helper()
        for field in self.fields.values():
            if isinstance(field.widget, (Select, SelectMultiple)):
                field.widget.attrs["class"] = "form-select"
            else:
                field.widget.attrs["class"] = "form-control"

    # restore helptext for model in case it is rest in form
    def _restore_model_help_text(self):
        for name, field in self.fields.items():
            # Only for model-backed fields
            if name in getattr(self._meta, "fields", []):
                model_field = self._meta.model._meta.get_field(name)
                if not field.help_text and getattr(model_field, "help_text", ""):
                    field.help_text = model_field.help_text

    def _setup_form_fields(self):
        # Populate subdomain field with instance subdomain if it exists
        self.fields["subdomain"].widget.data["project_pk"] = self.project_pk
        self.fields["subdomain"].widget.data["hidden"] = "hidden"
        self.fields["subdomain"].initial = ""
        if self.instance and self.instance.pk:
            self.fields["subdomain"].initial = self.instance.subdomain.subdomain if self.instance.subdomain else ""
            self.fields["subdomain"].widget.data["hidden"] = ""

        # Handle name
        self.fields["name"].initial = ""
        # Initialize the tags field to existing tags or empty list
        if self.instance and self.instance.pk and hasattr(self.instance, "tags"):
            self.instance.refresh_from_db()
            self._original_tags = list(self.instance.tags.all())
        else:
            self._original_tags = []
        self._restore_model_help_text()

    def _setup_form_helper(self):
        # Create a footer for submit form or cancel
        self.footer = Div(
            Button(
                "cancel",
                "Cancel",
                css_class="btn-outline-dark btn-outline-cancel me-2",
                onclick="window.history.back()",
            ),
            Submit("submit", "Submit"),
            css_class="card-footer d-flex justify-content-end",
        )
        self.helper = FormHelper(self)
        self.helper.attrs = {
            "class": "needs-validation",
            "novalidate": "novalidate",
        }
        # Ensure HTML5 `required` attributes are rendered
        self.helper.use_required_attribute = True
        self.helper.form_method = "post"

    def add_metadata(self):
        instance = getattr(self, "instance", None)
        if not instance or not getattr(instance, "pk", None):
            return
        has_language_field = "language" in self.fields
        has_funding_field = "funding_sources_json" in self.fields
        # Fetch from Invenio only if there is at least one metadata field to prefill.
        if not has_language_field and not has_funding_field:
            return
        try:
            client = InvenioClient(
                base_url=settings.INVENIO_URL,
                token=settings.INVENIO_API_TOKEN,
            )

            record = None

            record_id = getattr(instance, "invenio_record_id", None)
            if record_id:
                record = client.get_record(record_id)

            if record:
                if has_language_field:
                    invenio_lang_id = client.extract_language_id(record)
                    self.fields["language"].initial = invenio_lang_id
                if has_funding_field:
                    funding_entries = client.extract_funding(record)
                    self.fields["funding_sources_json"].initial = json.dumps(funding_entries)

        except Exception:
            logger.exception("Failed to fetch metadata from Invenio; leaving default initial values.")

    def clean_subdomain(self):
        cleaned_data = super().clean()
        subdomain_input = cleaned_data.get("subdomain")
        return self.validate_subdomain(subdomain_input)

    def clean_source_code_url(self):
        cleaned_data = super().clean()
        access = cleaned_data.get("access")
        source_code_url = cleaned_data.get("source_code_url")

        if access == "public" and not source_code_url:
            self.add_error("source_code_url", "Source is required when access is public.")

        return source_code_url

    def clean_note_on_linkonly_privacy(self):
        cleaned_data = super().clean()

        access = cleaned_data.get("access", None)
        note_on_linkonly_privacy = cleaned_data.get("note_on_linkonly_privacy", None)

        if access == "link" and not note_on_linkonly_privacy:
            self.add_error(
                "note_on_linkonly_privacy", "Please, provide a reason for making the app accessible only via a link."
            )

        return note_on_linkonly_privacy

    def clean_tags(self):
        cleaned_data = super().clean()
        return cleaned_data.get("tags", [])

    def clean_funding_sources_json(self):
        raw = self.cleaned_data.get("funding_sources_json") or "[]"
        try:
            data = json.loads(raw) if isinstance(raw, str) else raw
        except json.JSONDecodeError as e:
            raise forms.ValidationError("Invalid funding sources data.") from e

        if not isinstance(data, list):
            raise forms.ValidationError("Funding sources must be a list.")

        for item in data:
            if not isinstance(item, dict):
                raise forms.ValidationError("Invalid funding source entry.")

            funder_name = (item.get("funder_name") or "").strip()
            funder_id = (item.get("funder_id") or "").strip()

            if not funder_name:
                raise forms.ValidationError("Each funding source must have a funder name.")
            if not funder_id:
                raise forms.ValidationError("Each funding source must be selected from the Invenio funders list.")

        return json.dumps(data)

    def validate_subdomain(self, subdomain_input):
        # If user did not input subdomain, set it to our standard release name
        if not subdomain_input:
            subdomain = "r" + uuid.uuid4().hex[0:8]
            if Subdomain.objects.filter(subdomain=subdomain_input).exists():
                error_message = "Wow, you just won the lottery. Contact us for a free chocolate bar."
                raise forms.ValidationError(error_message)
            return SubdomainTuple(subdomain, False)

        # Check if the instance has an existing subdomain
        current_subdomain = getattr(self.instance, "subdomain", None)

        # Validate if the subdomain input matches the instance's current subdomain
        if current_subdomain and current_subdomain.subdomain == subdomain_input:
            return SubdomainTuple(subdomain_input, current_subdomain.is_created_by_user)

        # Convert the subdomain to lowercase. OK because we force convert to lowecase in the UI.
        subdomain_input = subdomain_input.lower()

        # Check if the subdomain adheres to helm rules
        subdomain_candidate = SubdomainCandidateName(subdomain_input, self.project_pk)

        try:
            subdomain_candidate.validate_subdomain()
        except forms.ValidationError as e:
            raise forms.ValidationError(f"{e.message}")

        # Check for subdomain availability
        if not subdomain_candidate.is_available():
            error_message = "Subdomain already exists. Please choose another one."
            raise forms.ValidationError(error_message)

        return SubdomainTuple(subdomain_input, True)

    @property
    def changed_data(self):
        # Override the default changed_data to handle the tags field
        changed_data = super().changed_data
        if "tags" in changed_data and hasattr(self.instance, "tags"):
            new_tags = self.cleaned_data.get("tags", [])
            if list(new_tags) == self._original_tags:
                changed_data.remove("tags")
        return changed_data

    class Meta:
        # Specify model to be used
        model = BaseAppInstance
        fields = "__all__"


class AppBaseForm(BaseForm):
    """
    Generic form for apps that require some compute power,
    so you can treat this form as an actual base form for the most of the apps
    """

    volume = forms.ModelChoiceField(
        queryset=VolumeInstance.objects.none(), required=False, empty_label="None", initial=None
    )

    flavor = forms.ModelChoiceField(queryset=Flavor.objects.none(), required=True, empty_label=None)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def _setup_form_fields(self):
        super()._setup_form_fields()
        flavor_queryset = (
            Flavor.objects.filter(project__pk=self.project_pk) if self.project_pk else Flavor.objects.none()
        )
        # Handle Flavor field
        self.fields["flavor"].label = "Hardware"
        self.fields["flavor"].queryset = flavor_queryset
        self.fields["flavor"].initial = flavor_queryset.first()  # if flavor_queryset else None

        # Handle Access field
        self.fields["access"].label = "Permission"

        self.fields["subdomain"].help_text = "Choose subdomain, create a new one or leave blank to get a random one."
