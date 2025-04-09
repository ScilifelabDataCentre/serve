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
            Field("name", placeholder="Name your app"),
            css_class="card-body",
        )

        self.helper.layout = Layout(body, self.footer)

    class Meta:
        model = MLFlowInstance
        fields = ["name"]
