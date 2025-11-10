from crispy_bootstrap5.bootstrap5 import BS5Accordion
from crispy_forms.bootstrap import Accordion, AccordionGroup, PrependedText
from crispy_forms.layout import Div, Field, Layout
from django import forms
from django.utils.safestring import mark_safe

from apps.forms.base import AppBaseForm
from apps.forms.field.common import SRVCommonDivField
from apps.models import VolumeInstance, VSCodeInstance

__all__ = ["VSCodeForm"]


class VSCodeForm(AppBaseForm):
    volume = forms.ModelMultipleChoiceField(queryset=VolumeInstance.objects.none(), required=False)

    def _setup_form_helper(self):
        super()._setup_form_helper()

        # Define AccordionGroups
        general = AccordionGroup(
            mark_safe("<h3>App Metadata</h3>"),
            SRVCommonDivField("name", placeholder="Name your app"),
            SRVCommonDivField("access"),
            active=True,
        )

        configuration = AccordionGroup(
            mark_safe("<h3>Configuration Settings</h3>"),
            Field("volume"),
            SRVCommonDivField("flavor"),
            active=True,
        )
        accordion = BS5Accordion(
            general,
            configuration,
            always_open=True,
            css_class="form-accordion",
        )
        accordion.always_open = True  # Force property for Bootstrap 5.3+

        body = Div(accordion, css_class="card-body")
        body.always_open = True
        self.helper.layout = Layout(body, self.footer)

    class Meta:
        model = VSCodeInstance
        fields = ["name", "volume", "flavor", "access"]
