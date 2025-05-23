"""This module is used to test the helper functions that are used by user app instance functionality."""

import json
from unittest.mock import ANY, patch

import pytest
from django.contrib.auth import get_user_model
from django.test import TestCase

from common.tests.manage_test_data import TestDataManager
from projects.models import Flavor, Project

from ..app_registry import APP_REGISTRY
from ..constants import AppActionOrigin
from ..forms import DashForm
from ..helpers import (
    create_instance_from_form,
    generate_schema_org_description,
    get_subdomain_name,
)
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

            # Get app instance and verify the instance properties including status codes
            app_instance = DashInstance.objects.get(pk=id)

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
            self.assertFalse(app_instance.subdomain.is_created_by_user)

            mock_task.assert_called_once()


# Mock the tasks that manipulate k8s resources.
# Note that these are passed to the test functions in reverse order.
# The delete_resource task is used sync (without delay) in helpers.
@patch("apps.tasks.deploy_resource.delay")
@patch("apps.tasks.delete_resource")
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

        # Define the original values
        self.name = "test-app-name-original"
        self.description = "app-form-description"
        self.port = 8000
        self.image = "test-image-orig"
        self.subdomain_name = "test-subdomain-update-app"
        self.source_code_url = "https://someurlthatdoesnotexist.com"

        is_created_by_user = True
        subdomain = Subdomain.objects.create(
            subdomain=self.subdomain_name, project=self.project, is_created_by_user=is_created_by_user
        )

        k8s_user_app_status = K8sUserAppStatus.objects.create()

        self.app_instance = DashInstance.objects.create(
            app=self.app,
            access="public",
            owner=self.user,
            name=self.name,
            description=self.description,
            port=self.port,
            image=self.image,
            source_code_url=self.source_code_url,
            project=self.project,
            subdomain=subdomain,
            k8s_user_app_status=k8s_user_app_status,
        )

        self.assertIsNotNone(self.app_instance.id)
        self.assertTrue(self.app_instance.id > 0)
        self.assertIsNotNone(self.app_instance.subdomain)
        self.assertIsNotNone(self.app_instance.subdomain.subdomain)
        self.assertEqual(self.app_instance.subdomain.subdomain, self.subdomain_name)
        self.assertTrue(self.app_instance.subdomain.is_created_by_user)

    def test_update_instance_from_form_modify_port_should_redeploy(self, mock_delete, mock_deploy):
        """
        Test function create_instance_from_form to update an existing app instance
        to modify properties that should result in a re-deployment.
        The modified property in this test is the Port.
        """

        # Create the form data
        # Fields requiring special consideration: tags, volume, subdomain
        # In the below data dict, we modify the app port:
        data = {
            "name": self.name,
            "description": self.description,
            "access": "public",
            "port": 9999,
            "image": self.image,
            "source_code_url": self.source_code_url,
            "subdomain": self.subdomain_name,
        }

        changed_fields = ["port"]

        # Apply the form and validate the result
        self._verify_update_instance_from_form(data, changed_fields)

        # Modifying the port should cause a re-deploy:
        mock_deploy.assert_called_once()
        # Not modifying the subdomain should not cause a delete:
        mock_delete.assert_not_called()

    def test_update_instance_from_form_modify_image_should_redeploy(self, mock_delete, mock_deploy):
        """
        Test function create_instance_from_form to update an existing app instance
        to modify properties that should result in a re-deployment.
        The modified property in this test is the Image.
        """

        # Create the form data
        # Fields requiring special consideration: tags, volume, subdomain
        # In the below data dict, we modify the app image:
        data = {
            "name": self.name,
            "description": self.description,
            "access": "public",
            "port": self.port,
            "image": "test-image-new",
            "source_code_url": self.source_code_url,
            "subdomain": self.subdomain_name,
        }

        changed_fields = ["image"]

        # Apply the form and validate the result
        self._verify_update_instance_from_form(data, changed_fields)

        # Modifying the image should cause a re-deploy:
        mock_deploy.assert_called_once()
        # Not modifying the subdomain should not cause a delete:
        mock_delete.assert_not_called()

    def test_update_instance_from_form_modify_subdomain_should_redeploy(self, mock_delete, mock_deploy):
        """
        Test function create_instance_from_form to update an existing app instance
        to modify properties that should result in a re-deployment.
        The modified property in this test is the Subdomain.
        Modifying the subdomain also results in a delete resource call.
        """

        # Create the form data
        # Fields requiring special consideration: tags, volume, subdomain
        # In the below data dict, we modify the app subdomain:
        data = {
            "name": self.name,
            "description": self.description,
            "access": "public",
            "port": self.port,
            "image": self.image,
            "source_code_url": self.source_code_url,
            "subdomain": "test-subdomain-update-app-new",
        }

        changed_fields = ["subdomain"]

        # Apply the form and validate the result
        self._verify_update_instance_from_form(data, changed_fields)

        # Modifying the subdomain should cause a re-deploy:
        mock_deploy.assert_called_once()
        # Modifying the subdomain SHOULD cause a delete:
        mock_delete.assert_called_once_with(ANY, AppActionOrigin.USER.value)

    def test_update_instance_from_form_modify_no_redeploy_values(self, mock_delete, mock_deploy):
        """
        Test function create_instance_from_form to update an existing app instance
        to modify only properties that should NOT result in a re-deployment.
        """

        f = DashForm()
        self.assertIsNotNone(f)

        model_class, form_class = APP_REGISTRY.get(self.app_slug)

        instance = model_class.objects.get(pk=self.app_instance.id)
        self.assertIsNotNone(instance)
        self.assertIsInstance(instance, DashInstance)

        # Create the form data
        # Fields requiring special consideration: tags, volume, subdomain
        # In the below data dict, we modify only properties that do not lead to re-deployment:
        data = {
            "name": "test-app-name-new",
            "description": "app-form-description-new",
            "access": "public",
            "port": self.port,
            "image": self.image,
            "source_code_url": "https://someurlthatdoesnotexist.com/new",
            "subdomain": self.subdomain_name,
            "tags": None,
        }

        changed_fields = ["name", "description", "source_code_url"]

        # Apply the form and validate the result
        self._verify_update_instance_from_form(data, changed_fields)

        # Not modifying any re-deployment fields should NOT cause a re-deploy:
        mock_deploy.assert_not_called()
        # Not modifying the subdomain should not cause a delete:
        mock_delete.assert_not_called()

    def _verify_update_instance_from_form(self, data: dict, changed_fields: list[str]) -> None:
        """Helper function to verify the result of the create_instance_from_form function tests."""

        f = DashForm()
        self.assertIsNotNone(f)

        model_class, form_class = APP_REGISTRY.get(self.app_slug)

        instance = model_class.objects.get(pk=self.app_instance.id)
        self.assertIsNotNone(instance)
        self.assertIsInstance(instance, DashInstance)

        # Perform the form validation and tests using an existing app instance
        form = form_class(data, project_pk=self.project.pk, instance=instance)

        self.assertTrue(form.is_valid(), f"The form should be valid but has errors: {form.errors}")

        self.assertIsNotNone(form.changed_data)
        self.assertEqual(form.changed_data, changed_fields)

        id = create_instance_from_form(form, self.project, self.app_slug, app_id=self.app_instance.id)

        self.assertIsNotNone(id)
        self.assertTrue(id > 0)

        # Get app instance and verify the instance properties including status codes
        app_instance = DashInstance.objects.get(pk=id)

        self.assertIsNotNone(app_instance)
        self.assertEqual(app_instance.latest_user_action, "Changing")
        self.assertIsNotNone(app_instance.k8s_user_app_status)
        self.assertIsNone(app_instance.k8s_user_app_status.status)
        self.assertEqual(app_instance.name, data.get("name"))
        self.assertEqual(app_instance.description, data.get("description"))
        self.assertEqual(app_instance.access, data.get("access"))
        self.assertEqual(app_instance.port, data.get("port"))
        self.assertEqual(app_instance.image, data.get("image"))
        self.assertEqual(app_instance.source_code_url, data.get("source_code_url"))

        # Verify the subdomain. Determine from the data dict.
        self.assertIsNotNone(app_instance.subdomain)
        self.assertIsNotNone(app_instance.subdomain.subdomain)

        expected_subdomain_name = data.get("subdomain", None)
        if expected_subdomain_name is None:
            # The subdomain was not changed from the original
            expected_subdomain_name = self.subdomain_name

        self.assertEqual(app_instance.subdomain.subdomain, expected_subdomain_name)
        self.assertTrue(app_instance.subdomain.is_created_by_user)


@pytest.mark.django_db
def test_get_subdomain_name():
    """Test function get_subdomain_name using form data with a subdomain."""

    expected_subdomain_name = "test-subdomain-get-from-form"
    is_created_by_user = True
    subdomain = SubdomainTuple(expected_subdomain_name, is_created_by_user)

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
        subdomain_name == expected_subdomain_name
    ), f"The determined subdomain name {subdomain_name} should equal \
        the expected name {expected_subdomain_name}"

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


@pytest.mark.django_db
def test_schema_org_description():
    user_data = {
        "affiliation": "uu",
        "department": "unit_test_schema_org_description_user_department_name",
        "email": "unit_test_schema_org_description_user_email@scilifelab.uu.se",
        "first_name": "unit_test_schema_org_description_user_first_name",
        "last_name": "unit_test_schema_org_description_user_last_name",
        "username": "unit_test_schema_org_description_user_name",
        "password": "tesT12345@",
    }

    project_data = {
        "project_name": "unit_test_schema_org_description_project_name",
        "project_description": "unit_test_schema_org_description_project_description",
    }

    manager = TestDataManager(user_data=user_data)
    user = manager.create_user()
    project = Project.objects.create_project(
        name=project_data["project_name"], owner=user, description=project_data["project_description"]
    )
    app = Apps.objects.create(
        name="Unit test schema org description app type", slug="unit_test_schema_org_description_slug"
    )
    subdomain = Subdomain.objects.create(subdomain="unit_test_schema_org_description_subdomain")
    k8s_user_app_status = K8sUserAppStatus.objects.create()
    app_instance = DashInstance.objects.create(
        access="private",
        owner=user,
        name="unit_test_schema_org_description_app_name",
        description="unit_test_schema_org_description_app_description",
        port=8000,
        image="ghcr.io/scilifelabdatacentre/example-dash:latest",
        source_code_url="https://someurlthatdoesnotexist.com",
        app=app,
        project=project,
        subdomain=subdomain,
        k8s_user_app_status=k8s_user_app_status,
    )

    schema_description = generate_schema_org_description(app_instance)
    schema_dict = json.loads(schema_description)

    # Check 'hasPart' entries
    has_part = schema_dict["hasPart"]
    assert len(has_part) == 3, "'hasPart' does not have three entries"

    # Application assertions
    software_app = next(item for item in has_part if item["@type"] == "SoftwareApplication")
    assert (
        software_app["name"] == "unit_test_schema_org_description_app_name"
    ), f"App name '{software_app['name']}' should match 'unit_test_schema_org_description_app_name'"

    assert software_app["author"] == {
        "@type": "Person",
        "name": f"{user_data['first_name']} {user_data['last_name']}",
        "email": user_data["email"],
    }, f"Author info mismatch, type should be 'Person', name should be \
            '{user_data['first_name']} {user_data['last_name']}' email should be \
                '{user_data['last_name']}'"

    # Person assertions
    person = next(item for item in has_part if item["@type"] == "Person")
    assert (
        person["name"] == f"{user_data['first_name']} {user_data['last_name']}"
    ), f"person  \
        name '{user_data['last_name']}' should match {user_data['first_name']} {user_data['last_name']}"
    assert (
        person["email"] == user_data["email"]
    ), f"person email '{person['email']}' should match '{user_data['email']}'"
    assert person["memberOf"] == {
        "@type": "Project",
        "name": project_data["project_name"],
    }, f"Person's project type should match 'Project' and \
            project name should match '{project_data['project_name']}'"

    # Project assertions
    project_entry = next(item for item in has_part if item["@type"] == "Project")
    assert (
        project_entry["name"] == project_data["project_name"]
    ), f"project name \
        '{project_entry['name']}' should match '{project_data['project_name']}'"
    assert (
        project_entry["description"] == project_data["project_description"]
    ), f"project description\
        '{project_entry['description']}' should match '{project_data['project_description']}'"
