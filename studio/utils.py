import logging
from ipaddress import ip_address, ip_network
from typing import Any, List

import structlog
from django.conf import settings
from django.http import HttpRequest
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView


def get_logger(name: str) -> Any:
    """
    Get different loggers depending on the value of DEBUG.
    When DEBUG = True, then we return the standard logger,
    otherwise, the structlog.
    """
    if settings.DEVELOP_LOGS_ENABLED:
        return logging.getLogger(name)
    else:
        return structlog.getLogger(name)


def add_loggers(logging: dict[str, Any], installed_apps: List[str]) -> dict[str, Any]:
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


class WhitelistThrottleFilter(UserRateThrottle):
    """
    Custom throttle filter that whitelists certain IP ranges
    """

    rate = "1/minute"

    def allow_request(self, request: HttpRequest, view: APIView) -> Any:
        incomming_ip = self.get_ident(request)
        whitelist_range = getattr(settings, "RATE_LIMIT_WHITELIST", [])
        for network in whitelist_range:
            if ip_address(incomming_ip) in ip_network(network):
                return True
        return super().allow_request(request, view)
