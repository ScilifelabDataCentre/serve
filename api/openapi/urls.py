import rest_framework.routers as drfrouters
from django.conf.urls import include
from django.urls import path
from rest_framework_nested import routers

from .common_api import APIInfo, are_you_there, get_system_version
from .content_stats_api import ContentStatsAPI
from .lookups_api import DepartmentLookupAPI, UniversityLookupAPI
from .monitoring import UniqueIngressIPCountAPI
from .public_apps_api import PublicAppsAPI

app_name = "openapi"

router_drf = drfrouters.DefaultRouter()
router = routers.SimpleRouter(trailing_slash=False)

urlpatterns = [
    path("", include(router_drf.urls)),
    path("", include(router.urls)),
    # Generic API endpoints
    path("are-you-there", are_you_there),
    path("system-version", get_system_version),
    path("api-info", APIInfo.as_view({"get": "get_api_info"})),
    # The Public apps resource API
    path("public-apps", PublicAppsAPI.as_view({"get": "list_apps"})),
    path("public-apps/<int:pk_in>", PublicAppsAPI.as_view({"get": "retrieve"})),
    # The Content statistics resource API
    path("content-stats", ContentStatsAPI.as_view({"get": "get_stats"})),
    # Supplementary lookups API
    path(
        "lookups/universities",
        UniversityLookupAPI.as_view({"get": "list_or_single"}),
        name="openapi-lookups-universities",
    ),
    path(
        "lookups/departments",
        DepartmentLookupAPI.as_view({"get": "list"}),
        name="openapi-lookups-departments",
    ),
    # Unique IP count monitoring
    path(
        "monitoring/unique-ip-count/<str:app_subdomain>",
        UniqueIngressIPCountAPI.as_view(),
        name="openapi-monitoring-unique-ip-count",
    ),
]
