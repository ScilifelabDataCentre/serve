"""Claiming a subdomain must reuse an existing row rather than attempt a duplicate insert."""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.app_registry import APP_REGISTRY
from apps.helpers import create_instance_from_form
from projects.models import Project

from ..models import Apps, K8sUserAppStatus, Subdomain
from ..models.app_types.dash import DashInstance

User = get_user_model()

DELETE_RESOURCE_OK = {"success": True, "release_missing": False, "error": None}


@patch("apps.tasks.run_background_tasks.delay")
@patch("apps.tasks.delete_resource")
class ClaimSubdomainWithMismatchedRowTestCase(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user("foo1", "foo@test.com", "bar")
        self.project = Project.objects.create_project(name="test-subdomain-claim", owner=self.user, description="")
        self.app_slug = "dashapp"
        self.app = Apps.objects.create(name="Dash App", slug=self.app_slug, user_can_delete=False)

        self.subdomain_name = "test-app-subdomain"
        self.instance = DashInstance.objects.create(
            app=self.app,
            access="public",
            owner=self.user,
            name="test-app",
            description="description",
            port=8000,
            image="mock.io/test-image",
            source_code_url="https://someurlthatdoesnotexist.com",
            project=self.project,
            subdomain=Subdomain.objects.create(
                subdomain=self.subdomain_name, project=self.project, is_created_by_user=True
            ),
            k8s_user_app_status=K8sUserAppStatus.objects.create(),
        )

    def _save_with_subdomain(self, subdomain_name):
        data = {
            "name": "test-app",
            "description": "description",
            "access": "public",
            "port": 8000,
            "image": "mock.io/test-image",
            "source_code_url": "https://someurlthatdoesnotexist.com",
            "subdomain": subdomain_name,
            "invenio_tags": "Antibodies|Cells",
            "creators": '[{"name": "Test", "lastName": "User", "affiliation": "", "orcid": "", "order": 0}]',
        }

        model_class, form_class = APP_REGISTRY.get(self.app_slug)
        instance = model_class.objects.get(pk=self.instance.pk)
        form = form_class(data, project_pk=self.project.pk, instance=instance)
        self.assertTrue(form.is_valid(), f"The form should be valid but has errors: {form.errors}")

        with self.captureOnCommitCallbacks(execute=True):
            create_instance_from_form(form, self.project, self.app_slug, app_id=self.instance.pk)

    def test_saving_an_app_whose_row_has_no_project(self, mock_delete, mock_deploy):
        """Subdomain.project is nullable, so a row without one must not break the app's save."""
        Subdomain.objects.filter(pk=self.instance.subdomain.pk).update(project=None)

        self._save_with_subdomain(self.subdomain_name)

        self.assertEqual(Subdomain.objects.filter(subdomain=self.subdomain_name).count(), 1)

    def test_claiming_a_free_row_flagged_as_auto_generated(self, mock_delete, mock_deploy):
        """Migration 0006 backfilled is_created_by_user=False onto names users had chosen."""
        mock_delete.return_value = DELETE_RESOURCE_OK
        Subdomain.objects.create(subdomain="test-free-name", project=self.project, is_created_by_user=False)

        self._save_with_subdomain("test-free-name")

        self.assertEqual(Subdomain.objects.filter(subdomain="test-free-name").count(), 1)
        self.instance.refresh_from_db()
        self.assertEqual(self.instance.subdomain.subdomain, "test-free-name")
