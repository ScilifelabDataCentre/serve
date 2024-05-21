from crispy_forms.layout import HTML, Div, Field, Layout
from django import forms

from apps.forms.base import AppBaseForm
from apps.models import JupyterInstance, VolumeInstance
from projects.models import Flavor

__all__ = ["JupyterForm"]


class JupyterForm(AppBaseForm):
    def _setup_form_helper(self):
        super()._setup_form_helper()
        body = Div(
            self.get_common_field("name", placeholder="Name your app"),
            Field("volume"),
            self.get_common_field("access"),
            self.get_common_field("flavor"),
            css_class="card-body",
        )

        self.helper.layout = Layout(body, self.footer)

    class Meta:
        model = JupyterInstance
        fields = ["name", "volume", "flavor", "access"]
        
