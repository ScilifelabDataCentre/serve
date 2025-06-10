from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from api.services.loki import get_unique_ingress_ip_count
from apps.models import BaseAppInstance


class UniqueIngressIPCountAPI(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, app_subdomain: str):
        """
        Returns the count of unique IPs that accessed the app (by subdomain) in the last 29 days.
        Only the app owner can access this endpoint.
        """
        if not app_subdomain:
            raise ValidationError("Missing required parameter: app_subdomain")

        # Check app ownership
        try:
            app_instance = BaseAppInstance.objects.get(subdomain=app_subdomain)
        except BaseAppInstance.DoesNotExist:
            raise ValidationError("App with the given subdomain does not exist.")
        if app_instance.owner != request.user:
            raise PermissionDenied("You do not have permission to access this app's monitoring data.")

        count = get_unique_ingress_ip_count(app_instance.namespace, app_subdomain)
        return Response({"app_subdomain": app_subdomain, "unique_ip_count": count})
