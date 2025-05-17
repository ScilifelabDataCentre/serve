import json
import os
import unittest
from datetime import datetime
from unittest.mock import patch

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from apps.models import (
    AppCategories,
    Apps,
    CustomAppInstance,
    K8sUserAppStatus,
    Subdomain,
)
from projects.models import Project
from studio.utils import get_logger

logger = get_logger(__name__)


User = get_user_model()

test_user = {"username": "foo@test.com", "email": "foo@test.com", "password": "bar"}


class ApiTests(APITestCase):
    """
    Normally we do not unit test internal API endpoints because these
    are typically better tested at a lower level. However there are exceptions,
    hence this test module.
    """

    BASE_API_URL = "/api/"

    @classmethod
    def setUpTestData(cls):
        # Create a user
        cls.user = User.objects.create_user(test_user["username"], test_user["email"], test_user["password"])
        # Create a project
        cls.project = Project.objects.create_project(name="test-perm", owner=cls.user, description="")
        # Create a public app with status ImagePullBackOff
        cls.category = AppCategories.objects.create(name="Serve", priority=100, slug="serve")
        cls.app = Apps.objects.create(name="Some App", slug="customapp", category=cls.category)

        subdomain = Subdomain.objects.create(subdomain="test_internal")
        k8s_user_app_status = K8sUserAppStatus.objects.create(status="ImagePullBackOff")
        cls.app_instance = CustomAppInstance.objects.create(
            access="link",
            owner=cls.user,
            name="test_app_instance_public",
            description="My app description",
            app=cls.app,
            project=cls.project,
            k8s_values={
                "environment": {"pk": ""},
            },
            subdomain=subdomain,
            k8s_user_app_status=k8s_user_app_status,
        )

    def test_get_content_review_missing_token_should_return_401(self):
        url = os.path.join(self.BASE_API_URL, "content-review/")
        response = self.client.get(url, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_get_content_review_invalid_token_should_return_401(self):
        url = os.path.join(self.BASE_API_URL, "content-review/")
        response = self.client.get(url, query_params={"token": "badToken"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    @patch("api.views.validate_static_token")
    def test_get_content_review(self, mock_validate_static_token):
        """Tests the endpoint content-review implemented by get_content_review."""

        # Mock the static token validation to return True
        mock_validate_static_token.return_value = True

        url = os.path.join(self.BASE_API_URL, "content-review/")
        response = self.client.get(url, query_params={"token": "someunusedvalue"}, format="json")

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

        self.assertEqual(actual["n_recent_active_users"], 1)
        self.assertEqual(actual["n_recent_inactive_users"], 0)
        self.assertEqual(actual["n_recent_projects"], 1)

        self.assertEqual(actual["n_recent_apps"], 1)
        self.assertEqual(actual["n_apps_link"], 1)
        self.assertEqual(actual["n_apps_not_running"], 1)
        self.assertEqual(actual["n_apps_not_running"], 1)

        # TODO: complete
