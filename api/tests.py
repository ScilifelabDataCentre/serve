import json
import os
from datetime import date, datetime

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.models import AppInstance, Apps


class OpenApiTests(APITestCase):
    """Tests for the Open API endpoints"""

    BASE_API_URL = "/openapi/v1/"

    def test_get_are_you_there(self):
        """Tests the API endpoint /are-you-there"""
        url = os.path.join(self.BASE_API_URL, "are-you-there")
        response = self.client.get(url, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        actual = json.loads(response.content)
        self.assertEqual(actual, {"status": True})

    def test_get_system_version(self):
        """Tests the API endpoint /system-version"""
        url = os.path.join(self.BASE_API_URL, "system-version")
        response = self.client.get(url, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        print(response.content)
        actual = json.loads(response.content)
        assert actual["system-version"] == ""
        assert actual["build-date"] == ""
        assert actual["image-tag"] == ""

    def test_app_info(self):
        """Tests the API endpoint /api-info"""
        url = os.path.join(self.BASE_API_URL, "api-info")
        response = self.client.get(url, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        print(response.content)
        actual = json.loads(response.content)
        self.assertEqual(actual["apiName"], "SciLifeLab Serve OpenAPI")
        self.assertEqual(actual["apiVersion"], "1.0.0")
        self.assertEqual(actual["apiReleased"], "TODO")
        self.assertEqual(actual["apiDocumentation"], "TODO")
        self.assertEqual(actual["apiStatus"], "beta")
        self.assertEqual(actual["latest-api-version"], "v1")

    def test_public_apps_list(self):
        """Tests the API resource public-apps default endpoint (action list)"""
        url = os.path.join(self.BASE_API_URL, "public-apps")
        response = self.client.get(url, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        print(response.content)
        actual = json.loads(response.content)["data"]
        # TODO: create test data or mock the service
        self.assertEqual(len(actual), 0)

        for app in actual:
            self.assertTrue(app["id"] > 0)
            self.assertIsNotNone(app["name"])
            self.assertTrue(app["app_id"] > 0)
            self.assertIsNotNone(app["description"])
            self.assertIsTrue(app["updated_on"] > date(2000, 1, 1))
            self.assertIsNotNone(app["app_type"])

    def test_public_apps_single_app(self):
        """Tests the API resource public-apps get single object"""
        id = "3"
        url = os.path.join(self.BASE_API_URL, "public-apps/", id)
        response = self.client.get(url, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        print(response.content)
        actual = json.loads(response.content)["app"]
        print(type(actual))

        self.assertTrue(actual["id"] > 0)
        self.assertIsNotNone(actual["name"])
        self.assertTrue(actual["app_id"] > 0)
        self.assertIsNotNone(actual["description"])
        self.assertIsTrue(actual["updated_on"] > date(2000, 1, 1))
        self.assertIsNotNone(actual["app_type"])

    def test_public_apps_single_app_notfound(self):
        """Tests the API resource public-apps get single object for a non-existing id"""
        id = "-1"
        url = os.path.join(self.BASE_API_URL, "public-apps/", id)
        response = self.client.get(url, format="json")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
