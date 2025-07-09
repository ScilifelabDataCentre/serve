from crispy_forms.layout import Div, Layout

from apps.forms.base import BaseForm
from apps.forms.field.common import SRVCommonDivField
from apps.models import DepictioInstance

__all__ = ["DepictioForm"]


class DepictioForm(BaseForm):
    def _setup_form_fields(self):
        super()._setup_form_fields()

    def _setup_form_helper(self):
        super()._setup_form_helper()
        body = Div(
            SRVCommonDivField("name", placeholder="Name your app"),
            SRVCommonDivField("description", rows="3", placeholder="Provide a detailed description of your app"),
            SRVCommonDivField("access"),
            css_class="card-body",
        )

        self.helper.layout = Layout(body, self.footer)

    class Meta:
        model = DepictioInstance
        fields = ["name", "description", "access"]
