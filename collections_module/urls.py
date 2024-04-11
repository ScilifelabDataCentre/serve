from django.urls import path

from . import views

app_name = "collections_module"

urlpatterns = [
    path("collections/", views.index, name="index"),
    path("collections/<slug:slug>/", views.collection, name="collection"),
]
