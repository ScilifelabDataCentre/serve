import rest_framework.routers as drfrouters
from django.conf.urls import include
from django.urls import path
from rest_framework_nested import routers

from .public_views import are_you_there, get_studio_settings
from .views import (
    AppInstanceList,
    AppList,
    CustomAuthToken,
    EnvironmentList,
    FlavorsList,
    MembersList,
    MetadataList,
    ModelList,
    ModelLogList,
    ObjectTypeList,
    ProjectList,
    ProjectTemplateList,
    ResourceList,
    container_image_search,
    get_content_review,
    get_subdomain_input_html,
    get_subdomain_is_available,
    get_subdomain_is_valid,
    get_unique_ingress_ip_count,
    update_app_status,
    validate_password_request,
)

app_name = "api"

router_drf = drfrouters.DefaultRouter()
router = routers.SimpleRouter()
router.register(r"projects", ProjectList, basename="project")
router.register(r"apps", AppList, basename="apps")
router.register(r"projecttemplates", ProjectTemplateList, basename="projecttemplates")

models_router = routers.NestedSimpleRouter(router, r"projects", lookup="project")
models_router.register(r"models", ModelList, basename="model")
models_router.register(r"objecttype", ObjectTypeList, basename="objecttype")
models_router.register(r"members", MembersList, basename="members")
models_router.register(r"resources", ResourceList, basename="resources")
models_router.register(r"appinstances", AppInstanceList, basename="appinstances")
models_router.register(r"flavors", FlavorsList, basename="flavors")
models_router.register(r"environments", EnvironmentList, basename="environment")
models_router.register(r"modellogs", ModelLogList, basename="modellog")
models_router.register(r"metadata", MetadataList, basename="metadata")
models_router.register(r"apps", AppList, basename="apps")

urlpatterns = [
    path("", include(router_drf.urls)),
    path("", include(router.urls)),
    path("", include(models_router.urls)),
    # Generic API endpoints
    path("are-you-there/", are_you_there),
    # Internal API endpoints
    path("token-auth/", CustomAuthToken.as_view(), name="api_token_auth"),
    path("settings/", get_studio_settings),
    # TODO: Consider renaming this endpoint to update-k8s-app-status
    path("app-status/", update_app_status),
    path("app-subdomain/validate/", get_subdomain_is_valid),
    path("app-subdomain/is-available/", get_subdomain_is_available),
    path("htmx/subdomain-input/", get_subdomain_input_html, name="get_subdomain_input_html"),
    path("validate_password/", validate_password_request, name="validate_password"),
    path("container_image_search/", container_image_search, name="container_image_search"),
    path("content-review/", get_content_review),
    path("monitoring/unique-ip-count/<str:app_subdomain>", get_unique_ingress_ip_count),
]
