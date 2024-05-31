from crispy_forms.layout import Div, Field, Layout

from apps.forms.base import BaseForm
from apps.models import VolumeInstance

__all__ = ["VolumeForm"]


class VolumeForm(BaseForm):
    def _setup_form_helper(self):
        super()._setup_form_helper()
        body = Div(
            Field("name", placeholder="Name your app"),
            Field("size"),
            Field("subdomain", placeholder="Enter a subdomain or leave blank for a random one"),
            css_class="card-body",
        )

        self.helper.layout = Layout(body, self.footer)

    # create meta class
    class Meta:
        model = VolumeInstance
        fields = ["name", "size"]
