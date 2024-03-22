from django.http import JsonResponse
from rest_framework import generics, viewsets
from rest_framework.response import Response

from studio.system_version import SystemVersion
from studio.utils import get_logger

logger = get_logger(__name__)


class OpenAPI(generics.GenericAPIView):
    """
    The Open API basic API information endpoints.
    """

    def get(self, request):
        logger.info("Entered OpenAPI.get. Requested API version %s", request.version)
        return Response({"hello": "world"})


class APIInfo(viewsets.GenericViewSet):
    """
    The Open API basic API information endpoints, in accordance to the standard
    https://dev.dataportal.se/rest-api-profil/versionhantering
    :returns dict: A dictionary of app-info information.
    """

    def get_api_info(self, request):
        logger.info("Entered OpenAPI.get_api_info. Requested API version %s", request.version)

        if request.version == "beta":
            data = {
                "apiName": "SciLifeLab Serve OpenAPI",
                "apiVersion": "beta",
                "apiReleased": "TODO",
                "apiDocumentation": "TODO",
                "apiStatus": "beta",
                "latest-api-version": "v1",
            }
            return JsonResponse(data)

        elif request.version == "v1":
            data = {
                "apiName": "SciLifeLab Serve OpenAPI",
                "apiVersion": "1.0.0",
                "apiReleased": "TODO",
                "apiDocumentation": "TODO",
                "apiStatus": "beta",
                "latest-api-version": "v1",
            }
            return JsonResponse(data)


def are_you_there(request):
    """
    Most simple API endpoint useful for testing
    and verifications.
    :returns bool: true
    """
    return JsonResponse({"status": True})


def get_system_version(request):
    """
    Gets the version of the deployed application.
    :returns dict: A dictionary of system version information.
    """
    data = {
        "system-version": SystemVersion().get_gitref(),
        "build-date": SystemVersion().get_build_date(),
        "image-tag": SystemVersion().get_imagetag(),
    }
    return JsonResponse(data)
