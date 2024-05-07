from crispy_forms.layout import Layout, Div, Field, HTML
from django import forms

from apps.forms.base import AppBaseForm
from apps.models import VolumeInstance, JupyterInstance
from projects.models import Flavor

__all__ = [
    "JupyterForm"
]


class JupyterForm(AppBaseForm):
    volume = forms.ModelMultipleChoiceField(queryset=VolumeInstance.objects.none(), widget=forms.CheckboxSelectMultiple,
                                            required=False)
    flavor = forms.ModelChoiceField(queryset=Flavor.objects.none(), widget=forms.RadioSelect, required=False)

    def _setup_form_fields(self):
        # Handle Volume field
        super()._setup_form_fields()
        volume_queryset = VolumeInstance.objects.filter(project__pk=self.project_pk) if self.project_pk else VolumeInstance.objects.none()
        self.fields["volume"].queryset = volume_queryset

    def _setup_form_helper(self):
        super()._setup_form_helper()
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

    class Meta:
        model = JupyterInstance
        fields = ["name", "volume", "flavor", "tags", "description", "access", "note_on_linkonly_privacy"]