from crispy_forms.bootstrap import Accordion, AccordionGroup, PrependedText
from crispy_forms.layout import HTML, Div, Field, Layout, MultiField
from django import forms
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils.safestring import mark_safe

from apps.forms.base import AppBaseForm
from apps.forms.field.common import SRVCommonDivField
from apps.models import CustomAppInstance, VolumeInstance
from projects.models import Flavor

__all__ = ["CustomAppForm"]


class CustomAppForm(AppBaseForm):
    flavor = forms.ModelChoiceField(queryset=Flavor.objects.none(), required=False, empty_label=None)
    port = forms.IntegerField(min_value=3000, max_value=9999, required=True)
    image = forms.CharField(max_length=255, required=True)
    path = forms.CharField(max_length=255, required=False)
    default_url_subpath = forms.CharField(max_length=255, required=False, label="Custom URL subpath")

    def _setup_form_fields(self):
        # Handle Volume field
        super()._setup_form_fields()
        self.fields["volume"].initial = None

        self.fields["default_url_subpath"].widget.attrs.update({"class": "textinput form-control"})
        self.fields["default_url_subpath"].help_text = "Specify a non-default start URL if your app requires that."
        apps_url = reverse("portal:apps")
        self.fields["default_url_subpath"].bottom_help_text = mark_safe(
            (
                f"<span class='fw-bold'>Note:</span> This changes the URL connected to the Open button for an app"
                f" on the Serve <a href='{apps_url}'>Apps & Models</a> page."
            )
        )

    def _setup_form_helper(self):
        super()._setup_form_helper()

        body = Div(
            SRVCommonDivField("name", placeholder="Name your app"),
            SRVCommonDivField("description", rows=3, placeholder="Provide a detailed description of your app"),
            SRVCommonDivField("tags"),
            SRVCommonDivField("subdomain", placeholder="Enter a subdomain or leave blank for a random one."),
            Field("volume"),
            SRVCommonDivField("path", placeholder="/home/..."),
            SRVCommonDivField("flavor"),
            SRVCommonDivField("access"),
            SRVCommonDivField("source_code_url", placeholder="Provide a link to the public source code"),
            SRVCommonDivField(
                "note_on_linkonly_privacy",
                rows=1,
                placeholder="Describe why you want to make the app accessible only via a link",
            ),
            SRVCommonDivField("port", placeholder="8000"),
            SRVCommonDivField("image"),
            Accordion(
                AccordionGroup(
                    "Advanced settings",
                    PrependedText(
                        "default_url_subpath",
                        mark_safe("<span id='id_custom_default_url_prepend'>Subdomain/</span>"),
                        template="apps/partials/srv_prepend_append_input_group.html",
                    ),
                    active=False,
                ),
            ),
            css_class="card-body",
        )
        self.helper.layout = Layout(body, self.footer)

    def clean_path(self):
        cleaned_data = super().clean()

        path = cleaned_data.get("path", None)
        volume = cleaned_data.get("volume", None)

        if volume and not path:
            self.add_error("path", "Path is required when volume is selected.")

        if path and not volume:
            self.add_error("path", "Warning, you have provided a path, but not selected a volume.")

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
        model = CustomAppInstance
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
            "default_url_subpath",
        ]
        labels = {
            "note_on_linkonly_privacy": "Reason for choosing the link only option",
            "tags": "Keywords",
        }
