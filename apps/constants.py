from apps.forms import JupyterForm, VolumeForm, DashForm
from apps.models import JupyterInstance, VolumeInstance, DashInstance
from apps.types_.app_types import ModelFormTuple

SLUG_MODEL_FORM_MAP = {
    'jupyter-lab': ModelFormTuple(JupyterInstance, JupyterForm),
    'volumeK8s': ModelFormTuple(VolumeInstance, VolumeForm),
    "dashapp": ModelFormTuple(DashInstance, DashForm),
}

