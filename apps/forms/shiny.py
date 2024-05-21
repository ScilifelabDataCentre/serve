from crispy_forms.layout import HTML, Div, Field, Layout
from django import forms

from apps.forms.base import AppBaseForm
from apps.models import ShinyInstance
from projects.models import Flavor

__all__ = ["ShinyForm"]


class ShinyForm(AppBaseForm):
    flavor = forms.ModelChoiceField(queryset=Flavor.objects.none(), required=False, empty_label=None)
    port = forms.IntegerField(min_value=3000, max_value=9999, required=True)
    image = forms.CharField(max_length=255, required=True)
    proxy = forms.BooleanField(
        required=False,
        initial=False,
        label="Activate Proxy",
        help_text="""<i class='bi bi-question-circle me-2'></i> Check this box if your
            app requires lots of compute power. This will enable a proxy to handle the load.
            """,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if self.instance and self.instance.pk:
            self.initial_subdomain = self.instance.subdomain.subdomain
            self.initial_proxy = self.instance.proxy

    def _setup_form_fields(self):
        # Handle Volume field
        super()._setup_form_fields()

    def _setup_form_helper(self):
        super()._setup_form_helper()
        body = Div(
            self.get_common_field("name", placeholder="Name your app"),
            self.get_common_field("description", rows="3", placeholder="Provide a detailed description of your app"),
            Field(
                "proxy",
            ),
            Div(
                self.get_common_field(
                    "subdomain", placeholder="Enter a subdomain or leave blank for a random one", spinner=True
                ),
                css_class="form-input-with-spinner",
            ),
            self.get_common_field("flavor"),
            self.get_common_field("access"),
            self.get_common_field("source_code_url", placeholder="Provide a link to the public source code"),
            self.get_common_field("port", placeholder="3838"),
            self.get_common_field("image", placeholder="registry/repository/image:tag"),
            Field("tags"),
            css_class="card-body",
        )

        self.helper.layout = Layout(body, self.footer)

    def clean(self):
        cleaned_data = super().clean()
        access = cleaned_data.get("access", None)
        source_code_url = cleaned_data.get("source_code_url", None)

        if access == "public" and not source_code_url:
            self.add_error("source_code_url", "Source is required when access is public.")

        proxy = cleaned_data.get("proxy")
        subdomain = cleaned_data.get("subdomain")

        # Check if boolfield has changed
        if self.instance and self.instance.pk:
            if proxy != self.initial_proxy:
                # Ensure charfield is also changed
                if subdomain == self.initial_subdomain:
                    self.add_error("subdomain", "Subdomain must be changed if proxy is changed.")

        return cleaned_data

    class Meta:
        model = ShinyInstance
        fields = [
            "name",
            "description",
            "proxy",
            "volume",
            "flavor",
            "access",
            "source_code_url",
            "port",
            "image",
            "tags",
        ]
