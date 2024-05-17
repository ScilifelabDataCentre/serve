from crispy_forms.layout import HTML, Div, Field, Layout
from django import forms

from apps.forms.base import AppBaseForm
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
            self.get_common_field("name", placeholder="Name your app"),
            self.get_common_field("description", rows="3", placeholder="Provide a detailed description of your app"),
            self.get_common_field("subdomain", placeholder="Enter a subdomain or leave blank for a random one"),
            self.get_common_field("flavor"),
            self.get_common_field("access"),
            self.get_common_field(
                "note_on_linkonly_privacy",
                placeholder="Describe why you want to make the app accessible only via a link",
            ),
            self.get_common_field("source_code_url", placeholder="Provide a link to the public source code"),
            self.get_common_field("port", placeholder="8000"),
            self.get_common_field("image", placeholder="registry/repository/image:tag"),
            Field("tags"),
            css_class="card-body",
        )

        self.helper.layout = Layout(body, self.footer)

    def clean(self):
        cleaned_data = super().clean()
        access = cleaned_data.get("access")
        source_code_url = cleaned_data.get("source_code_url")

        if access == "public" and not source_code_url:
            self.add_error("source_code_url", "Source is required when access is public.")

        return cleaned_data

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
