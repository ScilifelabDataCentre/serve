from crispy_forms.layout import Div, Field, Layout

from apps.forms.base import BaseForm
from apps.models import MLFlowInstance

__all__ = [
    "MLFlowAppForm",
]


class MLFlowAppForm(BaseForm):
    def _setup_form_helper(self):
        super()._setup_form_helper()
        body = Div(
            Field("name", placeholder="Name your app"),
            Field("subdomain", placeholder="Enter a subdomain or leave blank for a random one"),
            css_class="card-body",
        )

        self.helper.layout = Layout(body, self.footer)

    class Meta:
        model = MLFlowInstance
        fields = ["name"]
