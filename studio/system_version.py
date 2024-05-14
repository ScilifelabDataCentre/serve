""" A singleton implementation of a class exposing version information about the currently deployed application.
    The singleton pattern is appropriate here because the SystemVersion class is a constant singleton.
    This singleton class would be appropriate to add to a cache and kept in memory.
"""

import pathlib
import tomllib
from typing import Any

from .singleton import Singleton
from .utils import get_logger

logger = get_logger(__name__)


class SystemVersion(metaclass=Singleton):
    """SystemVersion contains version information about the deployed django application."""

    __build_date = None
    __gitref = None
    __imagetag = None

    # debug info
    __pyproject_is_parsed = False
    __init_counter = 0

    def __init__(self, *args: Any, **kwargs: Any):
        self.__init_counter += 1
        self.__set_values_from_toml()

    def get_version_text(self) -> str:
        """Gets a formatted text of the deployed system in format <date> (v0.0.0)."""
        if self.__build_date == "" or self.__gitref == "":
            return "unset"
        return f"{self.__build_date} ({self.__gitref})"

    def get_build_date(self) -> str | None:
        """Gets the deployed system build date."""
        return self.__build_date

    def get_gitref(self) -> str | None:
        """Gets the deployed system git reference, e.g. develop or v1.0.0."""
        return self.__gitref

    def get_imagetag(self) -> str | None:
        """Gets the deployed image tag as e.g. main-20230912"""
        return self.__imagetag

    def get_debug_info(self) -> str:
        debug_info = f"toml has been parsed:{self.__pyproject_is_parsed}, init:{self.__init_counter}"
        return debug_info

    def get_init_counter(self) -> int:
        return self.__init_counter

    def get_pyproject_is_parsed(self) -> bool:
        return self.__pyproject_is_parsed

    def __set_values_from_toml(self) -> None:
        err_message = ""
        try:
            proj_path = pathlib.Path(__file__).parents[1] / "pyproject.toml"
            with open(proj_path, "rb") as f:
                toml_dict = tomllib.load(f)
                self.__build_date = toml_dict["tool"].get("serve").get("build-date")
                self.__gitref = toml_dict["tool"].get("serve").get("gitref")
                self.__imagetag = toml_dict["tool"].get("serve").get("imagetag")
            self.__pyproject_is_parsed = True
            return
        except tomllib.TOMLDecodeError:
            logger.error("Unable to parse pyproject.toml file. The toml file is invalid.")
            err_message = "parsing error"
        except Exception as e:
            logger.error("Unable to parse pyproject.toml file. Caught general exception.")
            err_message = f"error {str(e)}"
        logger.error("Unable to parse pyproject.toml file. Using default values for system version attributes.")
        self.__build_date = err_message
        self.__gitref = err_message
        self.__imagetag = err_message
