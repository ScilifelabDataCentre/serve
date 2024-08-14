from crispy_forms.layout import HTML, Div, Field, Layout
from django import forms

from apps.forms.base import AppBaseForm
from apps.models import VolumeInstance, VSCodeInstance

__all__ = ["VSCodeForm"]


class VSCodeForm(AppBaseForm):
    volume = forms.ModelMultipleChoiceField(queryset=VolumeInstance.objects.none(), required=False)

    def _setup_form_helper(self):
        super()._setup_form_helper()
        body = Div(
            self.get_common_field("name", placeholder="Name your app"),
            Field("volume"),
            self.get_common_field("flavor"),
            self.get_common_field("access"),
            css_class="card-body",
        )

        self.helper.layout = Layout(body, self.footer)

    class Meta:
        model = VSCodeInstance
        fields = ["name", "volume", "flavor", "access"]
