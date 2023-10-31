import rest_framework.routers as drfrouters
from django.conf.urls import include
from django.urls import path, re_path
from rest_framework_nested import routers

from .apps_views import AppsAPIView
from .common import are_you_there, get_api_info, get_system_version

app_name = "openapi"

router_drf = drfrouters.DefaultRouter()
router = routers.SimpleRouter(trailing_slash=False)

urlpatterns = [
    path("", include(router_drf.urls)),
    path("", include(router.urls)),
    # Generic API endpoints
    path("are-you-there", are_you_there),
    path("system-version", get_system_version),
    path("api-info", get_api_info),
    # API class Apps
    path("apps", AppsAPIView.as_view()),
]
