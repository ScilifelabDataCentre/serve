from django.http import JsonResponse
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from api.services.loki import get_unique_ingress_ip_count
from apps.models import BaseAppInstance
from studio.utils import get_logger

logger = get_logger(__name__)


class UniqueIngressIPCountAPI(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, app_subdomain: str):
        """
        Returns the count of unique IPs that accessed the app (by subdomain) in the last 29 days.
        Only admin and the app owner can access this endpoint.
        """
        if not app_subdomain:
            return JsonResponse({"error": "Missing required parameter: app_subdomain"}, status=400)

        # Check subdomain exists
        try:
            app_instance = BaseAppInstance.objects.get(subdomain__subdomain=app_subdomain)
        except Exception as e:
            logger.error("Subdomain not found. %s", e)
            return JsonResponse({"error": f"Subdomain not found. {e}"}, status=404)

        # Check app ownership
        if request.user.is_superuser or request.user == app_instance.owner:
            try:
                count = get_unique_ingress_ip_count(app_instance.namespace, app_subdomain)
                return JsonResponse({"app_subdomain": app_subdomain, "unique_ip_count": count})
            except Exception as e:
                return JsonResponse({"error": f"Error retrieving data: {str(e)}"}, status=500)
        else:
            return JsonResponse(
                {"error": "You do not have permission to access this app's monitoring data."}, status=403
            )
