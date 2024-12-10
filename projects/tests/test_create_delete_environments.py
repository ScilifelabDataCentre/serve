from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.test import TestCase

from apps.models import Apps, JupyterInstance, Subdomain
from projects.models import Environment, Project
from projects.views import can_model_instance_be_deleted

User = get_user_model()

TEST_USER = {"username": "foo1", "email": "foo@test.com", "password": "bar"}
TEST_SUPERUSER = {"username": "superuser", "email": "superuser@test.com", "password": "bar"}


class EnvironmentTestCaseRegularUser(TestCase):
    def setUp(self):
        user = User.objects.create_user(TEST_USER["username"], TEST_USER["email"], TEST_USER["password"])
        self.project = Project.objects.create_project(name="test-env", owner=user, description="")
        User.objects.create_superuser(TEST_SUPERUSER["username"], TEST_SUPERUSER["email"], TEST_SUPERUSER["password"])
        self.app = Apps.objects.create(name="Some App", slug="someapp")
        self.env_to_be_deleted = Environment.objects.create(
            app=self.app, name="env-to-be-deleted", project=self.project
        )
        self.client.login(username=TEST_USER["email"], password=TEST_USER["password"])

    def test_environment_creation_regular_user(self):
        """
        Test regular user not allowed to create environment
        """
        n_envs_before = Environment.objects.count()
        response = self.client.post(
            f"/projects/{self.project.slug}/createenvironment/",
            {
                "environment_name": "new-env-user",
                "environment_repository": "n",
                "environment_image": "n",
                "environment_app": "n",
                "app": self.app.pk,
            },
        )
        self.assertEqual(response.status_code, 403)
        n_envs_after = Environment.objects.count()
        self.assertEqual(n_envs_before, n_envs_after)

    def test_environment_deletion_regular_user(self):
        """
        Test regular user not allowed to delete environment
        """
        n_envs_before = Environment.objects.count()
        response = self.client.post(
            f"/projects/{self.project.slug}/deleteenvironment/", {"environment_pk": self.env_to_be_deleted.pk}
        )
        self.assertEqual(response.status_code, 403)
        n_envs_after = Environment.objects.count()
        self.assertEqual(n_envs_before, n_envs_after)


class EnvironmentTestCaseSuperUser(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(TEST_USER["username"], TEST_USER["email"], TEST_USER["password"])
        self.project = Project.objects.create_project(name="test-env", owner=self.user, description="")
        User.objects.create_superuser(TEST_SUPERUSER["username"], TEST_SUPERUSER["email"], TEST_SUPERUSER["password"])
        self.app = Apps.objects.create(name="Some App", slug="someapp")
        self.env_to_be_deleted = Environment.objects.create(
            app=self.app, name="env-to-be-deleted", project=self.project
        )
        self.client.login(username=TEST_SUPERUSER["email"], password=TEST_SUPERUSER["password"])

    def test_environment_creation_superuser(self):
        """
        Test superuser is allowed to create environment
        """
        n_envs_before = Environment.objects.count()
        response = self.client.post(
            f"/projects/{self.project.slug}/createenvironment/",
            {
                "environment_name": "new-env-superuser",
                "environment_repository": "n",
                "environment_image": "n",
                "environment_app": self.app.pk,
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        n_envs_after = Environment.objects.count()
        self.assertEqual(n_envs_before + 1, n_envs_after)

    def test_environment_deletion_inuse_superuser(self):
        """
        Test it is not allowed to delete environment that is in use
        """
        env_cannot_be_deleted = Environment.objects.create(
            app=self.app, name="env-cannot-be-deleted", project=self.project
        )
        subdomain = Subdomain.objects.create(subdomain="test_internal")
        self.app_instance = JupyterInstance.objects.create(
            access="public",
            owner=self.user,
            name="test_app_instance_env",
            app=self.app,
            project=self.project,
            environment=env_cannot_be_deleted,
            subdomain=subdomain,
        )
        can_env_be_deleted = can_model_instance_be_deleted("environment", env_cannot_be_deleted)
        self.assertFalse(can_env_be_deleted)

        n_envs_before = Environment.objects.count()
        response = self.client.post(
            f"/projects/{self.project.slug}/deleteenvironment/",
            {"environment_pk": env_cannot_be_deleted.pk},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        messages = list(get_messages(response.wsgi_request))
        self.assertEqual(len(messages), 1)
        self.assertIn("cannot be deleted", str(messages[0]))
        n_envs_after = Environment.objects.count()

        self.assertEqual(n_envs_before, n_envs_after)

    def test_environment_deletion_notinuse_superuser(self):
        """
        Test it is allowed to delete environment that is not in use
        """
        can_env_be_deleted = can_model_instance_be_deleted("environment", self.env_to_be_deleted)
        self.assertTrue(can_env_be_deleted)
        n_envs_before = Environment.objects.count()
        response = self.client.post(
            f"/projects/{self.project.slug}/deleteenvironment/",
            {"environment_pk": self.env_to_be_deleted.pk},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        n_envs_after = Environment.objects.count()

        self.assertEqual(n_envs_before - 1, n_envs_after)
