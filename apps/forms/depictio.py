from crispy_bootstrap5.bootstrap5 import BS5Accordion
from crispy_forms.bootstrap import AccordionGroup
from crispy_forms.layout import Div, Layout
from django.utils.safestring import mark_safe

from apps.forms.base import BaseForm
from apps.forms.field.common import SRVCommonDivField
from apps.models import DepictioInstance

__all__ = ["DepictioForm"]


class DepictioForm(BaseForm):
    def _setup_form_fields(self):
        super()._setup_form_fields()

    def _setup_form_helper(self):
        super()._setup_form_helper()
        # Define AccordionGroups
        general = AccordionGroup(
            mark_safe("<h4>App Metadata</h4>"),
            SRVCommonDivField("name", placeholder="Name your app"),
            SRVCommonDivField("description", rows="3", placeholder="Provide a detailed description of your app"),
            SRVCommonDivField("access"),
            active=True,
        )

        accordion = BS5Accordion(
            general,
            always_open=True,
            css_class="form-accordion",
        )
        accordion.always_open = True  # Force property for Bootstrap 5.3+

        body = Div(accordion, css_class="card-body")
        body.always_open = True
        self.helper.layout = Layout(body, self.footer)

    class Meta:
        model = DepictioInstance
        fields = ["name", "description", "access"]
