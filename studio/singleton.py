from typing import Any, Dict, Type


class Singleton(type):
    """
    Implements the singleton pattern.
    Usage: ClassName(metaclass=Singleton)
    """

    _instances: Dict[Type[type], object] = {}

    def __call__(cls: Any, *args: Any, **kwargs: Any) -> Any:
        if cls not in cls._instances:
            cls._instances[cls] = super(Singleton, cls).__call__(*args, **kwargs)
        return cls._instances[cls]
