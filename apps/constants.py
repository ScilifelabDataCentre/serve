from apps.forms import JupyterForm, RStudioForm, VSCodeForm, VolumeForm, DashForm, CustomAppForm, ShinyForm, NetpolicyForm, TissuumapsForm
from apps.models import JupyterInstance, RStudioInstance, VSCodeInstance, VolumeInstance, DashInstance, CustomAppInstance, ShinyInstance, NetpolicyInstance, TissuumapsInstance 
from apps.types_.app_types import ModelFormTuple

SLUG_MODEL_FORM_MAP = {
    'jupyter-lab': ModelFormTuple(JupyterInstance, JupyterForm),
    'rstudio': ModelFormTuple(RStudioInstance, RStudioForm),
    'vscode': ModelFormTuple(VSCodeInstance, VSCodeForm),
    'volumeK8s': ModelFormTuple(VolumeInstance, VolumeForm),
    'netpolicy': ModelFormTuple(NetpolicyInstance, NetpolicyForm),
    "dashapp": ModelFormTuple(DashInstance, DashForm),
    "customapp": ModelFormTuple(CustomAppInstance, CustomAppForm),
    "shinyproxyapp": ModelFormTuple(ShinyInstance, ShinyForm),
    "tissuumaps": ModelFormTuple(TissuumapsInstance, TissuumapsForm),
}

