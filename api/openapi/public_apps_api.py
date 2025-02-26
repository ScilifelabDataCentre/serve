from django.core.exceptions import FieldError
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from rest_framework import viewsets
from rest_framework.exceptions import NotFound

from apps.app_registry import APP_REGISTRY
from apps.models import Apps, BaseAppInstance
from studio.utils import get_logger

logger = get_logger(__name__)


class PublicAppsAPI(viewsets.ReadOnlyModelViewSet):
    """
    The Public Apps API with read-only methods to get public apps information.
    """

    def list_apps(self, request):
        """
        This endpoint gets a list of public apps.
        :returns list: A list of app information, ordered by date created from the most recent to the oldest.
        """
        logger.info("PublicAppsAPI. Entered list method.")
        logger.info("Requested API version %s", request.version)
        list_apps = []
        list_apps_dict = {}

        # TODO: MAKE SURE THAT THIS IS FILTERED BASED ON ACCESS
        for model_class in APP_REGISTRY.iter_orm_models():
            # Loop over all models, and check if they have the access and description field
            # Note: It is not possible to use BaseAppInstance.objects.get_app_instances_not_deleted here
            # This is the reason for looping over model_class instead
            if hasattr(model_class, "description") and hasattr(model_class, "access"):
                queryset = model_class.objects.filter(access="public").values(
                    "id",
                    "name",
                    "app_id",
                    "url",
                    "description",
                    "created_on",
                    "updated_on",
                    "latest_user_action",
                    "k8s_user_app_status",
                )
                # Using a dictionary to avoid duplicates for shiny apps
                for item in queryset:
                    # Do not include deleted apps
                    app_status = BaseAppInstance.convert_to_app_status(
                        item.get("latest_user_action"),
                        item.get("k8s_user_app_status"),
                    )
                    if app_status != "Deleted":
                        item["app_status"] = app_status
                        list_apps_dict[item["id"]] = item

            # Order the combined list by "created_on"
            list_apps = sorted(list_apps_dict.values(), key=lambda x: x["created_on"], reverse=True)

        for app in list_apps:
            assert app["app_status"] != "Deleted"

            app["app_type"] = Apps.objects.get(id=app["app_id"]).name

            # Add the previous url key located at app.table_field.url to support clients using the previous schema
            app["table_field"] = {"url": app["url"]}

            # Remove misleading app_id from the final output because it only refers to the app type
            del app["app_id"]

        data = {"data": list_apps}
        logger.info("LIST: %s", data)
        return JsonResponse(data)

    def retrieve(self, request, app_slug=None, pk=None):
        """
        This endpoint retrieves a single public app instance.
        :returns dict: A dict of app information.
        """
        logger.info("PublicAppsAPI. Entered retrieve method with pk = %s", pk)
        logger.info("Requested API version %s", self.request.version)

        model_class = APP_REGISTRY.get_orm_model(app_slug)

        if model_class is None:
            logger.error("App slug has no corresponding model class")
            raise NotFound("Invalid app slug")

        try:
            queryset = model_class.objects.all().values(
                "id",
                "name",
                "app_id",
                "url",
                "description",
                "created_on",
                "updated_on",
                "access",
                "latest_user_action",
                "k8s_user_app_status",
            )

            logger.info("Queryset: %s", queryset)
        except FieldError as e:
            message = f"Error in field: {e}"
            logger.error(f"App type is not available in public view: {message}")
            raise NotFound("App type is not available in public view")

        app_instance = get_object_or_404(queryset, pk=pk)
        if app_instance is None:
            logger.error("App instance is not available")
            raise NotFound("App instance is not available")

        app_status = BaseAppInstance.convert_to_app_status(
            app_instance.get("latest_user_action"),
            app_instance.get("k8s_user_app_status"),
        )

        if app_status == "Deleted":
            logger.info("This app has been deleted")
            raise NotFound("This app has been deleted")

        app_instance["app_status"] = app_status

        if app_instance.get("access", False) != "public":
            logger.info("This app is non-existent or not public")
            raise NotFound("This app is non-existent or not public")

        app_type_info = Apps.objects.get(id=app_instance["app_id"])
        app_instance["app_type"] = app_type_info.name

        # Remove misleading app_id from the final output because it only refers to the app type
        del app_instance["app_id"]

        data = {"app": app_instance}
        logger.info("API call successful")
        return JsonResponse(data)
