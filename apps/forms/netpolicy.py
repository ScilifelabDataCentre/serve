from crispy_forms.layout import Div, Field, Layout

from apps.forms.base import BaseForm
from apps.models import NetpolicyInstance

__all__ = ["NetpolicyForm"]


class NetpolicyForm(BaseForm):
    def _setup_form_helper(self):
        super()._setup_form_helper()
        body = Div(Field("name", placeholder="Name your app"), css_class="card-body")

        self.helper.layout = Layout(body, self.footer)

    # create meta class
    class Meta:
        model = NetpolicyInstance
        fields = ["name"]
