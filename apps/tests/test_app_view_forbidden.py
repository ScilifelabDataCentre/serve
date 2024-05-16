from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from projects.models import Project

User = get_user_model()

test_user = {"username": "foo1", "email": "foo@test.com", "password": "bar"}


class AppsViewForbidden(TestCase):
    def setUp(self):
        user = User.objects.create_user(test_user["username"], test_user["email"], test_user["password"])

        _ = Project.objects.create_project(name="test-perm", owner=user, description="")

        user = User.objects.create_user("member", "bar@test.com", "bar")
        self.client.login(username="bar@test.com", password="bar")

    def test_forbidden_apps_create(self):
        """
        Test non-project member not allowed to access /create/<app_slug>=test
        """
        project = Project.objects.get(name="test-perm")
        response = self.client.get(
            reverse(
                "apps:create",
                kwargs={
                    "project": project.slug,
                    "app_slug": "test",
                },
            )
        )
        self.assertTemplateUsed(response, "403.html")
        self.assertEqual(response.status_code, 403)

    def test_forbidden_apps_logs(self):
        """
        Test non-project member not allowed to access /logs/<app_slug>=jupyter-lab/<app_id>=1
        """
        project = Project.objects.get(name="test-perm")
        response = self.client.get(
            reverse(
                "apps:logs",
                kwargs={"project": project.slug, "app_slug": "jupyter-lab", "app_id": "1"},
            )
        )
        self.assertTemplateUsed(response, "403.html")
        self.assertEqual(response.status_code, 403)

    def test_forbidden_apps_settings(self):
        """
        Test non-project member not allowed to access /settings/<app_slug>=jupyter-lab/<app_id>=1
        """
        project = Project.objects.get(name="test-perm")
        response = self.client.get(
            reverse(
                "apps:appsettings",
                kwargs={"project": project.slug, "app_slug": "jupyter-lab", "app_id": "1"}
            )
        )
        self.assertTemplateUsed(response, "403.html")
        self.assertEqual(response.status_code, 403)

