from crispy_bootstrap5.bootstrap5 import BS5Accordion
from crispy_forms.bootstrap import Accordion, AccordionGroup, PrependedText
from crispy_forms.layout import HTML, Div, Field, Layout
from django import forms
from django.utils.safestring import mark_safe

from apps.forms.base import AppBaseForm
from apps.forms.field.common import SRVCommonDivField
from apps.models import JupyterInstance, VolumeInstance

__all__ = ["JupyterForm"]


class JupyterForm(AppBaseForm):
    volume = forms.ModelMultipleChoiceField(queryset=VolumeInstance.objects.none(), required=False)
    environment = forms.ModelChoiceField(queryset=None, required=True, empty_label=None)

    def _setup_form_fields(self):
        super()._setup_form_fields()
        self.fields["environment"].label = "Environment"
        self.fields["environment"].queryset = self.project.environment_set.filter(app__slug="jupyter-lab")
        self.fields["environment"].help_text = mark_safe(
            "Select the environment to run the app in. "
            "Read more about environments in the "
            '<a href="https://serve.scilifelab.se/docs/notebooks/">documentation</a>.'
        )

    def _setup_form_helper(self):
        super()._setup_form_helper()

        # Define AccordionGroups
        general = AccordionGroup(
            mark_safe("<h4>App Metadata</h4>"),
            SRVCommonDivField("name", placeholder="Name your app"),
            active=True,
        )

        deployment = AccordionGroup(
            mark_safe("<h4>Deployment Settings</h4>"),
            Field("volume"),
            SRVCommonDivField("access"),
            SRVCommonDivField("flavor"),
            SRVCommonDivField("environment"),
            active=True,
        )
        accordion = BS5Accordion(
            general,
            deployment,
            always_open=True,
            css_class="form-accordion",
        )
        accordion.always_open = True  # Force property for Bootstrap 5.3+

        body = Div(accordion, css_class="card-body")
        body.always_open = True
        self.helper.layout = Layout(body, self.footer)

    class Meta:
        model = JupyterInstance
        fields = ["name", "volume", "flavor", "access", "environment"]
