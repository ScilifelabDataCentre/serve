from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from rest_framework import viewsets
from rest_framework.exceptions import NotFound

from apps.models import BaseAppInstance, Apps
from studio.utils import get_logger

logger = get_logger(__name__)


class PublicAppsAPI(viewsets.ReadOnlyModelViewSet):
    """
    The Public Apps API with read-only methods to get public apps information.
    """

    # TODO: refactor. Rename list to list_apps, because it is a reserved word in python.
    def list(self, request):
        """
        This endpoint gets a list of public apps.
        :returns list: A list of app information.
        """
        logger.info("PublicAppsAPI. Entered list method.")
        logger.info("Requested API version %s", request.version)

        queryset = (
            BaseAppInstance.objects.filter(~Q(app_status__status="Deleted"), access="public")
            .order_by("-updated_on")[:8]
            .values("id", "name", "app_id", "table_field", "description", "updated_on")
        )

        list_apps = list(queryset)
        for app in list_apps:
            add_data = Apps.objects.get(id=app["app_id"])
            app["app_type"] = add_data.name
        data = {"data": list_apps}
        logger.info("LIST: %s", data)
        return JsonResponse(data)

    def retrieve(self, request, pk=None):
        """
        This endpoint retrieves a single public app instance.
        :returns dict: A dict of app information.
        """
        logger.info("PublicAppsAPI. Entered retrieve method with pk = %s", pk)
        logger.info("Requested API version %s", self.request.version)
        queryset = BaseAppInstance.objects.all().values(
            "id", "name", "app_id", "table_field", "description", "updated_on", "access", "app_status"
        )
        app = get_object_or_404(queryset, pk=pk)
        if app.app_status.status == "Deleted":
            raise NotFound("this app has been deleted")
        if app.access != "public":
            raise NotFound()

        add_data = Apps.objects.get(id=app["app_id"])
        app["app_type"] = add_data.name
        data = {"app": app}
        return JsonResponse(data)
