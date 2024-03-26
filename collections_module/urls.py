from django.urls import path

from . import views

app_name = "collections_module"

urlpatterns = [
    path("collections/<slug:slug>/", views.collection, name="collection"),
]
