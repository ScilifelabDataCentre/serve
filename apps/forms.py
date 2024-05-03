import uuid
from typing import Any
from django import forms
from django.utils.safestring import mark_safe
from django.core.exceptions import ValidationError

from .models import AbstractAppInstance, JupyterInstance, Social, Subdomain, VolumeInstance
from projects.models import Flavor, Project
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Submit, Button, Div, HTML, Field, Hidden


class BaseForm(forms.ModelForm):

    subdomain = forms.CharField(required=False)
    
    def __init__(self, *args, **kwargs):
        self.project_pk = kwargs.pop('project_pk', None)
        self.project = Project.objects.get(pk=self.project_pk) if self.project_pk else None
        
        super().__init__(*args, **kwargs)
        
        # Populate subdomain field with instance subdomain if it exists
        if self.instance and self.instance.pk:
            self.fields["subdomain"].initial = self.instance.subdomain.subdomain
        

        # Handle Name field
        self.fields["name"].label = mark_safe('Name: <span class="bi bi-question-circle" style="color: #989da0" data-bs-toggle="tooltip" title="" data-bs-placement="right" data-bs-original-title="The container wait time set for the ShinyProxy instance. Timeout for the container to be available to ShinyProxy; defaults to 20s (20000). I.e. if the container with the app is not in ready status within this time ShinyProxy will give up trying to reach it."></span>')
        self.fields["name"].initial = ""
        

        
        # Create a footer for submit form or cancel
        self.footer = Div(
            Button('cancel', 'Cancel', css_class='btn-danger', onclick='window.history.back()'),
            Submit('submit', 'Submit'),
            css_class="card-footer d-flex justify-content-between"
            )
        
        self.helper = FormHelper(self)
        self.helper.form_method = 'post'


    def clean(self) -> dict[str, Any]:
        cleaned_data = super().clean()

        # Handle subdomain
        subdomain_input = cleaned_data.get("subdomain")
        
        # If user did not input subdomain, set it to our standard release name
        if not subdomain_input:
            subdomain = "r" + uuid.uuid4().hex[0:8]
            if Subdomain.objects.filter(subdomain=subdomain_input).exists():
                error_message = "Wow, you just won the lottery. Contact us for a free chocolate bar."
                raise ValidationError(error_message)
            cleaned_data["subdomain"] = subdomain
            return cleaned_data
        
        # Check if the instance has an existing subdomain
        current_subdomain = getattr(self.instance, 'subdomain', None)
        
        # Validate if the subdomain input matches the instance's current subdomain
        if current_subdomain and current_subdomain.subdomain == subdomain_input:
            return cleaned_data
        
        # Check for subdomain availability
        if Subdomain.objects.filter(subdomain=subdomain_input).exists():
            error_message = "Subdomain already exists. Please choose another one."
            raise ValidationError(error_message)

        return cleaned_data

    class Meta:
        # Specify model to be used
        model = AbstractAppInstance
        fields = "__all__"


class BaseFormExtended(BaseForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        flavor_queryset = Flavor.objects.filter(project__pk=self.project_pk) if self.project_pk else Flavor.objects.none()
        
        # Handle Flavor field
        self.fields["flavor"].label = "Hardware"
        self.fields["flavor"].queryset = flavor_queryset
        self.fields["flavor"].initial = flavor_queryset.first() if flavor_queryset else None
        
        # Handle Access field
        self.fields["access"].label = "Permission"
        

class JupyterForm(BaseFormExtended):
    
    volume = forms.ModelMultipleChoiceField(queryset=VolumeInstance.objects.none(), widget=forms.CheckboxSelectMultiple, required=False)
    flavor = forms.ModelChoiceField(queryset=Flavor.objects.none(), widget=forms.RadioSelect, required=False)
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Handle Volume field
        volume_queryset = VolumeInstance.objects.filter(project__pk=self.project_pk) if self.project_pk else VolumeInstance.objects.none()
        self.fields["volume"].queryset = volume_queryset
        


        body = Div(
            Field("name", placeholder="Name your app"),
            Field("description", rows="3", placeholder="Provide a detailed description of your app"),
            Field("subdomain", placeholder="Enter a subdomain or leave blank for a random one"),
            Field("volume"),
            Field("flavor"),
            Field("access"),
            Field("note_on_linkonly_privacy", rows="3"),
            Field("tags"),
            css_class="card-body")

        self.helper.layout = Layout(
            body,
            self.footer
            )

    # create meta class
    class Meta:
        model = JupyterInstance
        fields = ["name", "volume", "flavor", "tags", "description", "access", "note_on_linkonly_privacy"]  
    

class VolumeForm(BaseForm):
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        body = Div(
            Field("name", placeholder="Name your app"),
            Field("size"),
            Field("subdomain", placeholder="Enter a subdomain or leave blank for a random one"),
            css_class="card-body")

        self.helper.layout = Layout(
            body,
            self.footer
            )

    # create meta class
    class Meta:
        model = VolumeInstance
        fields = ["name", "size"]  
