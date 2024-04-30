import uuid
from typing import Any
from django import forms
from django.utils.safestring import mark_safe
from django.core.exceptions import ValidationError

from .models import AbstractAppInstance, JupyterInstance, Social, Subdomain
from projects.models import Flavor, Project
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Submit, Button, Div, HTML, Field, Hidden


class BaseForm(forms.ModelForm):

    subdomain = forms.CharField(required=False)
    
    def __init__(self, *args, **kwargs):
        self.project_pk = kwargs.pop('project_pk', None)
        self.project = Project.objects.get(pk=self.project_pk) if self.project_pk else None
        
        super().__init__(*args, **kwargs)
        
        flavor_queryset = Flavor.objects.filter(project__pk=self.project_pk) if self.project_pk else Flavor.objects.none()
        
        # Handle Flavor field
        self.fields["flavor"].label = "Hardware"
        self.fields["flavor"].queryset = flavor_queryset
        self.fields["flavor"].initial = flavor_queryset.first() if flavor_queryset else None

        # Handle Name field
        self.fields["name"].label = mark_safe('Name: <span class="bi bi-question-circle" style="color: #989da0" data-bs-toggle="tooltip" title="" data-bs-placement="right" data-bs-original-title="The container wait time set for the ShinyProxy instance. Timeout for the container to be available to ShinyProxy; defaults to 20s (20000). I.e. if the container with the app is not in ready status within this time ShinyProxy will give up trying to reach it."></span>')
        self.fields["name"].initial = ""
        
        # Handle Access field
        self.fields["access"].label = "Permission"
        
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
        subdomain = cleaned_data.get("subdomain", None)
        # Raise validation error if subdomain exists
        print("SUBDOMAIN IN CLEAN FUNCTION IS:", subdomain, flush=True)
        if subdomain and Subdomain.objects.filter(subdomain=subdomain).exists():
            raise ValidationError(
                    "Subdomain already exists. Please choose another one."
                )       
        elif not subdomain: 
            # If user did not input subdomain, set it to our standard release name
            subdomain = "r" + uuid.uuid4().hex[0:8]
            cleaned_data["subdomain"] = subdomain
            print("RANDOM SUBDOMAIN IN CLEAN FUNCTION IS:", subdomain, flush=True)
        return cleaned_data

    class Meta:
        # Specify model to be used
        model = AbstractAppInstance
        fields = "__all__"


class JupyterForm(BaseForm):
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        body = Div(
            Field("name", placeholder="Name your app"),
            Field("subdomain", placeholder="Enter a subdomain or leave blank for a random one"),
            Field("flavor"),
            Field("description", rows="3", placeholder="Provide a detailed description of your app"),
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
        fields = ["name", "flavor", "tags", "description", "access", "note_on_linkonly_privacy"]  
    
