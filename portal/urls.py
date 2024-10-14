from django.urls import path

from projects.views import IndexView as IndexView

from . import views

app_name = "portal"

urlpatterns = [
    path("home/", views.HomeView.as_view(), name="home-explicit"),
    path("about/", views.about, name="about"),
    path("teaching/", views.teaching, name="teaching"),
    path("privacy/", views.privacy, name="privacy"),
    path("apps/", views.public_apps, name="apps"),
    path("news/", views.get_news, name="news"),
    path("events/", views.get_events, name="events"),
    path("collections/", views.get_collections_index, name="collections_index"),
    path("collections/<slug:slug>/", views.get_collection, name="collection"),
    path("", views.HomeView.as_view(), name="home"),
]
