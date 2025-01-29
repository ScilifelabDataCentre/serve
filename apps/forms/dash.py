from crispy_forms.bootstrap import Accordion, AccordionGroup, PrependedText
from crispy_forms.layout import HTML, Div, Field, Layout
from django import forms
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils.safestring import mark_safe

from apps.forms.base import AppBaseForm
from apps.forms.field.common import SRVCommonDivField
from apps.models import DashInstance
from projects.models import Flavor

__all__ = ["DashForm"]


class DashForm(AppBaseForm):
    flavor = forms.ModelChoiceField(queryset=Flavor.objects.none(), required=False, empty_label=None)
    port = forms.IntegerField(min_value=3000, max_value=9999, required=True)
    image = forms.CharField(max_length=255, required=True)
    default_url_subpath = forms.CharField(max_length=255, required=False, label="Custom URL subpath")

    def _setup_form_fields(self):
        # Handle Volume field
        super()._setup_form_fields()

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
            SRVCommonDivField("image", placeholder="e.g. docker.io/username/image-name:image-tag"),
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

    @property
    def changed_data(self):
        # Override the default changed_data to handle that volume not part of this app type.
        # TODO: Consider adding to all app forms that do not contain volume.
        changed_data = super().changed_data
        if "volume" in changed_data:
            changed_data.remove("volume")
        return changed_data

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
            "default_url_subpath",
        ]
        labels = {
            "tags": "Keywords",
            "note_on_linkonly_privacy": "Reason for choosing the link only option",
        }
