from typing import Any

from django.conf import settings
from django.http import JsonResponse
from django.views import View

from common.auth_cache import (
    build_cache_key,
    get_cached_value,
    invalidate_cache_key,
    is_cache_miss,
    set_cached_value,
)
from projects.models import Project


def _project_permission_cache_timeout() -> int:
    return getattr(settings, "PROJECT_PERMISSION_CACHE_TIMEOUT", 5)


def build_project_permission_cache_key(user_id: int, project_slug: str, permission: str) -> str:
    return build_cache_key("project_permission", user_id, project_slug, permission)


def invalidate_project_permission(user_id: int, project_slug: str, permission: str) -> None:
    invalidate_cache_key(build_project_permission_cache_key(user_id, project_slug, permission))


def get_project_permission(user: Any, project_slug: str, permission: str) -> bool | None:
    """Cached permission check for a project.

    Returns ``True``/``False`` for the decision, or ``None``
    when the project does not exist.
    """
    user_id = getattr(user, "pk", None)
    if user_id is None:
        return False
    cache_key = build_project_permission_cache_key(user_id, project_slug, permission)
    cache_timeout = _project_permission_cache_timeout()

    if cache_timeout > 0:
        cached_value = get_cached_value(cache_key)
        if not is_cache_miss(cached_value) and cached_value in (True, False):
            return bool(cached_value)

    try:
        project = Project.objects.get(slug=project_slug)
    except Project.DoesNotExist:
        return None

    allowed = bool(user.has_perm(permission, project))
    set_cached_value(cache_key, allowed, cache_timeout)
    return allowed


class CachedProjectPermissionRequiredMixin(View):
    project_url_kwarg = "project_slug"
    permission_name = "can_view_project"

    def dispatch(self, request: Any, *args: Any, **kwargs: Any) -> Any:
        if not request.user.is_authenticated:
            return JsonResponse({"error": "Authentication required"}, status=403)

        project_slug = kwargs.get(self.project_url_kwarg)
        if project_slug is None:
            return JsonResponse({"error": "Project not found"}, status=404)

        allowed = get_project_permission(request.user, project_slug, self.permission_name)
        if allowed is None:
            return JsonResponse({"error": "Project not found"}, status=404)
        if not allowed:
            return JsonResponse({"error": "Permission denied"}, status=403)

        return super().dispatch(request, *args, **kwargs)
