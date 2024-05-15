from django.urls import path

from projects.views import IndexView as IndexView

from . import views

app_name = "portal"

urlpatterns = [
    path("home/", views.HomeView.as_view(), name="home"),
    path("about/", views.about, name="about"),
    path("teaching/", views.teaching, name="teaching"),
    path("privacy/", views.privacy, name="privacy"),
    path("apps/", views.public_apps, name="apps"),
    path("news/", views.news, name="news"),
    path("", views.HomeViewDynamic.as_view(), name="home-dynamic"),
]
