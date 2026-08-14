from typing import Any, Dict, Type


class Singleton(type):
    """
    Implements the singleton pattern.
    Usage: ClassName(metaclass=Singleton)
    """

    _instances: dict[type[type], object] = {}

    def __call__(cls: Any, *args: Any, **kwargs: Any) -> Any:
        if cls not in cls._instances:
            cls._instances[cls] = super().__call__(*args, **kwargs)
        return cls._instances[cls]
