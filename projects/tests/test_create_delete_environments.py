from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.test import TestCase

from apps.models import Apps, JupyterInstance, Subdomain
from projects.models import Environment, Project
from projects.views import can_model_instance_be_deleted

User = get_user_model()

test_user = {"username": "foo1", "email": "foo@test.com", "password": "bar"}
test_superuser = {"username": "superuser", "email": "superuser@test.com", "password": "bar"}


class EnvironmentTestCase(TestCase):
    def setUp(self):
        user = User.objects.create_user(test_user["username"], test_user["email"], test_user["password"])
        project = Project.objects.create_project(name="test-env", owner=user, description="")
        User.objects.create_superuser(test_superuser["username"], test_superuser["email"], test_superuser["password"])
        app = Apps.objects.create(name="Some App", slug="someapp")
        Environment.objects.create(app=app, name="env-to-be-deleted", project=project)

    def test_environment_creation_user(self):
        """
        Test regular user not allowed to create environment
        """
        self.client.login(username=test_user["email"], password=test_user["password"])

        project = Project.objects.get(name="test-env")
        app = Apps.objects.get(slug="someapp")

        n_envs_before = Environment.objects.count()
        response = self.client.post(
            f"/projects/{project.slug}/createenvironment/",
            {
                "environment_name": "new-env-user",
                "environment_repository": "n",
                "environment_image": "n",
                "environment_app": "n",
                "app": app.pk,
            },
        )
        self.assertEqual(response.status_code, 403)
        n_envs_after = Environment.objects.count()

        self.assertEqual(n_envs_before, n_envs_after)

        """
        Test regular user not allowed to delete environment
        """
        env_to_be_deleted = Environment.objects.get(name="env-to-be-deleted")
        n_envs_before = Environment.objects.count()
        response = self.client.post(
            f"/projects/{project.slug}/deleteenvironment/", {"environment_pk": env_to_be_deleted.pk}
        )
        self.assertEqual(response.status_code, 403)
        n_envs_after = Environment.objects.count()
        self.assertEqual(n_envs_before, n_envs_after)

    def test_environment_creation_deletion_superuser(self):
        """
        Test superuser is allowed to create environment
        """
        self.client.login(username=test_superuser["email"], password=test_superuser["password"])
        project = Project.objects.get(name="test-env")
        app = Apps.objects.get(slug="someapp")

        n_envs_before = Environment.objects.count()
        response = self.client.post(
            f"/projects/{project.slug}/createenvironment/",
            {
                "environment_name": "new-env-superuser",
                "environment_repository": "n",
                "environment_image": "n",
                "environment_app": app.pk,
            },
        )
        self.assertEqual(response.status_code, 302)
        n_envs_after = Environment.objects.count()

        self.assertEqual(n_envs_before + 1, n_envs_after)

        """
        Test it is not allowed to delete environment that is in use
        """
        user = User.objects.get(email=test_superuser["email"])
        env = Environment.objects.get(name="new-env-superuser")

        subdomain = Subdomain.objects.create(subdomain="test_internal")
        self.app_instance = JupyterInstance.objects.create(
            access="public",
            owner=user,
            name="test_app_instance_env",
            app=app,
            project=project,
            environment=env,
            subdomain=subdomain,
        )

        can_env_be_deleted = can_model_instance_be_deleted("environment", env)
        self.assertFalse(can_env_be_deleted)

        n_envs_before = Environment.objects.count()
        response = self.client.post(f"/projects/{project.slug}/deleteenvironment/", {"environment_pk": env.pk})
        self.assertEqual(response.status_code, 302)
        messages = list(get_messages(response.wsgi_request))
        self.assertEqual(len(messages), 1)
        self.assertIn("cannot be deleted", str(messages[0]))
        n_envs_after = Environment.objects.count()

        self.assertEqual(n_envs_before, n_envs_after)

        """
        Test it is allowed to delete environment that is not in use
        """

        env_to_be_deleted = Environment.objects.get(name="env-to-be-deleted")

        can_env_be_deleted = can_model_instance_be_deleted("environment", env_to_be_deleted)
        self.assertTrue(can_env_be_deleted)

        n_env_before = Environment.objects.count()
        response = self.client.post(
            f"/projects/{project.slug}/deleteenvironment/", {"environment_pk": env_to_be_deleted.pk}
        )
        self.assertEqual(response.status_code, 302)
        n_envs_after = Environment.objects.count()

        self.assertEqual(n_envs_before - 1, n_envs_after)
