from crispy_forms.layout import HTML, Div, Field, Layout
from django import forms

from apps.forms.base import AppBaseForm
from apps.models import TissuumapsInstance
from projects.models import Flavor

__all__ = ["TissuumapsForm"]


class TissuumapsForm(AppBaseForm):
    def _setup_form_fields(self):
        # Handle Volume field
        super()._setup_form_fields()

    def _setup_form_helper(self):
        super()._setup_form_helper()
        body = Div(
            Field("name", placeholder="Name your app"),
            Field("description", rows="3", placeholder="Provide a detailed description of your app"),
            Field("subdomain", placeholder="Enter a subdomain or leave blank for a random one"),
            Field("volume"),
            Field("flavor"),
            Field("access"),
            Field("tags"),
            css_class="card-body",
        )

        self.helper.layout = Layout(body, self.footer)

    class Meta:
        model = TissuumapsInstance
        fields = ["name", "description", "volume", "flavor", "access", "tags"]
