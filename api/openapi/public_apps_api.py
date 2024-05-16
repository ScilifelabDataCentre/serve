from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.core.exceptions import FieldError
from rest_framework import viewsets
from rest_framework.exceptions import NotFound

from apps.models import BaseAppInstance, Apps, AppStatus
from apps.constants import SLUG_MODEL_FORM_MAP
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
        list_apps = []
        
        #TODO: MAKE SURE THAT THIS IS FILTERED BASED ON ACCESS
        for model_class, _ in SLUG_MODEL_FORM_MAP.values():
            # Loop over all models, and check if they have the access and description field
            if getattr(model_class, "description", None) and getattr(model_class, "access", None):
                queryset = (
                    model_class.objects.filter(~Q(app_status__status="Deleted"), access="public")
                    .order_by("-updated_on")[:8]
                    .values("id", "name", "app_id", "url", "description", "updated_on", "app_status")
                )
                list_apps.extend(list(queryset))
            
        for app in list_apps:
            app["app_type"] = Apps.objects.get(id=app["app_id"]).name
            app["app_status"] = AppStatus.objects.get(pk=app["app_status"]).status
            
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
        
        model_class = SLUG_MODEL_FORM_MAP.get(app_slug, (None, None))[0]

        if model_class is None:
            logger.error("App slug has no corresponding model class")
            raise NotFound("Invalid app slug")
        
        try:
            queryset = model_class.objects.all().values(
                "id", "name", "app_id", "url", "description", "updated_on", "access", "app_status"
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
        
        app_status_pk = app_instance.get("app_status", None)
        logger.info("DID WE GET HERE?!")
        if app_status_pk is None:
            raise NotFound("App status is not available")
        
        app_status = AppStatus.objects.get(pk=app_status_pk)
        if app_status.status == "Deleted":
            logger.error("This app has been deleted")
            raise NotFound("This app has been deleted")
        
        if app_instance.get("access", False) != "public":
            logger.error("This app is non-existent or not public")
            raise NotFound("This app is non-existent or not public")

        app_instance["app_status"] = app_status.status
        
        add_data = Apps.objects.get(id=app_instance["app_id"])
        app_instance["app_type"] = add_data.name
        data = {"app": app_instance} 
        logger.info("API call successful")
        return JsonResponse(data)
