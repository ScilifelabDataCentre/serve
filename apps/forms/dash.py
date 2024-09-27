from crispy_forms.layout import HTML, Div, Field, Layout
from django import forms

from apps.forms.base import AppBaseForm
from apps.forms.field.common import SRVCommonDivField
from apps.models import DashInstance
from projects.models import Flavor

__all__ = ["DashForm"]


class DashForm(AppBaseForm):
    flavor = forms.ModelChoiceField(queryset=Flavor.objects.none(), required=False, empty_label=None)
    port = forms.IntegerField(min_value=3000, max_value=9999, required=True)
    image = forms.CharField(max_length=255, required=True)

    def _setup_form_fields(self):
        # Handle Volume field
        super()._setup_form_fields()

    def _setup_form_helper(self):
        super()._setup_form_helper()
        body = Div(
            SRVCommonDivField("name", placeholder="Name your app"),
            SRVCommonDivField("description", rows="3", placeholder="Provide a detailed description of your app"),
            SRVCommonDivField("tags"),
            SRVCommonDivField(
                "subdomain", placeholder="Enter a subdomain or leave blank for a random one", spinner=True
            ),
            SRVCommonDivField("flavor"),
            SRVCommonDivField("access"),
            SRVCommonDivField(
                "note_on_linkonly_privacy",
                placeholder="Describe why you want to make the app accessible only via a link",
            ),
            SRVCommonDivField("source_code_url", placeholder="Provide a link to the public source code"),
            SRVCommonDivField("port", placeholder="8000"),
            SRVCommonDivField("image", placeholder="registry/repository/image:tag"),
            css_class="card-body",
        )

        self.helper.layout = Layout(body, self.footer)

    class Meta:
        model = DashInstance
        fields = [
            "name",
            "description",
            "flavor",
            "access",
            "note_on_linkonly_privacy",
            "source_code_url",
            "port",
            "image",
            "tags",
        ]
        labels = {
            "tags": "Keywords",
            "note_on_linkonly_privacy": "Reason for choosing the link only option",
        }
