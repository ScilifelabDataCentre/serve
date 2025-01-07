"""This module is used to test the helper functions that are used by user app instance functionality."""

from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.test import TestCase

from projects.models import Flavor, Project

from ..app_registry import APP_REGISTRY
from ..helpers import create_instance_from_form, get_subdomain_name
from ..models import Apps, DashInstance, K8sUserAppStatus, Subdomain
from ..types_.subdomain import SubdomainTuple

User = get_user_model()


class CreateAppInstanceTestCase(TestCase):
    """
    Test case for helper function create_instance_from_form
    while creating a new user app instance.
    """

    def setUp(self):
        self.user = User.objects.create_user("foo1", "foo@test.com", "bar")
        self.project = Project.objects.create_project(name="test-app-creation", owner=self.user, description="")
        self.flavor = Flavor.objects.create(name="flavor", project=self.project)

        self.app_slug = "dashapp"

        self.app = Apps.objects.create(
            name="Create App Test",
            slug=self.app_slug,
            user_can_delete=False,
        )

    def test_create_instance_from_form_valid_input(self):
        # Create the form data
        data = {
            "name": "test-app-form-name",
            "description": "app-form-description",
            "flavor": str(self.flavor.pk),
            "access": "public",
            "port": 8000,
            "image": "some-image",
            "source_code_url": "https://someurlthatdoesnotexist.com",
        }

        _, form_class = APP_REGISTRY.get(self.app_slug)
        form = form_class(data, project_pk=self.project.pk)

        self.assertTrue(form.is_valid(), f"The form should be valid but has errors: {form.errors}")

        with patch("apps.tasks.deploy_resource.delay") as mock_task:
            id = create_instance_from_form(form, self.project, self.app_slug, app_id=None)

            self.assertIsNotNone(id)
            self.assertTrue(id > 0)

            # Get app instance and verify the status codes
            app_instance = DashInstance.objects.get(pk=id)

            # Validate app instance properties
            self.assertIsNotNone(app_instance)
            self.assertEqual(app_instance.latest_user_action, "Creating")
            self.assertIsNone(app_instance.k8s_user_app_status)
            self.assertEqual(app_instance.name, data.get("name"))
            self.assertEqual(app_instance.description, data.get("description"))
            self.assertEqual(app_instance.access, data.get("access"))
            self.assertEqual(app_instance.port, data.get("port"))
            self.assertEqual(app_instance.image, data.get("image"))
            self.assertEqual(app_instance.source_code_url, data.get("source_code_url"))

            self.assertIsNotNone(app_instance.subdomain)
            subdomain_name = app_instance.subdomain.subdomain
            self.assertIsNotNone(subdomain_name)
            # Example subdomain name pattern: rd5d576b4
            self.assertTrue(
                subdomain_name.startswith("r"), f"The subdomain should begin with r but was {subdomain_name}"
            )

            mock_task.assert_called_once()


class UpdateExistingAppInstanceTestCase(TestCase):
    """
    Test case for helper function create_instance_from_form
    using an existing user app instance.
    """

    def setUp(self) -> None:
        self.user = User.objects.create_user("foo1", "foo@test.com", "bar")
        self.project = Project.objects.create_project(name="test-app-updating", owner=self.user, description="")
        self.flavor = Flavor.objects.create(name="flavor", project=self.project)

        self.app_slug = "dashapp"

        self.app = Apps.objects.create(
            name="Update App Test",
            slug=self.app_slug,
            user_can_delete=False,
        )

        self.subdomain_name = "test-subdomain"
        subdomain = Subdomain.objects.create(subdomain=self.subdomain_name)

        k8s_user_app_status = K8sUserAppStatus.objects.create()
        self.app_instance = DashInstance.objects.create(
            access="public",
            owner=self.user,
            name="test-app-name-original",
            app=self.app,
            project=self.project,
            subdomain=subdomain,
            k8s_user_app_status=k8s_user_app_status,
        )

        self.assertIsNotNone(self.app_instance.id)
        self.assertTrue(self.app_instance.id > 0)
        self.assertIsNotNone(self.app_instance.subdomain)
        self.assertIsNotNone(self.app_instance.subdomain.subdomain)

    def test_update_instance_from_form_modify_port_should_redeploy(self):
        """
        Test function create_instance_from_form to update an existing app instance
        to modify properties that should result in a re-deployment.
        """

        # Create the form data
        # TODO: Need to investigate subdomain. Does it always need to be included?
        # If included and the same, then get Subdomain already exists. Please choose another one.
        data = {
            "name": "test-app-name-new",
            "description": "app-form-description",
            "access": "public",
            "port": 9999,
            "image": "some-image",
            "source_code_url": "https://someurlthatdoesnotexist.com",
        }

        _, form_class = APP_REGISTRY.get(self.app_slug)
        form = form_class(data, project_pk=self.project.pk)

        self.assertTrue(form.is_valid(), f"The form should be valid but has errors: {form.errors}")

        with patch("apps.tasks.deploy_resource.delay") as mock_task:
            id = create_instance_from_form(form, self.project, self.app_slug, app_id=self.app_instance.id)

            self.assertIsNotNone(id)
            self.assertTrue(id > 0)

            # Get app instance and verify the status codes
            app_instance = DashInstance.objects.get(pk=id)

            # Validate app instance properties
            self.assertIsNotNone(app_instance)
            self.assertEqual(app_instance.latest_user_action, "Changing")
            self.assertIsNone(app_instance.k8s_user_app_status)
            self.assertEqual(app_instance.name, data.get("name"))
            self.assertEqual(app_instance.description, data.get("description"))
            self.assertEqual(app_instance.access, data.get("access"))
            self.assertEqual(app_instance.port, data.get("port"))
            self.assertEqual(app_instance.image, data.get("image"))
            self.assertEqual(app_instance.source_code_url, data.get("source_code_url"))

            mock_task.assert_called_once()

    def test_update_instance_from_form_modify_image_should_redeploy(self):
        """
        Test function create_instance_from_form to update an existing app instance
        to modify properties that should result in a re-deployment.
        """

        pass

    def test_update_instance_from_form_modify_subdomain_should_redeploy(self):
        """
        Test function create_instance_from_form to update an existing app instance
        to modify properties that should result in a re-deployment.
        """

        # is_created_by_user = False
        # subdomain = SubdomainTuple(self.subdomain_name, is_created_by_user)

        pass

    def test_update_instance_from_form_modify_no_redeploy_values(self):
        """
        Test function create_instance_from_form to update an existing app instance
        to modify only properties that do not result in a re-deployment.
        """

        # TODO:
        pass

        # mock_task.assert_ not called


@pytest.mark.django_db
def test_get_subdomain_name():
    """Test function get_subdomain_name using form data with a subdomain."""

    expected_subomain_name = "test-subdomain"
    is_created_by_user = False
    subdomain = SubdomainTuple(expected_subomain_name, is_created_by_user)

    data = {
        "name": "app-form-name",
        "description": "app-form-description",
        "access": "public",
        "port": 9999,
        "image": "some-image",
        "source_code_url": "https://someurlthatdoesnotexist.com",
        "subdomain": subdomain,
    }

    _, form_class = APP_REGISTRY.get("dashapp")
    form = form_class(data)

    assert form.is_valid(), f"The form should be valid but has errors: {form.errors}"

    subdomain_name, is_created_by_user = get_subdomain_name(form)

    assert (
        subdomain_name == expected_subomain_name
    ), f"The determined subdomain name {subdomain_name} should equal \
        the expected name {expected_subomain_name}"

    # The function overrides the input is_created_by_user setting it to True
    # because the user specified the subdomain.
    assert is_created_by_user is True, f"is_created_by_user should be True but was {is_created_by_user}"


@pytest.mark.django_db
def test_get_subdomain_name_no_subdomain_in_form():
    """Test function get_subdomain_name using form data without subdomain."""

    data = {
        "name": "app-form-name",
        "description": "app-form-description",
        "access": "public",
        "port": 9999,
        "image": "some-image",
        "source_code_url": "https://someurlthatdoesnotexist.com",
    }

    _, form_class = APP_REGISTRY.get("dashapp")
    form = form_class(data)

    assert form.is_valid(), f"The form should be valid but has errors: {form.errors}"

    subdomain_name, is_created_by_user = get_subdomain_name(form)

    # The get_subdomain_name function sets a random release name if not specified by the user
    assert subdomain_name is not None, "The subdomain should not be None"
    # Example subdomain name pattern: rd5d576b4
    assert subdomain_name.startswith("r"), f"The subdomain should begin with r but was {subdomain_name}"
    assert is_created_by_user is False, f"is_created_by_user should be False but was {is_created_by_user}"
