from apps.forms import JupyterForm, VolumeForm
from apps.models import JupyterInstance, VolumeInstance
from apps.types_.app_types import ModelFormTuple

SLUG_MODEL_FORM_MAP = {
    'jupyter-lab': ModelFormTuple(JupyterInstance, JupyterForm),
    'volumeK8s': ModelFormTuple(VolumeInstance, VolumeForm),
}

