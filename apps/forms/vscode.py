from crispy_bootstrap5.bootstrap5 import BS5Accordion
from crispy_forms.bootstrap import Accordion, AccordionGroup, PrependedText
from crispy_forms.layout import Div, Field, Layout
from django import forms
from django.utils.safestring import mark_safe

from apps.forms.base import AppBaseForm
from apps.forms.field.common import SRVCommonDivField
from apps.forms.mixins import VolumeMixin
from apps.models import VolumeInstance, VSCodeInstance

__all__ = ["VSCodeForm"]


class VSCodeForm(VolumeMixin, AppBaseForm):
    volume = forms.ModelMultipleChoiceField(queryset=VolumeInstance.objects.none(), required=False)

    def _setup_form_fields(self):
        super()._setup_form_fields()
        self._set_up_volume_field()

    def _setup_form_helper(self):
        super()._setup_form_helper()

        # Define AccordionGroups
        general = AccordionGroup(
            mark_safe("<h3>Description</h3>"),
            SRVCommonDivField("name", required=True),
            SRVCommonDivField("access"),
            active=True,
        )

        configuration = AccordionGroup(
            mark_safe("<h3>Configuration</h3>"),
            self._set_up_volume_helper(),
            SRVCommonDivField("flavor"),
            active=True,
        )
        accordion = BS5Accordion(
            configuration,
            general,
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
