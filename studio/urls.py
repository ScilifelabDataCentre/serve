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
from django.urls import include, path

from . import views

urlpatterns = (
    [
        path(settings.DJANGO_ADMIN_URL_PATH.rstrip("/") + "/", admin.site.urls, name="django-admin"),
        path("accounts/", include("django.contrib.auth.urls")),
        path("user/profile/", views.profile, name="user-profile"),
        path("user/delete-account/", views.delete_account, name="delete_account"),
        path(
            "user/delete-account-action/<int:user_id>",
            views.delete_account_post_handler,
            name="delete_account_post_handler",
        ),
        path("user/account-deleted/<int:user_id>", views.account_deleted, name="account_deleted"),
        path("auth/", views.AuthView.as_view()),
        # API paths using NamespaceVersioning
        path("openapi/beta/", include("api.openapi.urls", namespace="beta")),
        path("openapi/v1/", include("api.openapi.urls", namespace="v1")),
        path("openapi/", include("api.openapi.urls")),
        path("api/", include("api.urls", namespace="api")),
        path("api/v1/", include("api.urls", namespace="api-v1")),
        # for django-wiki
        path("docs/notifications/", include("django_nyt.urls")),
        path("docs/", include("wiki.urls")),
        path("projects/", include("projects.urls", namespace="projects")),
        path("", include("common.urls", namespace="common")),
        path("", include("models.urls", namespace="models")),
        path("", include("portal.urls", namespace="portal")),
        path("projects/<project>/apps/", include("apps.urls", namespace="apps")),
    ]
    + staticfiles_urlpatterns()
    + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
)
