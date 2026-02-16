from django.urls import path

from .views import keyword_search

urlpatterns = [
    path("keyword_search/", keyword_search, name="keyword_search"),
]
