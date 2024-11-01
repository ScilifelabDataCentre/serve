from crispy_forms.bootstrap import (
    Accordion,
    AccordionGroup,
    AppendedText,
    PrependedAppendedText,
    PrependedText,
)
from crispy_forms.layout import HTML, Div, Field, Layout, MultiField
from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
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

    custom_default_url = forms.CharField(max_length=255, required=False, label="Custom default start URL")

    def _setup_form_fields(self):
        # Handle Volume field
        super()._setup_form_fields()
        self.fields["volume"].initial = None

        self.fields["custom_default_url"].widget.attrs.update({"class": "textinput form-control"})
        self.fields["custom_default_url"].help_text = "Specify a non-default start URL if your app requires that."
        self.fields["custom_default_url"].bottom_help_text = mark_safe(
            (
                "We will display this URL for your app in our app catalogue."
                " Keep in mind that when your app does not have anything on the root URL"
                " (<span id='id_custom_default_url_form_help_text'></span>) if a user manually"
                " navigates to the root URL they will see an empty page there."
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
                        "custom_default_url",
                        "Subdomain/",
                        template="apps/partials/srv_prepend_input_group_custom_app.html",
                    ),
                    active=False,
                ),
            ),
            css_class="card-body",
        )
        self.helper.layout = Layout(body, self.footer)

    def clean_custom_default_url(self):
        cleaned_data = super().clean()
        custom_default_url = cleaned_data.get("custom_default_url", None)
        error_message = (
            "Your custom default URL is not valid, please correct it. "
            "It must be 1-53 characters long."
            " It can contain only letters, digits, hyphens"
            " ( - ), forward slashes ( / ), and underscores ( _ )."
            " It cannot start or end with a hyphen ( - ) and "
            "cannot start with a forward slash ( / )."
            " It cannot contain consecutive forward slashes ( // )."
        )
        regex_validator = RegexValidator(
            regex=r"^(?!-)(?!/)(?!.*//)[A-Za-z0-9-/_]{1,53}(?<!-)$|^$",
            message=error_message,
        )
        try:
            regex_validator(custom_default_url)
            return custom_default_url
        except ValidationError:
            self.add_error("custom_default_url", error_message)

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
            "custom_default_url",
        ]
        labels = {
            "note_on_linkonly_privacy": "Reason for choosing the link only option",
            "tags": "Keywords",
        }
