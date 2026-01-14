from crispy_bootstrap5.bootstrap5 import BS5Accordion
from crispy_forms.bootstrap import Accordion, AccordionGroup, PrependedText
from crispy_forms.layout import Div, Field, Layout
from django import forms
from django.utils.safestring import mark_safe

from apps.forms.base import AppBaseForm
from apps.forms.field.common import SRVCommonDivField
from apps.forms.mixins import ContainerImageMixin, StorageMixin
from apps.models import StreamlitInstance
from projects.models import Flavor

__all__ = ["StreamlitForm"]


class StreamlitForm(StorageMixin, ContainerImageMixin, AppBaseForm):
    flavor = forms.ModelChoiceField(queryset=Flavor.objects.none(), required=False, empty_label=None)
    port = forms.IntegerField(min_value=3000, max_value=9999, required=True)
    path = forms.CharField(max_length=255, required=False)

    def _setup_form_fields(self):
        # Handle Volume field
        super()._setup_form_fields()
        self.fields["volume"].initial = None

        # Setup container image field from mixin
        self._setup_container_image_field()
        self._set_up_mount_path_field()

    def _setup_form_helper(self):
        super()._setup_form_helper()

        # Define AccordionGroups
        general = AccordionGroup(
            mark_safe("<h3>App metadata</h3>"),
            SRVCommonDivField("name", placeholder="Name your app", required=True),
            SRVCommonDivField("description", rows=3, placeholder="Provide a detailed description of your app"),
            SRVCommonDivField("tags"),
            SRVCommonDivField("access"),
            SRVCommonDivField("source_code_url", placeholder="Provide a link to the public source code"),
            SRVCommonDivField(
                "note_on_linkonly_privacy",
                rows=1,
                placeholder="Describe why you want to make the app accessible only via a link",
            ),
            active=True,
        )

        configuration = AccordionGroup(
            mark_safe("<h3>Configuration settings</h3>"),
            SRVCommonDivField("subdomain", placeholder="Enter a subdomain or leave blank for a random one."),
            self._set_up_mount_path_helper(),
            SRVCommonDivField("flavor"),
            SRVCommonDivField("port", placeholder="8000"),
            self._setup_container_image_helper(),
            active=True,
        )

        accordion = BS5Accordion(
            general,
            configuration,
            always_open=True,
            css_class="form-accordion",
        )
        accordion.always_open = True  # Force property for Bootstrap 5.3+

        body = Div(accordion, css_class="card-body")
        body.always_open = True
        self.helper.layout = Layout(body, self.footer)

    def clean(self):
        return self._clean()

    class Meta:
        model = StreamlitInstance
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
            "mount_path",
        ]
        labels = {
            "note_on_linkonly_privacy": "Reason for choosing the link only option",
            "tags": "Keywords",
        }
