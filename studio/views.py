from typing import Any, Callable, cast

import requests
from django.conf import settings
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Q
from django.db.models.signals import pre_save
from django.dispatch import receiver
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import render, reverse
from rest_framework.authentication import SessionAuthentication, TokenAuthentication
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.app_registry import APP_REGISTRY
from apps.models import BaseAppInstance, Subdomain
from common.models import UserProfile
from common.tasks import send_email_task
from models.models import Model
from projects.models import Project
from studio.utils import get_logger

from .helpers import do_delete_account
from .negotiation import IgnoreClientContentNegotiation

logger = get_logger(__name__)


def disable_for_loaddata(signal_handler: Callable[..., Any]) -> Callable[..., Any]:
    """
    Decorator that turns off signal handlers when loading fixture data.
    """

    def wrapper(*args: Any, **kwargs: Any) -> Any:
        if kwargs.get("raw", False):
            return
        return signal_handler(*args, **kwargs)

    return wrapper


@receiver(pre_save, sender=User)
@disable_for_loaddata
def set_new_user_inactive(sender: Model, instance: User, **kwargs: dict[str, Any]) -> None:
    if instance._state.adding and settings.INACTIVE_USERS and not instance.is_superuser:
        logger.info("Creating Inactive User")
        instance.is_active = False
    else:
        logger.info("Updating User Record")


# Since this is a production feature, it will only work if DEBUG is set to False


def handle_page_not_found(request: Response, exception: Exception) -> HttpResponseRedirect:
    return HttpResponseRedirect("/")


class AccessPermission(BasePermission):
    def has_permission(self, request: Response, view: object) -> bool:
        """
        Should simply return, or raise a 403 response.
        """
        release = request.GET.get("release", None)
        try:
            # Must fetch the subdomain and reverse to the related model.
            subdomain = Subdomain.objects.get(subdomain=release)
            instance = BaseAppInstance.objects.filter(subdomain=subdomain).last()
            project = instance.project
        # TODO: Make it an explicit exception. At least catch `Exception`
        except:  # noqa: E722
            project_slug = request.GET.get("project")
            project = Project.objects.get(slug=project_slug)
            return cast(bool, request.user.has_perm("can_view_project", project))

        model_class = APP_REGISTRY.get_orm_model(instance.app.slug)
        if model_class is None:
            return False
        instance = getattr(instance, model_class.__name__.lower())
        access = getattr(instance, "access", None)

        if access is None:
            return False
        elif instance.access == "private":
            return cast(bool, instance.owner == request.user)
        elif instance.access == "project":
            return cast(bool, request.user.has_perm("can_view_project", project))
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

    def authenticate_header(self, request: Response) -> str:
        return "Session"


class AuthView(APIView):
    authentication_classes = [ModifiedSessionAuthentication, TokenAuthentication]
    permission_classes = [IsAuthenticated, AccessPermission]
    content_negotiation_class = IgnoreClientContentNegotiation

    def get(self, request: Response, format: str | None = None) -> Response:
        content = {
            "user": str(request.user),
            "auth": str(request.auth),
        }
        return Response(content)


@login_required
def profile(request: Response) -> Response:
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
def delete_account(request: Response) -> Response:
    """
    Renders a form that allows a user to delete their user account.
    Verifies that the user does not own any Serve projects.
    """

    # Check if the user owns any projects
    n_projects = Project.objects.filter(Q(owner=request.user), status="active").count()

    if n_projects == 0:
        account_can_be_deleted = True
        logger.debug("User account CAN be deleted. The user does not own any projects.")
    else:
        account_can_be_deleted = False
        logger.info(f"User account cannot be deleted. The user owns {n_projects} projects.")

    return render(request, "user/account_delete_form.html", {"account_can_be_deleted": account_can_be_deleted})


@login_required
def delete_account_post_handler(request: Response, user_id: int) -> Response:
    """
    Handles a POST action request by a user to delete their account.
    """

    if request.method == "POST":
        # Verify that the current session user account id = user_id
        if user_id != request.user.id:
            logger.error(f"Unable to delete user. Invalid input parameter {user_id=} unequal {request.user.id=}")
            return HttpResponse("Unable to delete user account. Server error.", status=500)

        logger.info(f"POST action to do_delete_account with User {request.user.id}, input {user_id=}")
        logger.debug(request.POST)

        user_account_deleted = do_delete_account(user_id)

        if user_account_deleted:
            try:
                # Send email
                email = request.user.email
                logger.debug(f"User account was deleted (set to inactive). Now sending email to user email {email}")

                send_email_task(
                    "User account deleted from SciLifeLab Serve",
                    f"The user account {request.user.username} was deleted from SciLifeLab Serve as requested.",
                    [email],
                    fail_silently=False,
                )

                # Remove cookie session
                logout(request)

            except Exception as err:
                logger.exception(f"Unable to delete user: {user_id=}. {err}", exc_info=True)
                return HttpResponse("Unable to delete user account.", status=500)

            # Redirect to new view
            return HttpResponseRedirect(
                reverse(
                    "account_deleted",
                    kwargs={"user_id": user_id},
                )
            )

        else:
            logger.error(f"Unable to delete user: {user_id=}")
            return HttpResponse("Unable to delete user account.", status=500)


def account_deleted(request: Response, user_id: int) -> Response:
    """Renders a view shown to users at the end of deletion of their account."""
    return render(request, "user/account_deleted.html", {"user_id": user_id})


def __get_university_name(request: Response, code: str) -> str:
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
        return cast(str, data["name"])
    else:
        raise Exception("API did not return status 200")
