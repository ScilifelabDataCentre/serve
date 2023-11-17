import json

import requests
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.http import HttpResponseRedirect
from django.shortcuts import render, reverse
from rest_framework.authentication import (
    BasicAuthentication,
    SessionAuthentication,
    TokenAuthentication,
)
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.models import AppInstance
from common.models import UserProfile
from projects.models import Project


@receiver(pre_save, sender=User)
def set_new_user_inactive(sender, instance, **kwargs):
    if instance._state.adding is True and settings.INACTIVE_USERS:
        print("Creating Inactive User")
        instance.is_active = False
    else:
        print("Updating User Record")


@receiver(post_save, sender=UserProfile)
def post_save_userprofile(sender, instance, **kwargs):
    if not settings.INACTIVE_USERS:
        user = instance.user
        user.is_active = instance.is_approved
        user.save()


# Since this is a production feature, it will only work if DEBUG is set to False


def handle_page_not_found(request, exception):
    return HttpResponseRedirect("/")


class AccessPermission(BasePermission):
    def has_permission(self, request, view):
        """
        Should simply return, or raise a 403 response.
        """
        try:
            release = request.GET.get("release")
            app_instance = AppInstance.objects.filter(parameters__contains={"release": release}).last()
            project = app_instance.project
        # TODO: Make it an explicit exception. At least catch `Exception`
        except:  # noqa: E722
            project_slug = request.GET.get("project")
            project = Project.objects.get(slug=project_slug)
            return request.user.has_perm("can_view_project", project)

        if app_instance.access == "private":
            return app_instance.owner == request.user
        elif app_instance.access == "project":
            return request.user.has_perm("can_view_project", project)
        else:
            return True


class ModifiedSessionAuthentication(SessionAuthentication):
    """
    This class is needed, because REST Framework's default SessionAuthentication does never return 401's,
    because they cannot fill the WWW-Authenticate header with a valid value in the 401 response. As a
    result, we cannot distinguish calls that are not unauthorized (401 unauthorized) and calls for which
    the user does not have permission (403 forbidden). See https://github.com/encode/django-rest-framework/issues/5968
    We do set authenticate_header function in SessionAuthentication, so that a value for the WWW-Authenticate
    header can be retrieved and the response code is automatically set to 401 in case of unauthenticated requests.
    """

    def authenticate_header(self, request):
        return "Session"


class AuthView(APIView):
    authentication_classes = [ModifiedSessionAuthentication, TokenAuthentication]
    permission_classes = [IsAuthenticated, AccessPermission]

    def get(self, request, format=None):
        content = {
            "user": str(request.user),
            "auth": str(request.auth),
        }
        return Response(content)


@login_required
def profile(request):
    # Get the user profile
    try:
        # Note that not all users have a user profile object
        # such as the admin superuser
        user_profile = UserProfile.objects.get(user_id=request.user.id)
    except:  # noqa E722 OK here
        user_profile = UserProfile()

    # The affiliation friendly name is set via ajax
    host = request.build_absolute_uri("/")
    API_URL = host + reverse("v1:openapi-lookups-universities")

    return render(request, "user/profile.html", {"user_profile": user_profile, "API_URL": API_URL})


def __get_university_name(request, code):
    """Gets the university name by making an API call.
    :param request: The request object.
    :param str code: The university code.
    :returns str name: The university name.
    """
    # Get the affiliation name from an API call to /universities by code
    # Note that reversing the url of openapi-v1 was not working
    host = request.build_absolute_uri("/")
    api_url = host + reverse("v1:openapi-lookups-universities")
    print(f"Making an API request to URL {api_url}")
    response = requests.get(api_url, params={"code": code})

    if response.status_code == 200:
        data = response.json()["data"]
        return data["name"]
    else:
        raise Exception("API did not return status 200")
