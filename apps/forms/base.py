import uuid
from typing import Any

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Submit, Button, Div
from django import forms
from django.shortcuts import get_object_or_404
from django.utils.safestring import mark_safe

from apps.models import BaseAppInstance, Subdomain, VolumeInstance
from projects.models import Flavor, Project
from django.core.validators import RegexValidator

__all__ = [
    "BaseForm",
    "AppBaseForm"
]


class BaseForm(forms.ModelForm):
    """The most generic form for apps running on serve. Current intended use is for VolumesK8S type apps"""
    subdomain = forms.CharField(required=False,
                min_length=3,
                max_length=30,
               )

    def __init__(self, *args, **kwargs):
        self.project_pk = kwargs.pop('project_pk', None)
        self.project = get_object_or_404(Project, pk=self.project_pk) if self.project_pk else None
        self.model_name = self._meta.model._meta.verbose_name.replace("Instance", "")
        super().__init__(*args, **kwargs)
        self._setup_form_fields()
        self._setup_form_helper()

    def _setup_form_fields(self):
        # Populate subdomain field with instance subdomain if it exists
        if self.instance and self.instance.pk:
            self.fields["subdomain"].initial = self.instance.subdomain.subdomain
        # Handle Name field
        self.fields["name"].label = mark_safe(
            'Name: <span class="bi bi-question-circle" style="color: #989da0" data-bs-toggle="tooltip" title="" data-bs-placement="right" data-bs-original-title="The container wait time set for the ShinyProxy instance. Timeout for the container to be available to ShinyProxy; defaults to 20s (20000). I.e. if the container with the app is not in ready status within this time ShinyProxy will give up trying to reach it."></span>')
        self.fields["name"].initial = ""

    def _setup_form_helper(self):
        # Create a footer for submit form or cancel
        self.footer = Div(
            Button('cancel', 'Cancel', css_class='btn-danger', onclick='window.history.back()'),
            Submit('submit', 'Submit'),
            css_class="card-footer d-flex justify-content-between"
        )
        self.helper = FormHelper(self)
        self.helper.form_method = 'post'

    def clean_subdomain(self):
        cleaned_data = super().clean()
        subdomain_input = cleaned_data.get("subdomain")
        return self.validate_subdomain(subdomain_input)


    def validate_subdomain(self, subdomain_input):
        # First, check if the subdomain adheres to helm rules
        regex_validator=RegexValidator(
            regex=r'^[a-zA-Z0-9]*$',
        )
        try:
            regex_validator(subdomain_input)
        except forms.ValidationError as e:
            raise forms.ValidationError("Subdomain must be alphanumeric characters without space")
        
        # If user did not input subdomain, set it to our standard release name
        if not subdomain_input:
            subdomain = "r" + uuid.uuid4().hex[0:8]
            if Subdomain.objects.filter(subdomain=subdomain_input).exists():
                error_message = "Wow, you just won the lottery. Contact us for a free chocolate bar."
                raise forms.ValidationError(error_message)
            return subdomain

        # Check if the instance has an existing subdomain
        current_subdomain = getattr(self.instance, 'subdomain', None)

        # Validate if the subdomain input matches the instance's current subdomain
        if current_subdomain and current_subdomain.subdomain == subdomain_input:
            return subdomain_input

        # Check for subdomain availability
        if Subdomain.objects.filter(subdomain=subdomain_input).exists():
            error_message = "Subdomain already exists. Please choose another one."
            raise forms.ValidationError(error_message)

        return subdomain_input

    class Meta:
        # Specify model to be used
        model = BaseAppInstance
        fields = "__all__"


class AppBaseForm(BaseForm):
    """
    Generic form for apps that require some compute power,
    so you can treat this form as an actual base form for the most of the apps
    """
    volume = forms.ModelMultipleChoiceField(queryset=VolumeInstance.objects.none(), widget=forms.CheckboxSelectMultiple,
                                            required=False)
    flavor = forms.ModelChoiceField(queryset=Flavor.objects.none(), 
                                    required=True,
                                    empty_label=None)
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def _setup_form_fields(self):
        super()._setup_form_fields()
        flavor_queryset = Flavor.objects.filter(
            project__pk=self.project_pk) if self.project_pk else Flavor.objects.none()
        # Handle Flavor field
        self.fields["flavor"].label = "Hardware"
        self.fields["flavor"].queryset = flavor_queryset
        self.fields["flavor"].initial = flavor_queryset.first()# if flavor_queryset else None

        # Handle Access field
        self.fields["access"].label = "Permission"

        # Handle Volume field
        volume_queryset = VolumeInstance.objects.filter(
            project__pk=self.project_pk) if self.project_pk else VolumeInstance.objects.none()
        
        self.fields["volume"].queryset = volume_queryset
        self.fields["volume"].initial = volume_queryset.first() if volume_queryset else None
        self.fields['volume'].help_text = f"Select volume(s) to mount to your {self.model_name}."




