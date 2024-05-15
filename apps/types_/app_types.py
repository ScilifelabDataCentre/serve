from typing import NamedTuple, Type

from apps.forms import BaseForm
from apps.models import BaseAppInstance


class ModelFormTuple(NamedTuple):
    Model: Type[BaseAppInstance]
    Form: Type[BaseForm]
