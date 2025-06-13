from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any

from django.contrib.auth.models import User
from django.http import JsonResponse
from rest_framework import viewsets
from rest_framework.request import Request

from apps.models import BaseAppInstance
from common.models import UserProfile
from projects.models import Project
from studio.utils import get_logger

logger = get_logger(__name__)


class ContentStatsAPI(viewsets.ReadOnlyModelViewSet):
    """
    The Content Stats API with read-only methods to get aggregated statistics
    about the content in the system.

    The top-level elements nested under data include:
    - stats_date_utz
    - stats_success
    - stats_message
    - stats_notes
    - n_projects
    - n_users
    - n_apps
    - apps_by_type
    - new_users_by_year
    - users_by_university
    - apps_by_image_registry
    """

    def get_stats(self, request: Request) -> Any:
        logger.info("Open API resource content-stats called")

        stats: dict[str, Any] = {}

        success: bool = True
        success_msg: str | None = None

        # Set to default values
        n_default: int = -1

        n_projects = n_default
        n_users = n_default
        n_apps = n_default

        new_users_by_year: dict[int, int] = {}

        users_by_univ: dict[str, int] = {}

        # A dict of pre-defined app types in the system.
        # Undefined app types are dynamically added during processing.
        # APP_REGISTRY is not used because its terminology is sligtly different.
        apps_by_type: dict[str, int] = defaultdict(int)
        apps_by_type.update(
            {
                "customapp": 0,
                "dashapp": 0,
                "gradio": 0,
                "shinyapp": 0,
                "streamlit": 0,
                "tissuumaps": 0,
            }
        )

        apps_by_image_registry: dict[str, int] = {
            "dockerhub": 0,
            "ghcr": 0,
        }

        # Projects
        try:
            n_projects = Project.objects.filter(status="active").distinct("pk").count()
        except Exception as e:
            success = False
            success_msg = _append_status_msg(success_msg, "Error setting number of projects (n_projects).")
            logger.warning(f"Unable to get the number of active projects: {e}", exc_info=True)

        # Users
        try:
            users = User.objects.filter(is_active=True).filter(is_superuser=False)

            n_users = users.count()

            # Get a list of years that users joined
            # and group by year and convert to dict
            user_dates = list(users.values_list("date_joined", flat=True).order_by("date_joined"))
            user_years = [dt.year for dt in user_dates]
            new_users_by_year = dict(Counter(user_years))
        except Exception as e:
            success = False
            success_msg = _append_status_msg(
                success_msg, "Error setting user information (n_users or new_users_by_year)."
            )
            logger.warning(f"Unable to get user information: {e}", exc_info=True)

        # User affiliation from UserProfile
        try:
            user_profiles = UserProfile.objects.filter(user__is_active=True).filter(user__is_superuser=False)
            user_affiliation = list(user_profiles.values_list("affiliation", flat=True).order_by("affiliation"))
            users_by_univ = dict(Counter(user_affiliation))
        except Exception as e:
            success = False
            success_msg = _append_status_msg(
                success_msg, "Error setting user information (n_users or new_users_by_year)."
            )
            logger.warning(f"Unable to get user information: {e}", exc_info=True)

        # Apps
        # Since we loop over apps to retrieve image registry info,
        # we also collect all app attributes in the same way.
        try:
            apps = BaseAppInstance.objects.get_app_instances_not_deleted()
            n_apps = 0

            for app in apps:
                if app.app.category.slug == "serve":
                    n_apps += 1

                    # Collect app image registry information
                    image = None
                    if app.k8s_values is not None and "appconfig" in app.k8s_values:
                        app_config = app.k8s_values["appconfig"]
                        if "image" in app_config and app_config["image"] is not None:
                            image = app_config["image"]

                    if image is None:
                        logger.info(
                            "An app is missing image information so it was skipped from the image registry counts."
                        )
                    else:
                        if "ghcr.io" in image:
                            apps_by_image_registry["ghcr"] += 1
                        else:
                            apps_by_image_registry["dockerhub"] += 1

                    # Collect app type information
                    if "shiny" in app.app.slug:
                        # Combine all shiny types into one app type
                        apps_by_type["shinyapp"] += 1
                    else:
                        apps_by_type[app.app.slug] += 1

        except Exception as e:
            success = False
            msg = f"Error setting apps information (n_apps or apps_by_image_registry). {e}"
            success_msg = _append_status_msg(success_msg, msg)
            logger.warning(f"Unable to get the number of user apps: {e}", exc_info=True)

        # Add the generic top-level elements
        stats["stats_date_utz"] = datetime.now(timezone.utc)
        stats["stats_success"] = success
        stats["stats_message"] = success_msg
        stats[
            "stats_notes"
        ] = "The number of users (n_users) in 2023 is the number of all active users registered in 2023 or earlier."

        # Add content-specific elements
        stats["n_projects"] = n_projects
        stats["n_users"] = n_users
        stats["n_apps"] = n_apps
        stats["apps_by_type"] = apps_by_type
        stats["new_users_by_year"] = new_users_by_year
        stats["users_by_university"] = users_by_univ
        stats["apps_by_image_registry"] = apps_by_image_registry

        data = {"data": stats}

        return JsonResponse(data)


def _append_status_msg(status_msg: str | None, new_msg: str) -> str:
    """Simple helper function to format status messages."""
    if status_msg is None:
        return new_msg
    else:
        return f"{status_msg} {new_msg}"
