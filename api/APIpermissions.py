from datetime import datetime, timedelta, timezone

from django.conf import settings
from rest_framework.permissions import BasePermission

from .serializers import Project


class IsTokenAuthenticated(BasePermission):
    code = "401 Unauthorized"
    message = "The authentication token is not valid. It may have expired."

    def has_permission(self, request, view):
        """
        Denies requests for users who lack a valid authentication token.
        Similar to DRF:s own IsAuthenticated permission class.
        Returns a boolean value that DRF will convert to an exception.
        """

        # If the user token is older than AUTH_TOKEN_EXPIRATION, then consider it expired
        # Give a small 10 second grace duration to give the CustomAuthToken class a chance to renew the token
        # The request.auth.created field contains a datetime value
        token_expiry = request.auth.created + timedelta(seconds=settings.AUTH_TOKEN_EXPIRATION + 10)

        print(f"DEBUG - Token expires = {token_expiry}, has expired = {datetime.now(timezone.utc) < token_expiry}")

        # The user has permission if the token is still valid (has not expired)
        return datetime.now(timezone.utc) < token_expiry


class ProjectPermission(BasePermission):
    def has_permission(self, request, view):
        """
        Should simply return, or raise a 403 response.
        """
        is_authorized = False
        project = Project.objects.get(pk=view.kwargs["project_pk"])

        # TODO: Check users project roles.
        if request.user == project.owner:
            is_authorized = True
        elif request.user in project.authorized.all():
            is_authorized = True
        print("Is authorized: {}".format(is_authorized))
        return is_authorized


class AdminPermission(BasePermission):
    def has_permission(self, request, view):
        """
        Should simply return, or raise a 403 response.
        """
        is_authorized = False

        if request.user.is_superuser:
            is_authorized = True
        print("Is authorized: {}".format(is_authorized))
        return is_authorized
