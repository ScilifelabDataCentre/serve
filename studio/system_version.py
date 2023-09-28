""" A singleton implementation of a class exposing version information about the currently deployed application.
    The singleton pattern is appropriate here because the SystemVersion class is a constant singleton.
    This singleton class would be appropriate to add to a cache and kept in memory.
"""

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


class SystemVersion(metaclass=Singleton):
    """SystemVersion contains version information about the deployed django application."""

    __build_date = None
    __gitref = None
    __imagetag = None

    # debug info
    __pyproject_is_parsed = False
    __init_counter = 0

    def __init__(self, *args, **kwargs):
        self.__init_counter += 1
        self.__parse_toml()

    def get_version_text(self):
        """Gets a formatted text of the deployed system in format <date> (v0.0.0)."""
        return f"{self.__build_date} ({self.__gitref})"

    def get_build_date(self):
        """Gets the deployed system build date."""
        return self.__build_date

    def get_gitref(self):
        """Gets the deployed system git reference, e.g. develop or v1.0.0."""
        return self.__gitref

    def get_imagetag(self):
        """Gets the deployed image tag as e.g. main-20230912"""
        return self.__imagetag

    def get_debug_info(self):
        debug_info = f"toml has been parsed:{self.__pyproject_is_parsed}, init:{self.__init_counter}"
        return debug_info

    def get_init_counter(self):
        return self.__init_counter

    def get_pyproject_is_parsed(self):
        return self.__pyproject_is_parsed

    def __parse_toml(self):
        # TODO: parse toml file
        self.__build_date = "<date from toml>"
        self.__gitref = "<git ref from toml>"
        self.__imagetag = "<image tag from toml>"
        self.__pyproject_is_parsed = True
