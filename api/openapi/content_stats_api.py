from datetime import datetime, timezone

from django.contrib.auth.models import User
from django.http import JsonResponse
from rest_framework import viewsets

from apps.models import BaseAppInstance
from projects.models import Project
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

    # A dict of pre-defined app types in the system.
    # Undefined app types are dynamically added during processing.
    # TODO: consider using APP_REGISTRY
    apps_by_type: dict[str, int] = {
        "customapp": 0,
        "dashapp": 0,
        "gradioapp": 0,
        "shinyapp": 0,
        "streamlitapp": 0,
        "tissuumapsapp": 0,
    }

    def get_stats(self, request):
        logger.info("Open API resource content-stats called")

        stats = {}

        success = True
        success_msg = None

        # Set to default values
        n_default: int = -1

        n_projects = n_default
        n_users = n_default
        n_apps = n_default

        new_users_by_year: list = []

        users_by_univ: list = []

        apps_by_image_registry: dict = {
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
            n_users = User.objects.filter(is_active=True).count()
        except Exception as e:
            success = False
            success_msg = _append_status_msg(success_msg, "Error setting number of users (n_users).")
            logger.warning(f"Unable to get the number of active users: {e}", exc_info=True)

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
                    if app.chart is None:
                        raise Exception("This app has no chart")
                    elif "ghcr.io" in app.chart:
                        apps_by_image_registry["ghcr"] += 1
                    else:
                        apps_by_image_registry["dockerhub"] += 1

                    # Collect app type information
                    if "shiny" in app.app.slug:
                        # Combine all shiny types into one app type
                        self._append_app_type("shinyapp")
                    else:
                        self._append_app_type(app.app.slug)

        except Exception as e:
            success = False
            msg = f"Error setting apps information (n_apps or apps_by_image_registry). {e}"
            success_msg = _append_status_msg(success_msg, msg)
            logger.warning(f"Unable to get the number of user apps: {e}", exc_info=True)

        # Add the generic top-level elements
        stats["stats_date_utz"] = datetime.now(timezone.utc)
        stats["stats_success"] = success
        stats["stats_message"] = success_msg

        # Add content-specific elements
        stats["n_projects"] = n_projects
        stats["n_users"] = n_users
        stats["n_apps"] = n_apps
        stats["apps_by_type"] = ContentStatsAPI.apps_by_type
        stats["new_users_by_year"] = new_users_by_year
        stats["users_by_university"] = users_by_univ
        stats["apps_by_image_registry"] = apps_by_image_registry

        # Apps
        """
        app = apps[0]
        stats["app1_name"] = app.name
        stats["app1_chart"] = app.app.chart
        stats["app1_app_name"] = app.app.name
        stats["app1_app_category.slug"] = app.app.category.slug
        stats["app1_app_slug"] = app.app.slug

        model_class = apps.model
        fields = model_class._meta.get_fields()
        column_names = [field.name for field in fields]
        stats["apps_fields"] = column_names
        """

        data = {"data": stats}

        return JsonResponse(data)

    def _append_app_type(self, app_type: str) -> None:
        """Constructs and increments app type counts."""
        if app_type in ContentStatsAPI.apps_by_type:
            ContentStatsAPI.apps_by_type[app_type] += 1
        else:
            # Append the app type as a new key
            ContentStatsAPI.apps_by_type[app_type] = 1


def _append_status_msg(status_msg: str, new_msg: str) -> str:
    """Simple helper function to format status messages."""
    if status_msg is None:
        return new_msg
    else:
        return f"{status_msg} {new_msg}"
