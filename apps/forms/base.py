import uuid

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Button, Div, Submit
from django import forms
from django.shortcuts import get_object_or_404

from apps.forms.field.widget import SubdomainInputGroup
from apps.models import BaseAppInstance, Subdomain, VolumeInstance
from apps.types_.subdomain import SubdomainCandidateName, SubdomainTuple
from projects.models import Flavor, Project

__all__ = ["BaseForm", "AppBaseForm"]


class BaseForm(forms.ModelForm):
    """The most generic form for apps running on serve. Current intended use is for VolumesK8S type apps"""

    subdomain = forms.CharField(
        required=False,
        min_length=3,
        max_length=53,
        widget=SubdomainInputGroup(base_widget=forms.TextInput, data={}),
    )

    def __init__(self, *args, **kwargs):
        self.project_pk = kwargs.pop("project_pk", None)
        self.project = get_object_or_404(Project, pk=self.project_pk) if self.project_pk else None
        self.model_name = self._meta.model._meta.verbose_name.replace("Instance", "")

        super().__init__(*args, **kwargs)

        self._setup_form_fields()
        self._setup_form_helper()

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
        if self.instance and self.instance.pk:
            self.instance.refresh_from_db()
            self._original_tags = list(self.instance.tags.all())
        else:
            self._original_tags = []

    def _setup_form_helper(self):
        # Create a footer for submit form or cancel
        self.footer = Div(
            Button("cancel", "Cancel", css_class="btn-danger", onclick="window.history.back()"),
            Submit("submit", "Submit"),
            css_class="card-footer d-flex justify-content-between",
        )
        self.helper = FormHelper(self)
        self.helper.form_method = "post"

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
        tags = cleaned_data.get("tags", None)
        if tags is None:
            return []
        return tags

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
        if "tags" in changed_data:
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

        # Handle Volume field
        volume_queryset = (
            VolumeInstance.objects.filter(project__pk=self.project_pk).exclude(app_status__status="Deleted")
            if self.project_pk
            else VolumeInstance.objects.none()
        )

        self.fields["volume"].queryset = volume_queryset
        self.fields["volume"].initial = volume_queryset
        self.fields["volume"].help_text = f"Select a volume to attach to your {self.model_name}."

        self.fields["subdomain"].help_text = "Choose subdomain, create a new one or leave blank to get a random one."
