from django.conf import settings
from rest_framework.request import Request

from common.auth_cache import (
    build_cache_key,
    get_cached_value,
    is_cache_miss,
    set_cached_value,
)


def is_auth_permission_cache_enabled() -> bool:
    return getattr(settings, "AUTH_PERMISSION_CACHE_ENABLED", False)


def build_auth_permission_cache_key(request: Request) -> str | None:
    user_id = getattr(request.user, "pk", None)
    if user_id is None:
        return None

    release = request.GET.get("release") or ""
    project = request.GET.get("project") or ""
    if not release and not project:
        return None

    return build_cache_key("auth_permission", user_id, release, project)


def get_cached_auth_permission(cache_key: str | None) -> bool | None:
    if not is_auth_permission_cache_enabled() or cache_key is None:
        return None

    cached_value = get_cached_value(cache_key)
    if is_cache_miss(cached_value):
        return None
    if cached_value in (True, False):
        return bool(cached_value)
    return None


def set_cached_auth_permission(cache_key: str | None, allowed: bool) -> None:
    if not is_auth_permission_cache_enabled() or cache_key is None:
        return

    timeout = getattr(settings, "AUTH_PERMISSION_CACHE_TIMEOUT", 30)
    if not allowed:
        timeout = getattr(settings, "AUTH_PERMISSION_CACHE_DENY_TIMEOUT", 5)
    set_cached_value(cache_key, allowed, timeout)
