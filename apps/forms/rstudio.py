from crispy_forms.layout import HTML, Div, Field, Layout
from django import forms
from django.utils.safestring import mark_safe

from apps.forms.base import AppBaseForm
from apps.forms.field.common import SRVCommonDivField
from apps.models import RStudioInstance, VolumeInstance

__all__ = ["RStudioForm"]


class RStudioForm(AppBaseForm):
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

    def _setup_form_helper(self):
        super()._setup_form_helper()
        body = Div(
            SRVCommonDivField("name", placeholder="Name your app"),
            Field("volume"),
            SRVCommonDivField("flavor"),
            SRVCommonDivField("access"),
            SRVCommonDivField("environment"),
            css_class="card-body",
        )

        self.helper.layout = Layout(body, self.footer)

    class Meta:
        model = RStudioInstance
        fields = ["name", "volume", "flavor", "access", "environment"]
