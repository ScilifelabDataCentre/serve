from apps.forms import CustomAppForm
from apps.models import GradioInstance

__all__ = ["GradioForm"]


class GradioForm(CustomAppForm):
    class Meta:
        model = GradioInstance
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
