from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from projects.models import Project

from ..models import AppCategories, CustomAppInstance, Apps,Subdomain, AppStatus

User = get_user_model()

test_user = {"username": "foo1", "email": "foo@test.com", "password": "bar"}


class AppSettingsViewTestCase(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(test_user["username"], test_user["email"], test_user["password"])
        self.category = AppCategories.objects.create(name="Network", priority=100, slug="network")
        self.app = Apps.objects.create(
            name="My Custom App",
            slug="customapp",
            user_can_edit=False,
            category=self.category,
        )

        self.project = Project.objects.create_project(name="test-perm", owner=self.user, description="")


        subdomain = Subdomain.objects.create(subdomain="test_internal")
        app_status = AppStatus.objects.create(status="Created")
        self.app_instance = CustomAppInstance.objects.create(
            access="public",
            owner=self.user,
            name="test_app_instance_public",
            app=self.app,
            project=self.project,
            subdomain=subdomain,
            app_status = app_status,
            k8s_values={
                "environment": {"pk": ""},
            },
        )

    def get_data(self, user=None):
        project = Project.objects.create_project(
            name="test-perm", owner=user if user is not None else self.user, description=""
        )

        return project

    def test_user_can_edit_true(self):
        c = Client()

        response = c.post("/accounts/login/", {"username": test_user["email"], "password": test_user["password"]})
        response.status_code

        self.assertEqual(response.status_code, 302)

        url = f"/projects/{self.project.slug}/" + f"apps/settings/{self.app_instance.app.slug}/{self.app_instance.id}"

        response = c.get(url)

        self.assertEqual(response.status_code, 403)

    def test_user_can_edit_false(self):
        c = Client()

        response = c.post("/accounts/login/", {"username": test_user["email"], "password": test_user["password"]})
        response.status_code

        self.assertEqual(response.status_code, 302)

        self.app.user_can_edit = True
        self.app.save()

        url = f"/projects/{self.project.slug}/" + f"apps/settings/{self.app_instance.app.slug}/{self.app_instance.id}"

        response = c.get(url)

        self.assertEqual(response.status_code, 200)
