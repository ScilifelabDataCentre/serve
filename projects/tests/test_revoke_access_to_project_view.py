from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from guardian.shortcuts import assign_perm

from projects.models import Project

User = get_user_model()

test_user_1 = {"username": "foo1", "email": "foo@test.com", "password": "bar"}

test_user_2 = {"username": "foo2", "email": "foo2@test.com", "password": "bar"}

test_user_3 = {"username": "foo3", "email": "foo3@test.com", "password": "bar"}


class RevokeAccessToProjectViewTestCase(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(test_user_1["username"], test_user_1["email"], test_user_1["password"])
        self.user2 = User.objects.create_user(test_user_2["username"], test_user_2["email"], test_user_2["password"])
        self.user3 = User.objects.create_user(test_user_3["username"], test_user_3["email"], test_user_3["password"])
        self.client = Client()

    def get_data(self, user=None):
        project = Project.objects.create_project(
            name="test-perm", owner=user if user is not None else self.user, description=""
        )

        project.authorized.add(self.user2)

        assign_perm("can_view_project", self.user2, project)

        return project

    def test_revoke_access_to_user(self):
        response = self.client.post(
            "/accounts/login/", {"username": test_user_1["email"], "password": test_user_1["password"]}
        )
        response.status_code

        self.assertEqual(response.status_code, 302)

        project = self.get_data()

        response = self.client.post(
            f"/{project.slug}/project/access/revoke/",
            {"selected_user": test_user_2["email"]},
        )

        self.assertEqual(response.status_code, 302)

        project = Project.objects.get(name="test-perm")

        authorized = project.authorized.all()

        self.assertEqual(len(authorized), 0)

        self.user2 = User.objects.get(username=test_user_2["email"])

        has_perm = self.user2.has_perm("can_view_project", project)

        self.assertFalse(has_perm)

    def test_revoke_access_non_existing_user(self):
        response = self.client.post(
            "/accounts/login/", {"username": test_user_1["email"], "password": test_user_1["password"]}
        )
        response.status_code

        self.assertEqual(response.status_code, 302)

        project = self.get_data()

        response = self.client.post(
            f"/{project.slug}/project/access/revoke/",
            {"selected_user": "non_existing_user"},
        )

        self.assertEqual(response.status_code, 400)

    def test_revoke_access_user_no_access_to_project(self):
        response = self.client.post(
            "/accounts/login/", {"username": test_user_1["email"], "password": test_user_1["password"]}
        )
        response.status_code

        self.assertEqual(response.status_code, 302)

        project = self.get_data()

        response = self.client.post(
            f"/{project.slug}/project/access/revoke/",
            {"selected_user": test_user_3["email"]},
        )

        self.assertEqual(response.status_code, 400)

    def test_revoke_access_can_not_remove_if_not_owner(self):
        response = self.client.post(
            "/accounts/login/", {"username": test_user_2["email"], "password": test_user_2["password"]}
        )
        response.status_code

        self.assertEqual(response.status_code, 302)

        project = self.get_data()

        project.authorized.add(self.user3)

        response = self.client.post(
            f"/{project.slug}/project/access/revoke/",
            {"selected_user": test_user_3["email"]},
        )

        self.assertEqual(response.status_code, 400)
