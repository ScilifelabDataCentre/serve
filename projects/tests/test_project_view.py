from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from ..models import Project

User = get_user_model()
test_user = {"username": "foo1", "email": "foo@test.com", "password": "bar"}

test_member = {"username": "member", "email": "member@test.com", "password": "bar"}


class ProjectViewTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(test_user["username"], test_user["email"], test_user["password"])
        cls.project_name = "test-title"
        cls.project = Project.objects.create_project(name=cls.project_name, owner=cls.user, description="")

    def setUp(self):
        self.client.login(username=test_user["email"], password=test_user["password"])

    def get_project_page(self, page: str):
        return self.client.get(
            reverse(f"projects:{page}", kwargs={"project_slug": self.project.slug})
        )

    def test_project_overview(self):
        resp = self.get_project_page("details")
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "projects/overview.html")
        assert f"<title>{self.project_name} | SciLifeLab Serve (beta)</title>" in resp.content.decode()


class FrobiddenProjectViewTestCase(TestCase):
    def setUp(self):
        user = User.objects.create_user(test_user["username"], test_user["email"], test_user["password"])
        _ = Project.objects.create_project(name="test-perm", owner=user, description="")
        user = User.objects.create_user(test_member["username"], test_member["email"], test_member["password"])
        self.client.login(username=test_user["email"], password=test_user["password"])

    def test_forbidden_project_details(self):
        """
        Test non-project member not allowed to access project overview
        """
        self.client.login(username=test_member["email"], password=test_member["password"])
        member = User.objects.get(username=test_member["email"])
        project = Project.objects.get(name="test-perm")
        response = self.client.get(
            reverse(
                "projects:details",
                kwargs={"project_slug": project.slug},
            )
        )
        self.assertTemplateUsed(response, "403.html")
        self.assertEqual(response.status_code, 403)

    def test_forbidden_project_settings(self):
        """
        Test non-project member not allowed to access project settings
        """
        self.client.login(username=test_member["email"], password=test_member["password"])
        member = User.objects.get(username=test_member["email"])
        project = Project.objects.get(name="test-perm")
        response = self.client.get(
            reverse(
                "projects:settings",
                kwargs={"project_slug": project.slug},
            )
        )
        self.assertTemplateUsed(response, "403.html")
        self.assertEqual(response.status_code, 403)

    def test_forbidden_project_delete(self):
        """
        Test non-project member not allowed to access project delete
        """
        self.client.login(username=test_member["email"], password=test_member["password"])
        member = User.objects.get(username=test_member["email"])
        project = Project.objects.get(name="test-perm")
        response = self.client.get(
            reverse(
                "projects:delete",
                kwargs={"project_slug": project.slug},
            )
        )
        self.assertTemplateUsed(response, "403.html")
        self.assertEqual(response.status_code, 403)

    def test_forbidden_project_setS3storage(self):
        """
        Test non-project member not allowed to access project setS3storage
        """
        self.client.login(username=test_member["email"], password=test_member["password"])
        member = User.objects.get(username=test_member["email"])
        project = Project.objects.get(name="test-perm")
        response = self.client.get(
            reverse(
                "projects:set_s3storage",
                kwargs={"project_slug": project.slug},
            )
        )
        self.assertTemplateUsed(response, "403.html")
        self.assertEqual(response.status_code, 403)

    def test_forbidden_project_setmlflow(self):
        """
        Test non-project member not allowed to access project setmlflow
        """
        self.client.login(username=test_member["email"], password=test_member["password"])
        member = User.objects.get(username=test_member["email"])
        project = Project.objects.get(name="test-perm")
        response = self.client.get(
            reverse(
                "projects:set_mlflow",
                kwargs={"project_slug": project.slug},
            )
        )
        self.assertTemplateUsed(response, "403.html")
        self.assertEqual(response.status_code, 403)
