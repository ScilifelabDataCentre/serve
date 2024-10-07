from crispy_forms.layout import Div, Field, Layout

from apps.forms.base import AppBaseForm
from apps.forms.field.common import SRVCommonDivField
from apps.models import TissuumapsInstance

__all__ = ["TissuumapsForm"]


class TissuumapsForm(AppBaseForm):
    def _setup_form_fields(self):
        # Handle Volume field
        super()._setup_form_fields()
        volume_form_field = self.fields["volume"]
        volume_form_field.required = True
        volume_form_field.empty_label = None

    def _setup_form_helper(self):
        super()._setup_form_helper()
        body = Div(
            SRVCommonDivField("name", placeholder="Name your app"),
            SRVCommonDivField("description", rows="3", placeholder="Provide a detailed description of your app"),
            SRVCommonDivField("tags"),
            SRVCommonDivField(
                "subdomain", placeholder="Enter a subdomain or leave blank for a random one", spinner=True
            ),
            Field("volume"),
            SRVCommonDivField("flavor"),
            SRVCommonDivField("access"),
            SRVCommonDivField(
                "note_on_linkonly_privacy",
                placeholder="Describe why you want to make the app accessible only via a link",
            ),
            css_class="card-body",
        )

        self.helper.layout = Layout(body, self.footer)

    class Meta:
        model = TissuumapsInstance
        fields = ["name", "description", "volume", "flavor", "access", "note_on_linkonly_privacy", "tags"]
        labels = {"tags": "Keywords", "note_on_linkonly_privacy": "Reason for choosing the link only option"}
