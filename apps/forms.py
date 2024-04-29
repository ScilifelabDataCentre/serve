from django import forms
from django.utils.safestring import mark_safe

from .models import AbstractAppInstance, JupyterInstance, Social
from projects.models import Flavor
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Submit, Button, Div, HTML, Field, Hidden


class AppInstanceForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        project_pk = kwargs.pop('project_pk', None)
        super().__init__(*args, **kwargs)
        
        flavor_queryset = Flavor.objects.filter(project__pk=project_pk) if project_pk else Flavor.objects.none()
        
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
            Submit('submit', 'Submit'),
            Button('cancel', 'Cancel', css_class='btn-danger', onclick='window.history.back()'),
            css_class="card-footer d-flex justify-content-between")

    class Meta:
        # Specify model to be used
        model = AbstractAppInstance
        fields = "__all__"


class JupyterForm(AppInstanceForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.helper = FormHelper(self)
        self.helper.form_method = 'post'
        #self.helper.form_action = "{% url 'apps:create' %}"
        
        body = Div(
            Field("name", placeholder="Name your app"),
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
        # specify model to be used
        model = JupyterInstance
        fields = ["name", "flavor", "tags", "description", "access", "note_on_linkonly_privacy"]  
        