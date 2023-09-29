from typing import Dict


class Singleton(type):
    """
    Implements the singleton pattern.
    Usage: ClassName(metaclass=Singleton)
    """

    _instances: Dict[type, object] = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super(Singleton, cls).__call__(*args, **kwargs)
        return cls._instances[cls]
