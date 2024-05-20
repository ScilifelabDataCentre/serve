from crispy_forms.layout import HTML, Div, Field, Layout, MultiField
from django import forms

from apps.forms.base import AppBaseForm
from apps.models import CustomAppInstance, VolumeInstance
from projects.models import Flavor

__all__ = ["CustomAppForm"]
from apps.forms import CustomField


class CustomAppForm(AppBaseForm):
    volume = forms.ModelChoiceField(
        queryset=VolumeInstance.objects.none(), required=False, empty_label="None", initial=None
    )
    flavor = forms.ModelChoiceField(queryset=Flavor.objects.none(), required=False, empty_label=None)
    port = forms.IntegerField(min_value=3000, max_value=9999, required=True)
    image = forms.CharField(max_length=255, required=True)
    path = forms.CharField(max_length=255, required=False)

    def _setup_form_fields(self):
        # Handle Volume field
        super()._setup_form_fields()

    def _setup_form_helper(self):
        super()._setup_form_helper()
        self.fields["volume"].initial = None
        body = Div(
            self.get_common_field("name", placeholder="test"),
            self.get_common_field("description", rows=3),
            Div(
                self.get_common_field(
                    "subdomain", placeholder="Enter a subdomain or leave blank for a random one", spinner=True
                ),
                css_class="form-input-with-spinner",
            ),
            self.get_common_field("volume"),
            self.get_common_field("path", placeholder="/home/..."),
            self.get_common_field("flavor"),
            self.get_common_field("access"),
            self.get_common_field("source_code_url", placeholder="Provide a link to the public source code"),
            self.get_common_field("port", placeholder="8000"),
            self.get_common_field("image"),
            Field("tags"),
            css_class="card-body",
        )
        self.helper.layout = Layout(body, self.footer)

    def clean(self):
        cleaned_data = super().clean()
        access = cleaned_data.get("access", None)
        source_code_url = cleaned_data.get("source_code_url", None)
        path = cleaned_data.get("path", None)
        volume = cleaned_data.get("volume", None)

        if access == "public" and not source_code_url:
            self.add_error("source_code_url", "Source is required when access is public.")

        if volume and not path:
            self.add_error("path", "Path is required when volume is selected.")

        if path:
            # If new path matches current path, it is valid.
            if self.instance and getattr(self.instance, "path", None) == path:
                return cleaned_data
            # Verify that path starts with "/home"
            path = path.strip().rstrip("/").lower().replace(" ", "")
            if not path.startswith("/home"):
                self.add_error("path", 'Path must start with "/home"')

        return cleaned_data

    class Meta:
        model = CustomAppInstance
        fields = [
            "name",
            "description",
            "volume",
            "path",
            "flavor",
            "access",
            "source_code_url",
            "port",
            "image",
            "tags",
        ]
