from apps.forms import (
    CustomAppForm,
    DashForm,
    FilemanagerForm,
    JupyterForm,
    NetpolicyForm,
    RStudioForm,
    ShinyForm,
    TissuumapsForm,
    VolumeForm,
    VSCodeForm,
)
from apps.models import (
    CustomAppInstance,
    DashInstance,
    FilemanagerInstance,
    JupyterInstance,
    NetpolicyInstance,
    RStudioInstance,
    ShinyInstance,
    TissuumapsInstance,
    VolumeInstance,
    VSCodeInstance,
)
from apps.types_.app_types import ModelFormTuple

SLUG_MODEL_FORM_MAP = {
    "jupyter-lab": ModelFormTuple(JupyterInstance, JupyterForm),
    "rstudio": ModelFormTuple(RStudioInstance, RStudioForm),
    "vscode": ModelFormTuple(VSCodeInstance, VSCodeForm),
    "volumeK8s": ModelFormTuple(VolumeInstance, VolumeForm),
    "netpolicy": ModelFormTuple(NetpolicyInstance, NetpolicyForm),
    "dashapp": ModelFormTuple(DashInstance, DashForm),
    "customapp": ModelFormTuple(CustomAppInstance, CustomAppForm),
    "shinyapp": ModelFormTuple(ShinyInstance, ShinyForm),
    "shinyproxyapp": ModelFormTuple(ShinyInstance, ShinyForm),
    "tissuumaps": ModelFormTuple(TissuumapsInstance, TissuumapsForm),
    "filemanager": ModelFormTuple(FilemanagerInstance, FilemanagerForm),
}
