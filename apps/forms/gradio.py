from apps.forms import CustomAppForm
from apps.models import GradioInstance

__all__ = ["GradioForm"]


class GradioForm(CustomAppForm):
    class Meta:
        model = GradioInstance
        fields = ["name", "description", "flavor", "access", "source_code_url", "port", "image", "tags"]
