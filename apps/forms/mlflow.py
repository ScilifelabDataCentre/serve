from crispy_forms.layout import HTML, Div, Field, Layout

from apps.forms.base import BaseForm
from apps.models import MLFlowInstance

__all__ = [
    "MLFlowAppForm",
]


class MLFlowAppForm(BaseForm):
    def _setup_form_helper(self):
        super()._setup_form_helper()
        body = Div(
            HTML(
                """
                <div class="alert alert-info" role="alert">
                <p>⚠️ Experimental Feature Notice</p>
                <p>This feature is currently in an experimental phase. Please use it with caution as
                stability and data integrity are not guaranteed. The feature could change at any time.</p>
                </div>
                <p>You are about to create a MLFlow app on SciLifeLab Serve.
                You can use it to track your machine learning experiments.
                You can start using it right away after it's created and we suggest you to start with
                reading the <a href="https://serve.scilifelab.se/docs/mlflow/">Serve User Guide for MLFlow</a> and
                <a href="https://mlflow.org/docs/latest/index.html">MLFlow Documentation</a>.</p>
                """
            ),
            Field("name", required=True),
            css_class="card-body",
        )

        self.helper.layout = Layout(body, self.footer)

    def clean_subdomain(self):
        if self.instance and self.instance.pk and "subdomain" not in self.data and self.instance.subdomain:
            return self.validate_subdomain(self.instance.subdomain.subdomain)

        return super().clean_subdomain()

    @property
    def changed_data(self):
        changed_data = super().changed_data
        if self.instance and self.instance.pk and "subdomain" not in self.data and "subdomain" in changed_data:
            changed_data.remove("subdomain")

        return changed_data

    class Meta:
        model = MLFlowInstance
        fields = ["name"]
