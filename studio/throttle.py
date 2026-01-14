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

    rate = getattr(settings, "AUTH_RATE_LIMIT_VALUE", None)

    def get_ident(self, request: HttpRequest) -> Any:
        """
        Extract the real client IP from proxy headers
        """

        # Try X-Forwarded-For first (standard proxy header)
        xff = request.META.get("HTTP_X_FORWARDED_FOR")
        if xff:
            ip = xff.split(",")[0].strip()
            return ip

        # Try X-Real-IP (nginx specific)
        real_ip = request.META.get("HTTP_X_REAL_IP")
        if real_ip:
            return real_ip

        # Fallback to Django's standard remote address
        fallback = request.META.get("REMOTE_ADDR", "unknown")
        return fallback

    def allow_request(self, request: HttpRequest, view: APIView) -> Any:
        # If no rate is configured, throttling is disabled entirely
        if not self.rate:
            return True

        whitelist_range = getattr(settings, "AUTH_RATE_LIMIT_WHITELIST", None)

        # If whitelist is configured, check if IP is whitelisted
        if whitelist_range:
            incoming_ip = self.get_ident(request)
            for network in whitelist_range if isinstance(whitelist_range, list) else [whitelist_range]:
                try:
                    if ip_address(incoming_ip) in ip_network(network):
                        return True  # Whitelisted, allow through
                except ValueError:
                    continue  # Skip invalid network/IP formats

        return super().allow_request(request, view)
