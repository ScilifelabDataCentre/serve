"""studio URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/3.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.urls import include, path, re_path

from . import views

urlpatterns = (
    [
        path("admin/", admin.site.urls),
        path("", include("common.urls", namespace="common")),
        path("", include("models.urls", namespace="models")),
        path("", include("portal.urls", namespace="portal")),
        path("", include("news.urls", namespace="news")),
        path("", include("projects.urls", namespace="projects")),
        path("accounts/", include("django.contrib.auth.urls")),
        path("auth/", views.AuthView.as_view()),
        path(
            "<user>/<project>/monitor/",
            include("monitor.urls", namespace="monitor"),
        ),
        path("<user>/<project>/apps/", include("apps.urls", namespace="apps")),
        # API paths using NamespaceVersioning
        path("openapi/beta/", include("api.openapi.urls", namespace="beta")),
        path("openapi/v1/", include("api.openapi.urls", namespace="v1")),
        path("openapi/", include("api.openapi.urls")),
        path("api/", include("api.urls", namespace="api")),
        # for django-wiki
        path("docs/notifications/", include("django_nyt.urls")),
        path("docs/", include("wiki.urls")),
    ]
    + staticfiles_urlpatterns()
    + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
)
