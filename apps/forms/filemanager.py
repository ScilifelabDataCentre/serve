from crispy_forms.layout import HTML, Button, Div, Field, Layout, Submit
from django import forms

from apps.forms.base import AppBaseForm
from apps.models import FilemanagerInstance, VolumeInstance

__all__ = ["FilemanagerForm"]


class FilemanagerForm(AppBaseForm):
    volume = forms.ModelMultipleChoiceField(queryset=VolumeInstance.objects.none(), required=False)

    def _setup_form_helper(self):
        super()._setup_form_helper()

        self.footer = Div(
            Button(
                "cancel",
                "Cancel",
                css_class="btn-outline-dark btn-outline-cancel me-2",
                onclick="window.history.back()",
            ),
            Submit("submit", "Activate", css_class="btn-profile text-dark"),
            css_class="card-footer d-flex justify-content-end",
        )
        body = Div(
            Div(
                HTML(
                    """<p>You are about to activate file manager on SciLifeLab Serve.
                    You can use it to upload or download files to a volume associated with this project.
                    This service will be active for 24 hours and automatically terminated afterwards.
                    The uploaded files will stay on the volume even after this service has been terminated.</p>
                    """
                ),
                HTML("<p>Click 'Activate' to activate file manager</p>"),
                css_class="p-3 my-3",
            ),
            Field("name", type="hidden"),
            Field("access", type="hidden"),
            Field("flavor", type="hidden"),
            Field("volume"),
            css_class="card-body",
        )

        self.fields["name"].initial = "File Manager"
        self.fields["access"].initial = "project"
        self.helper.layout = Layout(body, self.footer)

    class Meta:
        model = FilemanagerInstance
        fields = ["name", "access", "flavor", "volume"]
