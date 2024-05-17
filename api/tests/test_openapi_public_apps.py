import json
import os
from datetime import date, datetime

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from apps.models import Apps, AppStatus, CustomAppInstance, Subdomain
from projects.models import Project
from studio.utils import get_logger

logger = get_logger(__name__)


User = get_user_model()

test_user = {"username": "foo@test.com", "email": "foo@test.com", "password": "bar"}


class PublicAppsApiTests(APITestCase):
    """Tests for the public apps API resource endpoints"""

    BASE_API_URL = "/openapi/v1/"

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(test_user["username"], test_user["email"], test_user["password"])
        cls.project = Project.objects.create_project(name="test-perm", owner=cls.user, description="")
        cls.app = Apps.objects.create(name="Some App", slug="customapp")

        subdomain = Subdomain.objects.create(subdomain="test_internal")
        app_status = AppStatus.objects.create(status="Running")
        cls.app_instance = CustomAppInstance.objects.create(
            access="public",
            owner=cls.user,
            name="test_app_instance_public",
            description="My app description",
            app=cls.app,
            project=cls.project,
            k8s_values={
                "environment": {"pk": ""},
            },
            subdomain=subdomain,
            app_status=app_status,
        )

    def test_public_apps_list(self):
        """Tests the API resource public-apps default endpoint (action list)"""
        url = os.path.join(self.BASE_API_URL, "public-apps")
        response = self.client.get(url, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        logger.info(response.content)
        actual = json.loads(response.content)["data"]
        self.assertEqual(len(actual), 1)

        app = actual[0]
        self.assertEqual(app["id"], self.app_instance.id)
        self.assertIsNotNone(app["name"])
        self.assertEqual(app["name"], self.app_instance.name)
        self.assertTrue(app["app_id"] > 0)
        self.assertEqual(app["description"], self.app_instance.description)
        updated_on = datetime.fromisoformat(app["updated_on"][:-1])
        self.assertEqual(datetime.date(updated_on), datetime.date(self.app_instance.updated_on))
        self.assertEqual(app["app_type"], self.app_instance.app.name)

    def test_public_apps_single_app(self):
        """Tests the API resource public-apps get single object"""
        id = str(self.app_instance.id)
        app_slug = self.app_instance.app.slug
        url = os.path.join(self.BASE_API_URL, "public-apps", app_slug, id)
        response = self.client.get(url, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        logger.info(response.content)
        actual = json.loads(response.content)["app"]
        logger.info(type(actual))

        self.assertEqual(actual["id"], self.app_instance.id)
        self.assertIsNotNone(actual["name"])
        self.assertEqual(actual["name"], self.app_instance.name)
        self.assertTrue(actual["app_id"] > 0)
        self.assertEqual(actual["description"], self.app_instance.description)
        updated_on = datetime.fromisoformat(actual["updated_on"][:-1])
        self.assertEqual(datetime.date(updated_on), datetime.date(self.app_instance.updated_on))
        self.assertEqual(actual["app_type"], self.app_instance.app.name)

    def test_public_apps_single_app_notfound(self):
        """Tests the API resource public-apps get single object for a non-existing id"""
        id = "-1"
        app_slug = self.app_instance.app.slug
        url = os.path.join(self.BASE_API_URL, "public-apps", app_slug, id)
        response = self.client.get(url, format="json")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        app_slug = "invalid_app_slug"
        url = os.path.join(self.BASE_API_URL, "public-apps", app_slug, id)
        response = self.client.get(url, format="json")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
