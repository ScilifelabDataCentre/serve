import logging
from typing import List
import structlog
from django.conf import settings


def get_logger(name: str):
    """
    Get different loggers depending on the value of DEBUG.
    When DEBUG = True, then we return the standard logger,
    otherwise, the structlog.
    """
    if settings.DEBUG:
        return logging.getLogger(name)
    else:
        return structlog.getLogger(name)

def add_loggers(logging: dict, installed_apps: List[str]) -> dict:
    """
    Helper function to add loggers to each installed app
    """
    for apps in installed_apps:
        logging["loggers"][apps] = {
            "handlers": ["console" if settings.DEBUG else "json"],
            "level": "DEBUG" if settings.DEBUG else "INFO",
            "propagate": False,
        }

    return logging
