from typing import NamedTuple, Type

from apps.forms import BaseForm
from apps.models import AbstractAppInstance


class ModelFormTuple(NamedTuple):
    Model: Type[AbstractAppInstance]
    Form: Type[BaseForm]
