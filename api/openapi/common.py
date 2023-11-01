from django.http import JsonResponse

from studio.system_version import SystemVersion


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


def get_api_info(request):
    """
    Gets the API information.
    See https://dev.dataportal.se/rest-api-profil/versionhantering
    :returns dict: A dictionary of API information.
    """
    data = {
        "apiName": "SciLifeLab Serve OpenAPI",
        "apiVersion": "1.0.0",
        "apiReleased": "TODO",
        "apiDocumentation": "TODO",
        "apiStatus": "beta",
        "latest-api-version": "v1",
    }
    return JsonResponse(data)
