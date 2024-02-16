from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required

from django.http import HttpResponseRedirect
from django.urls import path
# This import are temporary and should be removed once the new urls are used everywhere by users.
from django.views import View


from . import views
from .views import (
    GrantAccessToProjectView,
    ProjectStatusView,
    RevokeAccessToProjectView,
    UpdatePatternView,
)

app_name = "projects"
User = get_user_model()
basicpatterns = [
    path("projects/", views.IndexView.as_view(), name="index"),
    path(
        "projects/create/",
        login_required(views.CreateProjectView.as_view()),
        name="create",
    ),
    path("projects/templates/", views.project_templates, name="project_templates"),
    path("<project_slug>/", views.DetailsView.as_view(), name="details"),
    path(
        "<project_slug>/environments/create/",
        views.create_environment,
        name="create_environment",
    ),
    path("<project_slug>/settings/", views.settings, name="settings"),
    path("<project_slug>/delete/", views.delete, name="delete"),
    path(
        "<project_slug>/setS3storage/",
        views.set_s3storage,
        name="set_s3storage",
    ),
    path("<project_slug>/setmlflow/", views.set_mlflow, name="set_mlflow"),
    path(
        "<project_slug>/details/change/",
        views.change_description,
        name="change_description",
    ),
    path(
        "<project_slug>/pattern/update/",
        UpdatePatternView.as_view(),
        name="update_pattern",
    ),
    path(
        "<project_slug>/project/publish/",
        views.publish_project,
        name="publish_project",
    ),
    path(
        "<project_slug>/project/access/grant/",
        GrantAccessToProjectView.as_view(),
        name="grant_access",
    ),
    path(
        "<project_slug>/project/access/revoke/",
        RevokeAccessToProjectView.as_view(),
        name="revoke_access",
    ),
    path(
        "<project_slug>/project/status/",
        ProjectStatusView.as_view(),
        name="get_status",
    ),
]

extrapatterns = [
    path(
        "<project_slug>/environments/create/",
        views.create_environment,
        name="create_environment",
    ),
    path(
        "<project_slug>/createflavor/",
        views.create_flavor,
        name="create_flavor",
    ),
    path(
        "<project_slug>/deleteflavor/",
        views.delete_flavor,
        name="delete_flavor",
    ),
    path(
        "<project_slug>/createenvironment/",
        views.create_environment,
        name="create_environment",
    ),
    path(
        "<project_slug>/deleteenvironment/",
        views.delete_environment,
        name="delete_environment",
    ),
]

if settings.ENABLE_PROJECT_EXTRA_SETTINGS or User.is_superuser:
    urlpatterns = basicpatterns + extrapatterns
else:
    urlpatterns = basicpatterns


# Everying below this comment should be removed once the new urls are used everywhere by users.
# This was written on 2024-02-16


class CustomRedirectView(View):
    def get_redirect_url(self, *args, **kwargs):
        # Extract the project_slug from kwargs
        # Construct the new URL
        return f"{self.request.get_full_path()}".replace(f"/{self.request.user}", "")

    def get(self, request, *args, **kwargs):
        url = self.get_redirect_url(*args, **kwargs)
        return HttpResponseRedirect(url)


urlpatterns += [
    path("<user>/<project_slug>/", CustomRedirectView.as_view(), name="redirect_details"),
    path("<user>/<project_slug>/project/status/", CustomRedirectView.as_view(), name="redirect_status"),
    path("<user>/<project_slug>/settings/", CustomRedirectView.as_view(), name="settings"),
    path("<user>/<project_slug>/delete/", CustomRedirectView.as_view(), name="delete"),
    path(
        "<user>/<project_slug>/details/change/",
        CustomRedirectView.as_view(),
        name="redirect_change_description",
    ),
    path(
        "<user>/<project_slug>/pattern/update/",
        CustomRedirectView.as_view(),
        name="redirect_update_pattern",
    ),
    path(
        "<user>/<project_slug>/project/publish/",
        CustomRedirectView.as_view(),
        name="redirect_publish_project",
    ),
    path(
        "<user>/<project_slug>/project/access/grant/",
        CustomRedirectView.as_view(),
        name="redirect_grant_access",
    ),
    path(
        "<user>/<project_slug>/project/access/revoke/",
        CustomRedirectView.as_view(),
        name="redirect_revoke_access",
    ),
    path(
        "<user>/<project_slug>/project/status/",
        CustomRedirectView.as_view(),
        name="redirect_get_status",
    ),
]
# End of temporary code
