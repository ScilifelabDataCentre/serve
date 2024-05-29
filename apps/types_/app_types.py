from typing import NamedTuple, Type, Union

from apps.forms import BaseForm
from apps.models import BaseAppInstance


class ModelFormTuple(NamedTuple):
    Model: Type[BaseAppInstance]
    Form: Type[BaseForm]


NoneTuple = tuple[None, None]

OptionalModelFormTuple = Union[ModelFormTuple, NoneTuple]
