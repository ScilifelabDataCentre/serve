from crispy_forms.layout import HTML, Div, Field, Layout
from django import forms

from apps.forms.base import AppBaseForm
from apps.forms.field.common import SRVCommonDivField
from apps.models import JupyterInstance, VolumeInstance

__all__ = ["JupyterForm"]


class JupyterForm(AppBaseForm):
    volume = forms.ModelMultipleChoiceField(queryset=VolumeInstance.objects.none(), required=False)

    def _setup_form_helper(self):
        super()._setup_form_helper()

        body = Div(
            SRVCommonDivField("name", placeholder="Name your app"),
            Field("volume"),
            SRVCommonDivField("access"),
            SRVCommonDivField("flavor"),
            css_class="card-body",
        )

        self.helper.layout = Layout(body, self.footer)

    class Meta:
        model = JupyterInstance
        fields = ["name", "volume", "flavor", "access"]
