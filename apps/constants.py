from apps.forms import JupyterForm, VolumeForm, DashForm, CustomAppForm, ShinyForm, NetpolicyForm
from apps.models import JupyterInstance, VolumeInstance, DashInstance, CustomAppInstance, ShinyInstance, NetpolicyInstance 
from apps.types_.app_types import ModelFormTuple

SLUG_MODEL_FORM_MAP = {
    'jupyter-lab': ModelFormTuple(JupyterInstance, JupyterForm),
    'volumeK8s': ModelFormTuple(VolumeInstance, VolumeForm),
    'netpolicy': ModelFormTuple(NetpolicyInstance, NetpolicyForm),
    "dashapp": ModelFormTuple(DashInstance, DashForm),
    "customapp": ModelFormTuple(CustomAppInstance, CustomAppForm),
    "shinyproxyapp": ModelFormTuple(ShinyInstance, ShinyForm),
}

