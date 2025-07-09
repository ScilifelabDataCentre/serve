import json
import os
from datetime import datetime

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from apps.models import AppCategories, Apps, K8sUserAppStatus, ShinyInstance, Subdomain
from common.models import UserProfile
from projects.models import Project
from studio.utils import get_logger

logger = get_logger(__name__)


User = get_user_model()

test_user = {"username": "foo@test.com", "email": "foo@test.com", "password": "bar"}


class ContentStatsApiTests(APITestCase):
    """Tests for the content stats API resource endpoints"""

    BASE_API_URL = "/openapi/v1/"

    def load_data(self):
        # Create a public app with status Running
        self.user = User.objects.create_user(test_user["username"], test_user["email"], test_user["password"])
        self.profile = UserProfile.objects.create(user=self.user, is_approved=True, affiliation="slu")
        self.project = Project.objects.create_project(name="test-perm", owner=self.user, description="")
        self.category = AppCategories.objects.create(name="Serve", priority=100, slug="serve")

        # App type shinyproxyapp should be combined with shiny app so good to test shiny
        self.app = Apps.objects.create(name="Shiny Proxy App", slug="shinyproxyapp", category=self.category)

        subdomain = Subdomain.objects.create(subdomain="test_internal")
        k8s_user_app_status = K8sUserAppStatus.objects.create(status="Running")
        self.app_instance = ShinyInstance.objects.create(
            access="public",
            owner=self.user,
            name="test_open_api_content_stats_app",
            description="My app description",
            app=self.app,
            project=self.project,
            k8s_values={
                "appconfig": {"port": 9999, "image": "ghcr.io/scilifelabdatacentre/test-shiny:3"},
                "permission": "public",
            },
            subdomain=subdomain,
            k8s_user_app_status=k8s_user_app_status,
        )

    def test_with_preloaded_contents(self):
        """Tests the API resource with some pre-loaded users, projects and apps."""

        self.load_data()

        url = os.path.join(self.BASE_API_URL, "content-stats")
        response = self.client.get(url, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        actual = json.loads(response.content)["data"]

        # Perform a second request and verify the counts have not changed
        response2 = self.client.get(url, format="json")
        self.assertEqual(response2.status_code, status.HTTP_200_OK)
        actual2 = json.loads(response2.content)["data"]

        def verify_response(actual):
            self.assertIsNotNone(actual)
            self.assertIsInstance(actual, dict)
            self.assertTrue(len(actual) > 1)

            self.assertIsNotNone(actual["stats_date_utz"])
            stats_date = datetime.strptime(actual["stats_date_utz"], "%Y-%m-%dT%H:%M:%S.%fZ")
            self.assertIsInstance(stats_date, datetime)
            self.assertEqual(stats_date.date(), datetime.today().date())

            self.assertTrue(actual["stats_success"])
            self.assertIsNone(actual["stats_message"])

            self.assertEqual(actual["n_projects"], 1)
            self.assertEqual(actual["n_users"], 1)
            self.assertEqual(actual["n_apps"], 1)
            self.assertEqual(actual["n_apps_public"], 1)

            self.assertIsNotNone(actual["apps_by_type"])
            self.assertTrue(len(actual["apps_by_type"]) > 1)
            self.assertEqual(actual["apps_by_type"]["shinyapp"], 1)
            self.assertEqual(actual["apps_by_type"]["customapp"], 0)
            self.assertEqual(actual["apps_by_type"]["dashapp"], 0)
            self.assertEqual(actual["apps_by_type"]["gradio"], 0)
            self.assertEqual(actual["apps_by_type"]["streamlit"], 0)

            self.assertEqual(actual["new_users_by_year"], {str(datetime.today().year): 1})

            self.assertEqual(actual["users_by_university"], {"slu": 1})

            self.assertIsNotNone(actual["apps_by_image_registry"])
            self.assertEqual(len(actual["apps_by_image_registry"]), 3)
            self.assertEqual(actual["apps_by_image_registry"]["dockerhub"], 0)
            self.assertEqual(actual["apps_by_image_registry"]["ghcr"], 1)
            self.assertEqual(actual["apps_by_image_registry"]["noimage"], 0)

        # Verify the responses
        verify_response(actual)
        verify_response(actual2)

    def test_with_empty_contents(self):
        """Tests the API resource against an empty system."""

        url = os.path.join(self.BASE_API_URL, "content-stats")
        response = self.client.get(url, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        actual = json.loads(response.content)["data"]

        self.assertIsNotNone(actual)
        self.assertIsInstance(actual, dict)
        self.assertTrue(len(actual) > 1)

        self.assertIsNotNone(actual["stats_date_utz"])
        stats_date = datetime.strptime(actual["stats_date_utz"], "%Y-%m-%dT%H:%M:%S.%fZ")
        self.assertIsInstance(stats_date, datetime)
        self.assertEqual(stats_date.date(), datetime.today().date())
        self.assertTrue(actual["stats_success"])
        self.assertIsNone(actual["stats_message"])

        self.assertEqual(actual["n_projects"], 0)
        self.assertEqual(actual["n_users"], 0)
        self.assertEqual(actual["n_apps"], 0)
        self.assertEqual(actual["n_apps_public"], 0)

        self.assertIsNotNone(actual["apps_by_type"])
        self.assertTrue(len(actual["apps_by_type"]) > 1)
        self.assertEqual(actual["apps_by_type"]["shinyapp"], 0)
        self.assertEqual(actual["apps_by_type"]["customapp"], 0)
        self.assertEqual(actual["apps_by_type"]["dashapp"], 0)
        self.assertEqual(actual["apps_by_type"]["gradio"], 0)
        self.assertEqual(actual["apps_by_type"]["streamlit"], 0)

        self.assertEqual(actual["new_users_by_year"], {})

        self.assertEqual(actual["users_by_university"], {})

        self.assertIsNotNone(actual["apps_by_image_registry"])
        self.assertEqual(len(actual["apps_by_image_registry"]), 3)
        self.assertEqual(actual["apps_by_image_registry"]["dockerhub"], 0)
        self.assertEqual(actual["apps_by_image_registry"]["ghcr"], 0)
        self.assertEqual(actual["apps_by_image_registry"]["noimage"], 0)
