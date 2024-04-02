import json
from datetime import datetime, timezone

import requests
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.exceptions import ObjectDoesNotExist
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.http import HttpResponse, HttpResponseRedirect
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
from studio.utils import get_logger

logger = get_logger(__name__)


@receiver(pre_save, sender=User)
def set_new_user_inactive(sender, instance, **kwargs):
    if instance._state.adding and settings.INACTIVE_USERS and not instance.is_superuser:
        logger.info("Creating Inactive User")
        instance.is_active = False
    else:
        logger.info("Updating User Record")


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
    except ObjectDoesNotExist as e:
        logger.error(str(e), exc_info=True)
        user_profile = UserProfile()
    except Exception as e:
        logger.error(str(e), exc_info=True)
        user_profile = UserProfile()

    return render(request, "user/profile.html", {"user_profile": user_profile})


@login_required
def delete_account(request):
    logger.debug("Rendering page delete a user account.")
    logger.info(f"User views page to delete their user account. User {request.user}")

    account_can_be_deleted = False

    # Check if the user owns any projects
    try:
        projects = Project.objects.filter(owner=request.user)

        if len(projects) == 0:
            account_can_be_deleted = True
            logger.debug("User account CAN be deleted. The user does not own any projects.")
        else:
            account_can_be_deleted = False
            logger.info(f"User account cannot be deleted. The user owns {len(projects)} projects.")
    except TypeError as err:
        account_can_be_deleted = False
        logger.error(str(err), exc_info=True)

    # Then POST, and verify csrf

    return render(request, "user/account_delete_form.html", {"account_can_be_deleted": account_can_be_deleted})


@login_required
def do_delete_account(request, user_id):
    if request.method == "POST":
        logger.info(f"POST action to do_delete_account with User {request.user.id}, input {user_id=}")
        logger.debug(request.POST)

        logger.debug(f"POST action to do_delete_account with User {request.user}")

        # Verify that the current session user account id = user_id
        if user_id != request.user.id:
            logger.error(f"Unable to delete user. Invalid input parameter {user_id=} unequal {request.user.id=}")
            return HttpResponse("Unable to delete user account. Server error.", status=500)

        user = User.objects.get(pk=user_id)

        user_account_deleted = False

        # TODO: Try catch
        # Set user Active = false
        user.is_active = False
        # user.deleted_date = datetime.now(timezone.utc)
        # user.save(update_fields=["deleted_date"])

        user_account_deleted = True
        # Remove cookie session
        # Logg info

        if user_account_deleted is True:
            # Send email
            logger.debug(f"User account was deleted (set to inactive). Now sending email to user email {user.email}")

    # Redirect to new view
    return HttpResponseRedirect(
        reverse(
            "account_deleted",
            kwargs={"user_id": user_id},
        )
    )


def account_deleted(request, user_id):
    return render(request, "user/account_deleted.html", {"user_id": user_id})


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
    logger.info(f"Making an API request to URL {api_url}")
    response = requests.get(api_url, params={"code": code})

    if response.status_code == 200:
        data = response.json()["data"]
        return data["name"]
    else:
        raise Exception("API did not return status 200")
