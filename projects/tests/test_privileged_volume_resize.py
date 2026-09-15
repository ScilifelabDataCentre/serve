from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings

from apps.models import Apps, K8sUserAppStatus, Subdomain, VolumeInstance
from common.models import UserProfile

from ..models import Project

User = get_user_model()

PASSWORD = "tesT12345@"


def make_privileged(user):
    profile, _ = UserProfile.objects.get_or_create(user=user)
    profile.is_privileged = True
    profile.save()

    return User.objects.get(pk=user.pk)


class PrivilegedVolumeResizeTestCase(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("owner", "owner@test.com", PASSWORD)
        self.project = Project.objects.create_project(name="privileged-proj", owner=self.owner, description="")
        self.volume = VolumeInstance.objects.create(
            name="project-vol",
            size=10,
            owner=self.owner,
            app=Apps.objects.create(name="Persistent Volume", slug="volumeK8s"),
            project=self.project,
            subdomain=Subdomain.objects.create(subdomain="project-vol"),
            k8s_user_app_status=K8sUserAppStatus.objects.create(),
        )
        self.url = f"/projects/{self.project.slug}/volume/{self.volume.pk}/resize/"

    def login(self, email):
        client = Client()
        self.assertEqual(client.post("/accounts/login/", {"username": email, "password": PASSWORD}).status_code, 302)

        return client

    def test_a_plain_owner_cannot_resize(self):
        response = self.login(self.owner.email).post(self.url, {"size": 20})

        self.assertEqual(response.status_code, 403)
        self.volume.refresh_from_db()
        self.assertEqual(self.volume.size, 10)

    @patch("projects.views._redeploy_volume")
    def test_a_privileged_owner_can_expand_and_the_old_size_is_remembered(self, mock_redeploy):
        make_privileged(self.owner)

        response = self.login(self.owner.email).post(self.url, {"size": 20})

        self.assertEqual(response.status_code, 200)
        self.volume.refresh_from_db()
        self.assertEqual(self.volume.size, 20)
        self.assertEqual(self.volume.previous_size, 10)
        mock_redeploy.assert_called_once()

    @patch("projects.views._redeploy_volume")
    def test_shrinking_is_rejected(self, mock_redeploy):
        make_privileged(self.owner)

        response = self.login(self.owner.email).post(self.url, {"size": 5})

        self.assertEqual(response.status_code, 400)
        self.assertIn("never shrunk", response.json()["error"])
        self.volume.refresh_from_db()
        self.assertEqual(self.volume.size, 10)
        mock_redeploy.assert_not_called()

    @override_settings(PRIVILEGED_USER_MAX_VOLUME_SIZE_GB=50)
    @patch("projects.views._redeploy_volume")
    def test_a_size_above_the_ceiling_is_rejected(self, mock_redeploy):
        make_privileged(self.owner)

        response = self.login(self.owner.email).post(self.url, {"size": 51})

        self.assertEqual(response.status_code, 400)
        self.assertIn("50 GB", response.json()["error"])
        mock_redeploy.assert_not_called()

    @override_settings(PRIVILEGED_USER_MAX_VOLUME_SIZE_GB=200000)
    @patch("projects.views._redeploy_volume")
    def test_a_ceiling_above_the_model_maximum_does_not_bypass_it(self, mock_redeploy):
        make_privileged(self.owner)

        response = self.login(self.owner.email).post(self.url, {"size": 150000})

        self.assertEqual(response.status_code, 400)
        mock_redeploy.assert_not_called()

    def test_a_resize_the_cluster_refused_is_reverted_and_reported(self):
        make_privileged(self.owner)
        self.volume.size = 20
        self.volume.previous_size = 10
        self.volume.info = {"helm": {"success": False, "info": {"stderr": "pvc cannot be resized"}}}
        self.volume.save()

        response = self.login(self.owner.email).get(f"/projects/{self.project.slug}/settings/")

        self.volume.refresh_from_db()
        self.assertEqual(self.volume.size, 10)
        self.assertIsNone(self.volume.previous_size)
        self.assertContains(response, "could not be applied")
        self.assertNotContains(response, "pvc cannot be resized")
