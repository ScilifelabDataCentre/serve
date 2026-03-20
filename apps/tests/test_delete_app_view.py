from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from projects.models import Project

from ..models import AppCategories, Apps, JupyterInstance, K8sUserAppStatus, Subdomain

User = get_user_model()

test_user = {"username": "foo1", "email": "foo@test.com", "password": "bar"}


class DeleteAppViewTestCase(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(test_user["username"], test_user["email"], test_user["password"])
        self.category = AppCategories.objects.create(name="Network", priority=100, slug="network")
        self.app = Apps.objects.create(
            name="Jupyter Lab",
            slug="jupyter-lab",
            user_can_delete=False,
            category=self.category,
        )

        self.project = Project.objects.create_project(name="test-perm", owner=self.user, description="")

        subdomain = Subdomain.objects.create(subdomain="test_internal")
        k8s_user_app_status = K8sUserAppStatus.objects.create()

        self.app_instance = JupyterInstance.objects.create(
            access="private",
            owner=self.user,
            name="test_app_instance",
            app=self.app,
            project=self.project,
            subdomain=subdomain,
            k8s_user_app_status=k8s_user_app_status,
        )

    def get_data(self, user=None):
        project = Project.objects.create_project(
            name="test-perm", owner=user if user is not None else self.user, description=""
        )

        return project

    def test_user_can_delete_false(self):
        c = Client()

        response = c.post("/accounts/login/", {"username": test_user["email"], "password": test_user["password"]})
        response.status_code

        self.assertEqual(response.status_code, 302)

        url = f"/projects/{self.project.slug}/apps/delete/" + f"{self.app_instance.app.slug}/{self.app_instance.id}"

        response = c.get(url)

        self.assertEqual(response.status_code, 403)

    def test_user_can_delete_true(self):
        c = Client()

        response = c.post("/accounts/login/", {"username": test_user["email"], "password": test_user["password"]})
        response.status_code

        self.assertEqual(response.status_code, 302)

        self.app.user_can_delete = True
        self.app.save()

        with patch("apps.tasks.delete_resource.delay") as mock_task:
            url = f"/projects/{self.project.slug}/apps/delete/" + f"{self.app_instance.app.slug}/{self.app_instance.id}"

            response = c.get(url)

            self.assertEqual(response.status_code, 302)

            self.app_instance = JupyterInstance.objects.get(name="test_app_instance")

            self.assertEqual("private", self.app_instance.access)
            self.assertIsNotNone(self.app_instance.deleted_on)

            mock_task.assert_called_once()

    def test_public_app_cannot_be_deleted(self):
        """Test that public apps cannot be deleted regardless of user_can_delete setting"""
        c = Client()

        response = c.post("/accounts/login/", {"username": test_user["email"], "password": test_user["password"]})
        self.assertEqual(response.status_code, 302)

        # Create a public app instance for this test
        subdomain = Subdomain.objects.create(subdomain="test_public")
        k8s_user_app_status = K8sUserAppStatus.objects.create()
        
        public_app_instance = JupyterInstance.objects.create(
            access="public",
            owner=self.user,
            name="test_public_app_instance",
            app=self.app,
            project=self.project,
            subdomain=subdomain,
            k8s_user_app_status=k8s_user_app_status,
        )

        # Even with user_can_delete=True, public apps should not be deletable
        self.app.user_can_delete = True
        self.app.save()

        url = f"/projects/{self.project.slug}/apps/delete/" + f"{public_app_instance.app.slug}/{public_app_instance.id}"

        response = c.get(url)

        # Should return 403 Forbidden
        self.assertEqual(response.status_code, 403)
