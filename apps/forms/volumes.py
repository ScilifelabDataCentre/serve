from crispy_forms.layout import Div, Field, Layout
from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError

from apps.forms.base import BaseForm
from apps.models import VolumeInstance

__all__ = ["VolumeForm", "VolumeResizeForm"]


class VolumeForm(BaseForm):
    def _setup_form_helper(self):
        super()._setup_form_helper()
        body = Div(
            Field("name", required=True),
            Field("size"),
            Field("subdomain", placeholder="Enter a subdomain or leave blank for a random one"),
            css_class="card-body",
        )

        self.helper.layout = Layout(body, self.footer)

    # create meta class
    class Meta:
        model = VolumeInstance
        fields = ["name", "size"]


class VolumeResizeForm(forms.Form):
    """Validates a volume size change. Cannot shrink a PVC, only increases size."""

    size = forms.IntegerField(label="Size in GB")

    def __init__(self, *args, current_size: int, **kwargs):
        super().__init__(*args, **kwargs)
        self.current_size = current_size
        self.max_size = settings.PRIVILEGED_USER_MAX_VOLUME_SIZE_GB

    def clean_size(self) -> int:
        size = self.cleaned_data["size"]

        if size <= self.current_size:
            raise ValidationError(
                f"The new size must be larger than the current size of {self.current_size} GB. "
                "A volume can be expanded but never shrunk."
            )

        if size > self.max_size:
            raise ValidationError(
                f"The size cannot exceed {self.max_size} GB. Contact serve@scilifelab.se if you need more."
            )

        VolumeInstance._meta.get_field("size").run_validators(size)

        return size
