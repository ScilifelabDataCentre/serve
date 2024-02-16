from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from projects.models import Project

User = get_user_model()

test_user_1 = {"username": "foo1", "email": "foo@test.com", "password": "bar"}

test_user_2 = {"username": "foo2", "email": "foo2@test.com", "password": "bar"}

test_client = {"username": "client1", "email": "foo3@test.com", "password": "bar"}


class GrantAccessToProjectViewTestCase(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(test_user_1["username"], test_user_1["email"], test_user_1["password"])
        self.user2 = User.objects.create_user(test_user_2["username"], test_user_2["email"], test_user_2["password"])
        self.user3 = User.objects.create_user(test_client["username"], test_client["email"], test_client["password"])
        self.client = Client()

    def get_data(self, user=None):
        project = Project.objects.create_project(
            name="test-perm",
            owner=user if user is not None else self.user,
            description="",
        )

        return project

    def test_grant_access_to_user(self):
        response = self.client.post(
            "/accounts/login/", {"username": test_user_1["email"], "password": test_user_1["password"]}
        )
        response.status_code

        self.assertEqual(response.status_code, 302)

        project = self.get_data()

        response = self.client.post(
            f"/{project.slug}/project/access/grant/",
            {"selected_user": test_user_2["email"]},
        )

        self.assertEqual(response.status_code, 302)

        project = Project.objects.get(name="test-perm")

        authorized = project.authorized.all()

        self.assertEqual(len(authorized), 1)

        authorized_user = authorized[0]

        self.assertEqual(authorized_user.id, self.user2.id)

        self.user2 = User.objects.get(username=test_user_2["email"])

        has_perm = self.user2.has_perm("can_view_project", project)

        self.assertTrue(has_perm)

    def test_grant_access_to_user_no_access(self):
        response = self.client.post(
            "/accounts/login/", {"username": test_user_1["email"], "password": test_user_1["password"]}
        )
        response.status_code

        self.assertEqual(response.status_code, 302)

        project = self.get_data(user=self.user2)

        response = self.client.post(
            f"/{project.slug}/project/access/grant/",
            {"selected_user": test_user_2["email"]},
        )

        self.assertEqual(response.status_code, 403)

    def test_grant_access_to_non_existing_user(self):
        response = self.client.post(
            "/accounts/login/", {"username": test_user_1["email"], "password": test_user_1["password"]}
        )
        response.status_code

        self.assertEqual(response.status_code, 302)

        project = self.get_data()

        response = self.client.post(
            f"/{project.slug}/project/access/grant/",
            {"selected_user": "non_existing_user"},
        )

        self.assertEqual(response.status_code, 302)

        project = Project.objects.get(name="test-perm")

        authorized = project.authorized.all()

        self.assertEqual(len(authorized), 0)

    """
    THIS TEST FAILS ON SCALEOUT DUE TO is_client does not exist
    def test_grant_access_to_client(self):
        response = self.client.post(
            "/accounts/login/", {"username": test_user_1["email"], "password": test_user_1["password"]}
        )
        response.status_code

        self.assertEqual(response.status_code, 302)

        project = self.get_data()

        response = self.client.post(
            f"/{self.user.username}/{project.slug}/project/access/grant",
            {"selected_user":test_client["email"]},
        )

        self.assertEqual(response.status_code, 302)

        project = Project.objects.get(name="test-perm")

        authorized = project.authorized.all()

        self.assertEquals(len(authorized), 0)
    """
