import json
import os

from rest_framework import status
from rest_framework.test import APITestCase


class OpenApiTests(APITestCase):
    """Tests for the Open API generic base endpoints"""

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
