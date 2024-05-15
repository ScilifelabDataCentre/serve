from crispy_forms.layout import Layout, Div, Field, HTML
from django import forms

from apps.forms.base import AppBaseForm
from apps.models import VolumeInstance, JupyterInstance
from projects.models import Flavor

__all__ = [
    "JupyterForm"
]


class JupyterForm(AppBaseForm):
    
    def _setup_form_helper(self):
        super()._setup_form_helper()
        body = Div(
            Field("name", placeholder="Name your app"),
            Field("volume"),
            Field("access"),
            Field("flavor"),
            

            css_class="card-body")

        self.helper.layout = Layout(
            body,
            self.footer
        )

    class Meta:
        model = JupyterInstance
        fields = ["name", "volume", "flavor", "access"]