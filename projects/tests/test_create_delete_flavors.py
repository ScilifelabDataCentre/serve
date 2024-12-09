from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.test import TestCase

from apps.models import Apps, CustomAppInstance, Subdomain
from projects.models import Flavor, Project
from projects.views import can_model_instance_be_deleted

User = get_user_model()

test_user = {"username": "foo1", "email": "foo@test.com", "password": "bar"}
test_superuser = {"username": "superuser", "email": "superuser@test.com", "password": "bar"}


class FlavorTestCaseRegularUser(TestCase):
    def setUp(self):
        user = User.objects.create_user(test_user["username"], test_user["email"], test_user["password"])
        self.project = Project.objects.create_project(name="test-flavor", owner=user, description="")
        self.flavor_to_be_deleted = Flavor.objects.create(name="flavor-to-be-deleted", project=self.project)
        self.client.login(username=test_user["email"], password=test_user["password"])

    def test_flavor_creation_regular_user(self):
        """
        Test regular user not allowed to create flavor
        """
        n_flavors_before = Flavor.objects.count()
        response = self.client.post(
            f"/projects/{self.project.slug}/createflavor/",
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
        n_flavors_after = Flavor.objects.count()
        self.assertEqual(n_flavors_before, n_flavors_after)

    def test_flavor_deletion_regular_user(self):
        """
        Test regular user not allowed to delete flavor
        """
        n_flavors_before = Flavor.objects.count()
        response = self.client.post(
            f"/projects/{self.project.slug}/deleteflavor/", {"flavor_pk": self.flavor_to_be_deleted.pk}
        )
        self.assertEqual(response.status_code, 403)
        n_flavors_after = Flavor.objects.count()
        self.assertEqual(n_flavors_before, n_flavors_after)


class FlavorTestCaseSuperUser(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(test_user["username"], test_user["email"], test_user["password"])
        self.project = Project.objects.create_project(name="test-flavor", owner=self.user, description="")
        User.objects.create_superuser(test_superuser["username"], test_superuser["email"], test_superuser["password"])
        self.flavor_to_be_deleted = Flavor.objects.create(name="flavor-to-be-deleted", project=self.project)
        self.client.login(username=test_superuser["email"], password=test_superuser["password"])

    def test_flavor_creation_superuser(self):
        """
        Test superuser is allowed to create flavor
        """
        n_flavors_before = Flavor.objects.count()
        response = self.client.post(
            f"/projects/{self.project.slug}/createflavor/",
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
        n_flavors_after = Flavor.objects.count()
        self.assertEqual(n_flavors_before + 1, n_flavors_after)

    def test_flavor_deletion_inuse_superuser(self):
        """
        Test it is not allowed to delete flavor that is in use
        """
        flavor_cannot_be_deleted = Flavor.objects.create(name="flavor-cannot-be-deleted", project=self.project)

        app = Apps.objects.create(name="Some App", slug="customapp")
        subdomain = Subdomain.objects.create(subdomain="test_internal")
        self.app_instance = CustomAppInstance.objects.create(
            access="public",
            owner=self.user,
            name="test_app_instance_flavor",
            description="some app description",
            app=app,
            project=self.project,
            flavor=flavor_cannot_be_deleted,
            subdomain=subdomain,
        )

        can_flavor_be_deleted = can_model_instance_be_deleted("flavor", flavor_cannot_be_deleted)
        self.assertFalse(can_flavor_be_deleted)

        n_flavors_before = Flavor.objects.count()
        response = self.client.post(
            f"/projects/{self.project.slug}/deleteflavor/", {"flavor_pk": flavor_cannot_be_deleted.pk}
        )
        self.assertEqual(response.status_code, 302)
        messages = list(get_messages(response.wsgi_request))
        self.assertEqual(len(messages), 1)
        self.assertIn("cannot be deleted", str(messages[0]))
        n_flavors_after = Flavor.objects.count()

        self.assertEqual(n_flavors_before, n_flavors_after)

    def test_flavor_deletion_notinuse_superuser(self):
        """
        Test it is allowed to delete flavor that is not in use
        """
        can_flavor_be_deleted = can_model_instance_be_deleted("flavor", self.flavor_to_be_deleted)
        self.assertTrue(can_flavor_be_deleted)

        n_flavors_before = Flavor.objects.count()
        response = self.client.post(
            f"/projects/{self.project.slug}/deleteflavor/", {"flavor_pk": self.flavor_to_be_deleted.pk}
        )
        self.assertEqual(response.status_code, 302)
        n_flavors_after = Flavor.objects.count()

        self.assertEqual(n_flavors_before - 1, n_flavors_after)
