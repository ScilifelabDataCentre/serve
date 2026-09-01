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
basicpatterns = [
    path("", views.IndexView.as_view(), name="index"),
    path(
        "create/",
        login_required(views.CreateProjectView.as_view()),
        name="create",
    ),
    path("templates/", views.project_templates, name="project_templates"),
    path("<project_slug>/", views.DetailsView.as_view(), name="details"),
    path(
        "<project_slug>/environments/create/",
        views.create_environment,
        name="create_environment",
    ),
    path("<project_slug>/settings/", views.settings, name="settings"),
    path("<project_slug>/delete/", views.delete, name="delete"),
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
    path(
        "<project_slug>/update_storage_settings/",
        views.update_storage_settings,
        name="update_storage_settings",
    ),
    path(
        "<project_slug>/volume/<int:volume_id>/increase/",
        views.increase_volume_size,
        name="increase_volume_size",
    ),
    path(
        "<project_slug>/volume/<int:volume_id>/resize/",
        views.update_volume_size,
        name="update_volume_size",
    ),
    path(
        "<project_slug>/request_storage/<int:volume_id>/",
        views.request_storage,
        name="request_storage",
    ),
]

urlpatterns = basicpatterns + extrapatterns
