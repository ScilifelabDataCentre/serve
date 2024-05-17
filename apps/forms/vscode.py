from crispy_forms.layout import HTML, Div, Field, Layout
from django import forms

from apps.forms.base import AppBaseForm
from apps.models import VSCodeInstance

__all__ = ["VSCodeForm"]


class VSCodeForm(AppBaseForm):
    def _setup_form_helper(self):
        super()._setup_form_helper()
        body = Div(
            Field("name", placeholder="Name your app"),
            Field("volume"),
            Field("flavor"),
            Field("access"),
            css_class="card-body",
        )

        self.helper.layout = Layout(body, self.footer)

    class Meta:
        model = VSCodeInstance
        fields = ["name", "volume", "flavor", "access"]
