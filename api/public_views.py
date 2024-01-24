from django.conf import settings
from django.http import JsonResponse


def get_studio_settings(request):
    """
    This view should return a list of settings
    needed to set up the CLI client.
    """
    studio_settings = []

    studio_url = {"name": "studio_host", "value": settings.STUDIO_HOST}
    studio_settings.append(studio_url)

    return JsonResponse({"data": studio_settings})


def are_you_there(request):
    """
    Most simple API endpoint useful for testing
    and verifications.
    :returns bool: true
    """
    return JsonResponse({"status": True})
