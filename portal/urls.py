from django.conf import settings
from django.urls import path
from django.views.generic.base import TemplateView

from projects.views import IndexView as IndexView

from . import views

app_name = "portal"

urlpatterns = [
    path("home/", views.HomeView.as_view(), name="home-explicit"),
    path("about/", views.about, name="about"),
    path("about/roadmap/", views.roadmap, name="roadmap"),
    path("about/cite/", views.cite, name="cite"),
    path("contact/", views.contact, name="contact"),
    path("teaching/", views.teaching, name="teaching"),
    path("privacy/", views.privacy, name="privacy"),
    path("apps/", views.public_apps, name="apps"),
    path("news/", views.get_news, name="news"),
    path("events/", views.get_events, name="events"),
    path("collections/", views.get_collections_index, name="collections_index"),
    path("collections/<slug:slug>/", views.get_collection, name="collection"),
    path("", views.HomeView.as_view(), name="home"),
    path(
        "robots.txt",
        TemplateView.as_view(
            template_name="portal/robots.txt", content_type="text/plain", extra_context={"debug": settings.DEBUG}
        ),
    ),
]
