from django.urls import path
from projects.views import IndexView as IndexView
from . import views

app_name = "news"

urlpatterns = [
   path('news/', views.news, name='news'), 
]
