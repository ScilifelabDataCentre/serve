"""
Error handlers that render without touching the database.

Rendering with ``request=None`` skips context processors, so no DB connection is
opened on the ASGI error path.
"""


from django.http import HttpRequest, HttpResponse
from django.template import loader


def _render_static(template_name: str, status: int) -> HttpResponse:
    # request=None => no context processors => no DB access.
    template = loader.get_template(template_name)
    return HttpResponse(template.render({}), status=status)


def handler403(request: HttpRequest, exception: Exception | None = None) -> HttpResponse:
    return _render_static("403.html", 403)


def handler404(request: HttpRequest, exception: Exception | None = None) -> HttpResponse:
    return _render_static("404.html", 404)


def handler500(request: HttpRequest) -> HttpResponse:
    return _render_static("500.html", 500)
