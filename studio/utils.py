import logging

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
