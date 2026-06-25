from crispy_bootstrap5.bootstrap5 import BS5Accordion
from crispy_forms.bootstrap import Accordion, AccordionGroup, PrependedText
from crispy_forms.layout import HTML, Div, Field, Layout
from django import forms
from django.utils.safestring import mark_safe

from apps.forms.base import AppBaseForm
from apps.forms.field.common import SRVCommonDivField
from apps.forms.mixins import VolumeMixin
from apps.models import RStudioInstance, VolumeInstance

__all__ = ["RStudioForm"]


class RStudioForm(VolumeMixin, AppBaseForm):
    volume = forms.ModelMultipleChoiceField(queryset=VolumeInstance.objects.none(), required=False)
    environment = forms.ModelChoiceField(queryset=None, required=True, empty_label=None)

    def _setup_form_fields(self):
        super()._setup_form_fields()
        self.fields["environment"].label = "Environment"
        self.fields["environment"].queryset = self.project.environment_set.filter(app__slug="rstudio")
        self.fields["environment"].help_text = mark_safe(
            "Select the environment to run the app in. "
            "Read more about environments in the "
            '<a href="https://serve.scilifelab.se/docs/notebooks/">documentation</a>.'
        )
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
            SRVCommonDivField("environment"),
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
        self.helper.layout = Layout(body, self._deletion_note_layout(), self.footer)

    class Meta:
        model = RStudioInstance
        fields = ["name", "volume", "flavor", "access", "environment"]
