from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.models import Apps, CustomAppInstance, Subdomain
from projects.models import Flavor, Project
from projects.views import can_model_instance_be_deleted

User = get_user_model()

test_user = {"username": "foo1", "email": "foo@test.com", "password": "bar"}
test_superuser = {"username": "superuser", "email": "superuser@test.com", "password": "bar"}


class FlavorTestCase(TestCase):
    def setUp(self):
        user = User.objects.create_user(test_user["username"], test_user["email"], test_user["password"])
        project = Project.objects.create_project(name="test-flavor", owner=user, description="")
        User.objects.create_superuser(test_superuser["username"], test_superuser["email"], test_superuser["password"])
        Flavor.objects.create(name="flavor-to-be-deleted", project=project)

    def test_flavor_creation_user(self):
        """
        Test regular user not allowed to create flavor
        """
        self.client.login(username=test_user["email"], password=test_user["password"])

        project = Project.objects.get(name="test-flavor")

        n_flavors_before = len(Flavor.objects.all())
        response = self.client.post(
            f"/projects/{project.slug}/createflavor/",
            {
                "flavor_name": "new-flavor-user",
                "cpu_req": "n",
                "mem_req": "n",
                "ephmem_req": "n",
                "cpu_lim": "n",
                "mem_lim": "n",
                "ephmem_lim": "n",
            },
        )
        self.assertEqual(response.status_code, 403)
        n_flavors_after = len(Flavor.objects.all())

        self.assertEqual(n_flavors_before, n_flavors_after)

        """
        Test regular user not allowed to delete flavor
        """
        flavor_to_be_deleted = Flavor.objects.get(name="flavor-to-be-deleted")
        n_flavors_before = len(Flavor.objects.all())
        response = self.client.post(f"/projects/{project.slug}/deleteflavor/", {"flavor_pk": flavor_to_be_deleted.pk})
        self.assertEqual(response.status_code, 403)
        n_flavors_after = len(Flavor.objects.all())
        self.assertEqual(n_flavors_before, n_flavors_after)

    def test_flavor_creation_deletion_superuser(self):
        """
        Test superuser is allowed to create flavor
        """
        self.client.login(username=test_superuser["email"], password=test_superuser["password"])
        project = Project.objects.get(name="test-flavor")
        n_flavors_before = len(Flavor.objects.all())
        response = self.client.post(
            f"/projects/{project.slug}/createflavor/",
            {
                "flavor_name": "new-flavor-superuser",
                "cpu_req": "n",
                "mem_req": "n",
                "ephmem_req": "n",
                "cpu_lim": "n",
                "mem_lim": "n",
                "ephmem_lim": "n",
            },
        )
        self.assertEqual(response.status_code, 302)
        n_flavors_after = len(Flavor.objects.all())

        self.assertEqual(n_flavors_before + 1, n_flavors_after)

        """
        Test it is not allowed to delete flavor that is in use
        """
        user = User.objects.get(email=test_superuser["email"])
        flavor = Flavor.objects.get(name="new-flavor-superuser")

        app = Apps.objects.create(name="Some App", slug="customapp")
        subdomain = Subdomain.objects.create(subdomain="test_internal")
        self.app_instance = CustomAppInstance.objects.create(
            access="public",
            owner=user,
            name="test_app_instance_flavor",
            description="some app description",
            app=app,
            project=project,
            k8s_values={
                "environment": {"pk": ""},
            },
            flavor=flavor,
            subdomain=subdomain,
        )

        can_flavor_be_deleted = can_model_instance_be_deleted("flavor", flavor.pk)
        self.assertFalse(can_flavor_be_deleted)

        n_flavors_before = len(Flavor.objects.all())
        response = self.client.post(f"/projects/{project.slug}/deleteflavor/", {"flavor_pk": flavor.pk})
        self.assertEqual(response.status_code, 302)
        n_flavors_after = len(Flavor.objects.all())

        self.assertEqual(n_flavors_before, n_flavors_after)

        """
        Test it is allowed to delete flavor that is not in use
        """

        flavor_to_be_deleted = Flavor.objects.get(name="flavor-to-be-deleted")

        can_flavor_be_deleted = can_model_instance_be_deleted("flavor", flavor_to_be_deleted.pk)
        self.assertTrue(can_flavor_be_deleted)

        n_flavors_before = len(Flavor.objects.all())
        response = self.client.post(f"/projects/{project.slug}/deleteflavor/", {"flavor_pk": flavor_to_be_deleted.pk})
        self.assertEqual(response.status_code, 302)
        n_flavors_after = len(Flavor.objects.all())

        self.assertEqual(n_flavors_before - 1, n_flavors_after)
