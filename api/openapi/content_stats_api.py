from datetime import datetime, timedelta, timezone

from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from rest_framework import viewsets
from rest_framework.exceptions import NotFound

from studio.utils import get_logger

logger = get_logger(__name__)


class ContentStatsAPI(viewsets.ReadOnlyModelViewSet):
    """
    The Content Stats API with read-only methods to get aggregated statistics
    about the content in the system.

    The top-level elements nested under data include:
    - stats-date
    - TODO
    """

    def get_stats(self, request):
        stats = {}

        n_default: int = -1

        apps_by_type: dict = {
            "custom": n_default,
            "dash": n_default,
            "gradio": n_default,
            "shiny": n_default,
            "streamlit": n_default,
            "tissuumaps": n_default,
        }

        new_users_by_year: list = []

        users_by_univ: list = []

        apps_by_image_registry: dict = {
            "dockerhub": n_default,
            "ghcr": n_default,
        }

        stats["stats_date_utz"] = datetime.now(timezone.utc)
        stats["n_projects"] = n_default
        stats["n_users"] = n_default
        stats["n_apps"] = n_default
        stats["apps_by_type"] = apps_by_type
        stats["new_users_by_year"] = new_users_by_year
        stats["users_by_university"] = users_by_univ
        stats["apps_by_image_registry"] = apps_by_image_registry

        data = {"data": stats}
        logger.info("STATS: %s", data)

        return JsonResponse(data)
