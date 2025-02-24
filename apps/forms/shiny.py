from crispy_forms.bootstrap import Accordion, AccordionGroup, Field, PrependedText
from crispy_forms.layout import Div, Layout
from django import forms
from django.forms.widgets import HiddenInput
from django.utils.safestring import mark_safe

from apps.forms.base import AppBaseForm
from apps.forms.field.common import SRVCommonDivField
from apps.forms.mixins import ContainerImageMixin
from apps.models import ShinyInstance
from projects.models import Flavor

__all__ = ["ShinyForm"]


class ShinyForm(ContainerImageMixin, AppBaseForm):
    flavor = forms.ModelChoiceField(queryset=Flavor.objects.none(), required=False, empty_label=None)
    port = forms.IntegerField(min_value=3000, max_value=9999, required=True)
    shiny_site_dir = forms.CharField(max_length=255, required=False, label="Path to site_dir")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if self.instance and self.instance.pk:
            self.initial_subdomain = self.instance.subdomain.subdomain

        # Setup container image field from mixin
        self._setup_container_image_field()

    def _setup_form_fields(self):
        # Handle Volume field
        super()._setup_form_fields()
        self.fields["volume"].initial = None
        self.fields["volume"].widget = HiddenInput()
        self.fields["path"].initial = "/srv/shiny-server/"
        self.fields["path"].widget = HiddenInput()
        self.fields["shiny_site_dir"].widget.attrs.update({"class": "textinput form-control"})
        self.fields["shiny_site_dir"].help_text = (
            "Provide a path to the Shiny app inside your " "Docker image if it is different from /srv/shiny-server/"
        )
        self.fields["shiny_site_dir"].bottom_help_text = mark_safe(
            "Use this field to specify subfolder if you did not place your app directly in <i>/srv/shiny-server/</i>. "
            'You can find more about it <a href="/docs/application-hosting/shiny/#wiki-toc-advanced-settings">'
            "in our documentation</a>."
        )

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
            Field("path", placeholder="/srv/shiny-server/..."),
            SRVCommonDivField("flavor"),
            SRVCommonDivField("access"),
            SRVCommonDivField(
                "note_on_linkonly_privacy",
                placeholder="Describe why you want to make the app accessible only via a link",
            ),
            SRVCommonDivField("source_code_url", placeholder="Provide a link to the public source code"),
            SRVCommonDivField("port", placeholder="3838"),
            # Container image field
            self._setup_container_image_helper(),
            Accordion(
                AccordionGroup(
                    "Advanced settings",
                    PrependedText(
                        "shiny_site_dir",
                        "/srv/shiny-server/",
                        template="apps/partials/srv_prepend_append_input_group.html",
                    ),
                    active=False,
                ),
            ),
            css_class="card-body",
        )

        self.helper.layout = Layout(body, self.footer)

    def clean_shiny_site_dir(self):
        cleaned_data = super().clean()
        shiny_site_dir = cleaned_data.get("shiny_site_dir", None)
        if shiny_site_dir and shiny_site_dir.startswith("/"):
            self.add_error("shiny_site_dir", "Path must not start with a forward slash.")
        # Check that the path is ascii
        if shiny_site_dir and not shiny_site_dir.isascii():
            self.add_error("shiny_site_dir", "Path must be ASCII.")

        return shiny_site_dir

    def clean_path(self):
        cleaned_data = super().clean()

        path = cleaned_data.get("path", None)
        volume = cleaned_data.get("volume", None)

        if volume and not path:
            self.add_error("path", "Path is required when volume is selected.")

        if path:
            # If new path matches current path, it is valid.
            if self.instance and getattr(self.instance, "path", None) == path:
                return path
            # Verify that path starts with "/home"
            path = path.strip().rstrip("/").lower().replace(" ", "")
            if not path.startswith("/home"):
                self.add_error("path", 'Path must start with "/home"')

        return path

    class Meta:
        model = ShinyInstance
        fields = [
            "name",
            "description",
            "volume",
            "path",
            "flavor",
            "access",
            "note_on_linkonly_privacy",
            "source_code_url",
            "port",
            "image",
            "tags",
            "shiny_site_dir",
        ]
        labels = {
            "tags": "Keywords",
            "note_on_linkonly_privacy": "Reason for choosing the link only option",
            "shiny_site_dir": "Custom subpath for Shiny app after /srv/shiny-server/",
        }
