"""This module is used to test the helper functions that are used by user app instance functionality."""

import unittest
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from projects.models import Flavor, Project

from ..app_registry import APP_REGISTRY
from ..helpers import create_instance_from_form
from ..models import Apps, JupyterInstance, K8sUserAppStatus

User = get_user_model()


class CreateAppInstanceTestCase(TestCase):
    """Test case for testing create_instance_from_form"""

    def setUp(self):
        self.user = User.objects.create_user("foo1", "foo@test.com", "bar")
        self.project = Project.objects.create_project(name="test-app-creation", owner=self.user, description="")

    @unittest.expectedFailure
    def test_create_instance_from_form_valid_input(self):
        # TODO: Status

        # Create the form data
        flavor = Flavor.objects.filter(project=self.project).first()

        app_slug = "dashapp"

        data = {
            "name": "app-form-name",
            "description": "app-form-description",
            "flavor": str(flavor.pk),
            "access": "public",
            "port": 8000,
            "image": "some-image",
            "source_code_url": "https://someurlthatdoesnotexist.com",
        }

        _, form_class = APP_REGISTRY.get(app_slug)
        form = form_class(data, project_pk=self.project.pk)

        with patch("apps.tasks.delete_resource.delay") as mock_task:  # noqa: F841
            create_instance_from_form(form, self.project, app_slug, app_id=None)

            pass

        self.assertTrue(1 == 0)

    @unittest.expectedFailure
    def test_create_instance_from_form_invalid_input(self):
        # TODO: Status
        with patch("apps.tasks.delete_resource.delay") as mock_task:  # noqa: F841
            pass

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

    @unittest.expectedFailure
    def test_create_instance_from_form_valid_input(self):
        # TODO: Status. Implement
        with patch("apps.tasks.delete_resource.delay") as mock_task:  # noqa: F841
            pass

        self.assertTrue(1 == 0)

    @unittest.expectedFailure
    def test_create_instance_from_form_invalid_input(self):
        # TODO: Status. Implement
        with patch("apps.tasks.delete_resource.delay") as mock_task:  # noqa: F841
            pass

        self.assertTrue(1 == 0)
