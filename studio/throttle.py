from ipaddress import ip_address, ip_network
from typing import Any

from django.conf import settings
from django.http import HttpRequest
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView


class WhitelistThrottleFilter(UserRateThrottle):
    """
    Custom throttle filter that whitelists certain IP ranges
    """

    rate = getattr(settings, "AUTH_RATE_LIMIT_VALUE", "10/minute")

    def allow_request(self, request: HttpRequest, view: APIView) -> Any:
        incoming_ip = self.get_ident(request)
        whitelist_range = getattr(settings, "AUTH_RATE_LIMIT_WHITELIST", [])
        for network in whitelist_range:
            if ip_address(incoming_ip) in ip_network(network):
                return True
        return super().allow_request(request, view)
