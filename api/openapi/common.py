from django.http import JsonResponse


def are_you_there(request):
    """
    Most simple API endpoint useful for testing
    and verifications.
    """
    data = [{"status": True}]
    return JsonResponse({"data": data})


def get_system_version(request):
    """
    Returns the version of the deployed application.
    """
    data = [{"system-version": "TODO"}, {"build-date": "TODO"}, {"image-tag": "TODO"}]
    # data = [{"service-version": "1.0 openapi"}]
    return JsonResponse({"data": data})


def get_api_info(request):
    """
    Returns the API information.
    See https://dev.dataportal.se/rest-api-profil/versionhantering
    """
    data = [{"apiName": "TODO"}, {"apiVersion": "TODO"}, {"apiReleased": "TODO"}]
    data += [{"apiDocumentation": "TODO"}, {"apiStatus": "beta"}]
    data += [{"latest-api-version": "v1.0"}]
    return JsonResponse({"data": data})


def list_apps(request):
    """
    This API endpoint returns
    """
    list_apps = [{"name": "App Name"}]
    data = {"data": list_apps}
    print("LIST: ", data)
    return JsonResponse(data)
