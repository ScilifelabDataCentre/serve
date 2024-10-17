from apps.forms import CustomAppForm
from apps.models import GradioInstance

__all__ = ["StreamlitForm"]

from apps.models.app_types.custom.streamlit import StreamlitInstance


class StreamlitForm(CustomAppForm):
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
        ]
        labels = {
            "note_on_linkonly_privacy": "Reason for choosing the link only option",
            "tags": "Keywords",
        }
