from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from guardian.shortcuts import assign_perm

from apps.models import Apps
from common.models import UserProfile

from ..models import Environment, Flavor, Project

User = get_user_model()

PASSWORD = "tesT12345@"


def make_privileged(user):
    profile, _ = UserProfile.objects.get_or_create(user=user)
    profile.is_privileged = True
    profile.save()

    return User.objects.get(pk=user.pk)


class PrivilegedProjectResourcesTestCase(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("owner", "owner@test.com", PASSWORD)
        self.project = Project.objects.create_project(name="privileged-proj", owner=self.owner, description="")
        self.app = Apps.objects.create(name="Jupyter Lab", slug="jupyter-lab")

    def login(self, email):
        client = Client()
        self.assertEqual(client.post("/accounts/login/", {"username": email, "password": PASSWORD}).status_code, 302)

        return client

    def flavor_payload(self):
        return {
            "flavor_name": "4 vCPU, 8 GB RAM",
            "cpu_req": "200m",
            "cpu_lim": "4000m",
            "mem_req": "0.5Gi",
            "mem_lim": "8Gi",
            "ephmem_req": "200Mi",
            "ephmem_lim": "5000Mi",
            "gpu_req": 0,
            "gpu_lim": 0,
        }

    def test_a_plain_owner_cannot_create_a_flavor(self):
        response = self.login(self.owner.email).post(
            f"/projects/{self.project.slug}/createflavor/", self.flavor_payload()
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(Flavor.objects.filter(project=self.project).exists())

    def test_a_privileged_owner_can_create_and_delete_a_flavor(self):
        make_privileged(self.owner)
        client = self.login(self.owner.email)

        response = client.post(f"/projects/{self.project.slug}/createflavor/", self.flavor_payload())

        self.assertEqual(response.status_code, 302)
        flavor = Flavor.objects.get(project=self.project, name="4 vCPU, 8 GB RAM")

        response = client.post(f"/projects/{self.project.slug}/deleteflavor/", {"flavor_pk": flavor.pk})

        self.assertEqual(response.status_code, 302)
        self.assertFalse(Flavor.objects.filter(pk=flavor.pk).exists())

    def test_a_privileged_owner_can_create_an_environment(self):
        make_privileged(self.owner)

        response = self.login(self.owner.email).post(
            f"/projects/{self.project.slug}/createenvironment/",
            {
                "environment_name": "test-environment",
                "environment_repository": "docker.io",
                "environment_image": "jupyter/minimal-notebook:latest",
                "environment_app": self.app.pk,
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(Environment.objects.filter(project=self.project, name="test-environment").exists())

    def test_a_privileged_non_owner_needs_a_grant(self):
        other = make_privileged(User.objects.create_user("other", "other@test.com", PASSWORD))
        self.project.authorized.add(other)
        assign_perm("can_view_project", other, self.project)

        client = self.login(other.email)
        url = f"/projects/{self.project.slug}/createflavor/"

        self.assertEqual(client.post(url, self.flavor_payload()).status_code, 403)

        self.project.privileged_users.add(other)

        self.assertEqual(client.post(url, self.flavor_payload()).status_code, 302)
