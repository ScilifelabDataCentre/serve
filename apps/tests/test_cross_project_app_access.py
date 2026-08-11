"""Tests that the app views under /projects/<project>/apps/ scope app lookups to the project.

Each test calls an endpoint under a project the logged-in user owns, but passes the id of an
app belonging to another user's project, and asserts the app is treated as non-existent. One
test covers the same endpoint with an app from the user's own project to confirm it still
resolves.
"""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from projects.models import Project

from ..models import (
    AppCategories,
    Apps,
    BackgroundTask,
    JupyterInstance,
    K8sUserAppStatus,
    Subdomain,
)

User = get_user_model()

user_1 = {"username": "user1@test.com", "email": "user1@test.com", "password": "bar"}
user_2 = {"username": "user2@test.com", "email": "user2@test.com", "password": "bar"}


class CrossProjectAppAccessTestCase(TestCase):
    """User 1 must not reach apps that live in user 2's project."""

    def setUp(self) -> None:
        self.user_1 = User.objects.create_user(user_1["username"], user_1["email"], user_1["password"])
        self.user_2 = User.objects.create_user(user_2["username"], user_2["email"], user_2["password"])

        self.category = AppCategories.objects.create(name="Network", priority=100, slug="network")
        self.app = Apps.objects.create(
            name="Jupyter Lab",
            slug="jupyter-lab",
            user_can_delete=True,
            category=self.category,
        )

        # User 1 owns a project of their own, so they pass the permission check on the
        # project slug in the URL.
        self.project_1 = Project.objects.create_project(name="project-one", owner=self.user_1, description="")
        self.project_2 = Project.objects.create_project(name="project-two", owner=self.user_2, description="")

        self.app_2 = JupyterInstance.objects.create(
            access="private",
            owner=self.user_2,
            name="app_in_project_two",
            app=self.app,
            project=self.project_2,
            subdomain=Subdomain.objects.create(subdomain="project_two_internal"),
            k8s_user_app_status=K8sUserAppStatus.objects.create(),
        )

        self.client = Client()
        logged_in = self.client.login(username=user_1["email"], password=user_1["password"])
        self.assertTrue(logged_in)

    def url(self, path):
        """Build a URL under user 1's own project."""
        return f"/projects/{self.project_1.slug}/apps/{path}"

    def test_status_does_not_leak_apps_from_other_projects(self):
        response = self.client.post(self.url("status"), {"apps": [self.app_2.id]})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {})

    def test_status_still_returns_apps_in_own_project(self):
        app_1 = JupyterInstance.objects.create(
            access="private",
            owner=self.user_1,
            name="app_in_project_one",
            app=self.app,
            project=self.project_1,
            subdomain=Subdomain.objects.create(subdomain="project_one_internal"),
            k8s_user_app_status=K8sUserAppStatus.objects.create(),
        )

        response = self.client.post(self.url("status"), {"apps": [app_1.id]})

        self.assertEqual(response.status_code, 200)
        self.assertIn(f"{self.app.slug}-{app_1.pk}", response.json())

    def test_logs_page_from_other_project_is_not_found(self):
        response = self.client.get(self.url(f"logs/{self.app.slug}/{self.app_2.id}"))

        self.assertEqual(response.status_code, 404)

    def test_logs_query_from_other_project_is_not_found(self):
        response = self.client.post(self.url(f"logs/{self.app.slug}/{self.app_2.id}"), {"container": ""})

        self.assertEqual(response.status_code, 404)

    def test_delete_from_other_project_is_forbidden(self):
        with patch("apps.tasks.delete_resource.delay") as mock_task:
            response = self.client.get(self.url(f"delete/{self.app.slug}/{self.app_2.id}"))

        self.assertEqual(response.status_code, 403)
        mock_task.assert_not_called()

        self.app_2.refresh_from_db()
        self.assertIsNone(self.app_2.deleted_on)

    def test_secrets_from_other_project_is_not_found(self):
        response = self.client.get(self.url(f"secrets/{self.app.slug}/{self.app_2.id}"))

        self.assertEqual(response.status_code, 404)

    def test_retry_background_task_from_other_project_is_not_found(self):
        task = BackgroundTask.objects.create(
            app_instance=self.app_2,
            task_name="deploy_resource",
            status="failed",
        )

        with patch("apps.tasks.retry_background_task.delay") as mock_task:
            response = self.client.post(self.url(f"tasks/{self.app.slug}/{self.app_2.id}/{task.id}/retry"))

        self.assertEqual(response.status_code, 404)
        mock_task.assert_not_called()
