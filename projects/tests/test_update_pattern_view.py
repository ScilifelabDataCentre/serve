from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from projects.models import Project

from ..views import UpdatePatternView

User = get_user_model()

test_user = {
    "username": "foo1",
    "email": "foo@test.com",
    "password": "bar"
}

class UpdatePatternViewTestCase(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(test_user["username"], test_user["email"], test_user["password"])
        self.client = Client()

    def get_data(self, user=None):
        project = Project.objects.create_project(
            name="test-perm",
            owner=user if user is not None else self.user,
            description="",
            repository="",
        )

        return project

    def test_update_pattern_view(self):
        response = self.client.post("/accounts/login/", {"username": test_user["email"], "password": test_user["password"]})
        response.status_code

        self.assertEqual(response.status_code, 302)

        project = self.get_data()

        response = self.client.post(
            f"/{self.user.username}/{project.slug}/pattern/update",
            {"pattern": "pattern-1"},
        )

        self.assertEqual(response.status_code, 200)

        response = self.client.post(
            f"/{self.user.username}/{project.slug}/pattern/update",
            {"pattern": "pattern-0"},
        )

        self.assertEqual(response.status_code, 400)

        user = User.objects.create_user("foo2", "foo2@test.com", "bar2")

        response = self.client.post("/accounts/login/", {"username": "foo2@test.com", "password": "bar2"})
        response.status_code

        self.assertEqual(response.status_code, 302)

        response = self.client.post(
            f"/{user.username}/{project.slug}/pattern/update",
            {"pattern": "pattern-1"},
        )

        self.assertEqual(response.status_code, 403)

    def test_validatte(self):
        view = UpdatePatternView()

        result = view.validate("pattern-1")
        self.assertTrue(result)

        result = view.validate("pattern-2")
        self.assertTrue(result)

        result = view.validate("pattern-12")
        self.assertTrue(result)

        result = view.validate("pattern-0")
        self.assertFalse(result)

        result = view.validate("pattern-13")
        self.assertTrue(result)

        result = view.validate("pattern-30")
        self.assertTrue(result)

        result = view.validate("pattern-31")
        self.assertFalse(result)

        result = view.validate("patter-5")
        self.assertFalse(result)

        result = view.validate("something-very-random")
        self.assertFalse(result)
