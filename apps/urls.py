from django.urls import path

from apps.views import AppSettingsView, CreateServeView, CreateViewz

from . import views

app_name = "apps"

urlpatterns = [
    path("apps/", views.index, name="index"),
    path("status", views.GetStatusView.as_view(), name="get_status"),
    path("logs", views.GetLogsView.as_view(), name="get_logs"),
    path("<category>", views.FilteredView.as_view(), name="filtered"),
    path("create/<app_slug>", views.CreateJupyterApp.as_view(), name="create"),
    path("create/<app_slug>/create_releasename", views.create_releasename, name="create_releasename"),
    path("serve/<app_slug>/<version>", CreateServeView.as_view(), name="serve"),
    path("logs/<ai_id>", views.GetLogsView.as_view(), name="logs"),
    path("settings/<ai_id>", AppSettingsView.as_view(), name="appsettings"),
    path("settings/<ai_id>/add_tag", views.add_tag, name="add_tag"),
    path("settings/<ai_id>/remove_tag", views.remove_tag, name="remove_tag"),
    path("delete/<category>/<ai_id>", views.delete, name="delete"),
    path("publish/<category>/<ai_id>", views.publish, name="publish"),
    path("unpublish/<category>/<ai_id>", views.unpublish, name="unpublish"),
]
