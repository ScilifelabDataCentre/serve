from django.urls import path
from django.views.generic import RedirectView

from . import views

app_name = "apps"

urlpatterns = [
    path("status", views.GetStatusView.as_view(), name="get_status"),
    path("logs", views.GetLogs.as_view(), name="get_logs"),
    path("logs/<app_slug>/<app_id>", views.GetLogs.as_view(), name="logs"),
    path("progress/<app_slug>/<app_id>", views.DeploymentProgressView.as_view(), name="deployment_progress"),
    path("details/<app_slug>/<app_id>", views.AppDetailsView.as_view(), name="details"),
    path("create/<app_slug>", views.CreateApp.as_view(), name="create"),
    path("settings/<app_slug>/<app_id>", views.CreateApp.as_view(), name="appsettings"),
    path("delete/<app_slug>/<app_id>", views.delete, name="delete"),
    path("secrets/<app_slug>/<app_id>", views.SecretsView.as_view(), name="secrets"),
    # Redirect old format to new format
    path(
        "metadata/<app_slug>/<app_id>",
        RedirectView.as_view(url="/records/%(app_id)s", permanent=True),
        name="redirect-old-app-metadata-url",
    ),
    # Background task URLs
    path("tasks/<app_slug>/<app_id>", views.BackgroundTasksView.as_view(), name="background_tasks"),
    path("tasks/<app_slug>/<app_id>/status", views.BackgroundTaskStatusAPI.as_view(), name="background_tasks_status"),
    path(
        "tasks/<app_slug>/<app_id>/<int:task_id>/retry",
        views.RetryBackgroundTaskView.as_view(),
        name="retry_background_task",
    ),
    # Admin background tasks view
    path("admin/background-tasks", views.AdminBackgroundTasksView.as_view(), name="admin_background_tasks"),
]
