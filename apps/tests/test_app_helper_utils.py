"""This module is used to test the helper functions that are used by user app instance functionality."""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from projects.models import Project

from ..models import Apps, JupyterInstance, K8sUserAppStatus

User = get_user_model()


class CreateAppInstanceTestCase(TestCase):
    """Test case for testing create_instance_from_form"""

    def setUp(self):
        self.user = User.objects.create_user("foo1", "foo@test.com", "bar")

    def test_create_instance_from_form_valid_input(self):
        # TODO: Status
        self.assertTrue(1 == 0)

    def test_create_instance_from_form_invalid_input(self):
        # TODO: Status
        self.assertTrue(1 == 0)


class UpdateExistingAppInstanceTestCase(TestCase):
    """Test case for test create_instance_from_form and an existing user app instance."""

    def setUp(self) -> None:
        self.user = User.objects.create_user("foo1", "foo@test.com", "bar")
        self.app = Apps.objects.create(
            name="Custom App",
            slug="customapp",
        )

        self.project = Project.objects.create_project(name="test-perm", owner=self.user, description="")

        k8s_user_app_status = K8sUserAppStatus.objects.create()
        self.app_instance = JupyterInstance.objects.create(
            access="public",
            owner=self.user,
            name="test_app_instance_public",
            app=self.app,
            project=self.project,
            k8s_user_app_status=k8s_user_app_status,
        )

    def test_create_instance_from_form_valid_input(self):
        # TODO: Status. Implement
        self.assertTrue(1 == 0)

    def test_create_instance_from_form_invalid_input(self):
        # TODO: Status. Implement
        self.assertTrue(1 == 0)
