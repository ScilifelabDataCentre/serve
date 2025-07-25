from typing import Any

from django.core.exceptions import FieldError
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from rest_framework import viewsets
from rest_framework.exceptions import NotFound
from rest_framework.request import Request

from apps.app_registry import APP_REGISTRY
from apps.models import Apps, BaseAppInstance, K8sUserAppStatus
from studio.utils import get_logger

logger = get_logger(__name__)


class PublicAppsAPI(viewsets.ReadOnlyModelViewSet):
    """
    The Public Apps API with read-only methods to get public apps information.
    """

    def list_apps(self, request: Request) -> Any:
        """
        This endpoint gets a list of public apps.
        :returns list: A list of app information, ordered by date created from the most recent to the oldest.

        Available GET query parameters:
        - limit: integer. Optional. Determines the maximum number of records to return.

        Example requests:
        /openapi/v1/public-apps
        /openapi/v1/public-apps?limit=5
        """
        logger.info("PublicAppsAPI. Entered list method. Requested API version %s", request.version)
        list_apps = []
        list_apps_dict = {}

        # Handle user input parameters
        limit: int | None = request.GET.get("limit")

        try:
            limit = int(limit) if limit else None
        except Exception:
            return JsonResponse({"error": "The input limit in invalid."}, status=403)

        # NB: It is important that it only returns public apps
        try:
            for model_class in APP_REGISTRY.iter_orm_models():
                # Loop over all models, and check if they have the access and description field
                # Note: It is not possible to use BaseAppInstance.objects.get_app_instances_not_deleted here
                # This is the reason for looping over model_class instead
                if hasattr(model_class, "description") and hasattr(model_class, "access"):
                    queryset = (
                        model_class.objects.filter(access="public")
                        .select_related("k8s_user_app_status")
                        .values(
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
                            "k8s_user_app_status__status",
                        )
                    )

                    # Using a dictionary to avoid duplicates for shiny apps
                    for item in queryset:
                        # k8s_user_app_status must be the string text version, not id
                        item["k8s_user_app_status"] = item.get("k8s_user_app_status__status")
                        del item["k8s_user_app_status__status"]

                        app_status = BaseAppInstance.convert_to_app_status(
                            item.get("latest_user_action"),
                            item.get("k8s_user_app_status"),
                        )

                        # Do not include deleted apps
                        if app_status != "Deleted":
                            item["app_status"] = app_status
                            list_apps_dict[item["id"]] = item

                # Order the combined list by "created_on"
                list_apps = sorted(list_apps_dict.values(), key=lambda x: x["created_on"], reverse=True)

                # Truncate to limit (after sorting is done)
                if limit is not None and limit > 0:
                    # This list is small enough that slicing is performant
                    list_apps = list_apps[:limit]

            for app in list_apps:
                assert app["app_status"] != "Deleted"

                app["app_type"] = Apps.objects.get(id=app["app_id"]).name

                # Add the previous url key located at app.table_field.url to support clients using the previous schema
                app["table_field"] = {"url": app["url"]}

                # Remove misleading app_id from the final output because it only refers to the app type
                del app["app_id"]

        except Exception as e:
            logger.error("Unable to collect a list of the public apps. %s", e)
            return JsonResponse({"error": f"Unable to collect a list of the public apps. {e}"}, status=500)

        data = {"data": list_apps}
        return JsonResponse(data)

    def retrieve(self, request: Request, pk_in: int) -> Any:
        """
        This endpoint retrieves a single public app instance.
        :pk_in: The primary key of the public app to return.
        :returns dict: A dict of app information.
        """
        logger.info("PublicAppsAPI. Entered retrieve method. Requested API version %s", request.version)

        # Handle user input parameters
        if pk_in is None or pk_in < 1:
            return JsonResponse({"error": "The input app id in invalid."}, status=403)

        # First retrieve the app slug by id
        app = BaseAppInstance.objects.filter(pk=pk_in).first()

        if app is None:
            raise NotFound("An app with this id does not exist.")

        app_slug = app.app.slug
        model_class = APP_REGISTRY.get_orm_model(app_slug)

        if not hasattr(model_class, "description") or not hasattr(model_class, "access"):
            raise NotFound("An app with this id does not exist (incorrect type).")

        try:
            queryset = (
                model_class.objects.filter(pk=pk_in)
                .filter(access="public")
                .select_related("k8s_user_app_status")
                .values(
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
                    "k8s_user_app_status__status",
                )
            )

        except Exception as e:
            logger.error("Unable to get public app. %s", e)
            return JsonResponse({"error": f"Unable to get public app. {e}"}, status=500)

        app_instance = get_object_or_404(queryset, pk=pk_in)
        if app_instance is None:
            raise NotFound("A public app with the requested id does not exist.")

        # k8s_user_app_status must be the string text version, not id
        app_instance["k8s_user_app_status"] = app_instance.get("k8s_user_app_status__status")
        del app_instance["k8s_user_app_status__status"]

        app_status = BaseAppInstance.convert_to_app_status(
            app_instance.get("latest_user_action"),
            app_instance.get("k8s_user_app_status"),
        )

        if app_status == "Deleted":
            raise NotFound("This app has been deleted")

        app_instance["app_status"] = app_status

        if app_instance.get("access", False) != "public":
            raise NotFound("This app is non-existent or not public")

        app_type_info = Apps.objects.get(id=app_instance["app_id"])
        app_instance["app_type"] = app_type_info.name

        # Remove misleading app_id from the final output because it only refers to the app type
        del app_instance["app_id"]

        data = {"app": app_instance}
        return JsonResponse(data)
