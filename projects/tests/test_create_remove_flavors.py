from django.contrib.auth import get_user_model
from django.test import TestCase

from projects.models import Project, Flavor

User = get_user_model()

test_user = {"username": "foo1", "email": "foo@test.com", "password": "bar"}
test_superuser = {"username": "superuser", "email": "superuser@test.com", "password": "bar"}

class FlavorTestCase(TestCase):
    def setUp(self):
        user = User.objects.create_user(test_user["username"], test_user["email"], test_user["password"])
        _ = Project.objects.create_project(name="test-flavor", owner=user, description="")
        superuser = User.objects.create_superuser(test_superuser["username"], test_superuser["email"], test_superuser["password"])
        #self.client.login(username=test_user["email"], password=test_user["password"])

    def test_forbidden_flavor_creation(self):
        """
        Test regular user not allowed to create flavor
        """
        self.client.login(username=test_user["email"], password=test_user["password"])

        project = Project.objects.get(name="test-flavor")

        response = self.client.post(
            f"/projects/{project.slug}/createflavor/",
            {"flavor_name": "new-flavor",
             "cpu_req": "n",
             "mem_req": "n",
             "ephmem_req": "n",
             "cpu_lim": "n",
             "mem_lim": "n",
             "ephmem_lim": "n"             
             },
        )

        self.assertEqual(response.status_code, 403)

        flavors = Flavor.objects.all()
        self.assertEqual(len(flavors), 0)


    def test_allowed_flavor_creation(self):
        """
        Test superuser is allowed to create flavor
        """
        self.client.login(username=test_superuser["email"], password=test_superuser["password"])
        project = Project.objects.get(name="test-flavor")
        response = self.client.post(
            f"/projects/{project.slug}/createflavor/",
            {"flavor_name": "new-flavor",
             "cpu_req": "n",
             "mem_req": "n",
             "ephmem_req": "n",
             "cpu_lim": "n",
             "mem_lim": "n",
             "ephmem_lim": "n"             
             },
        )

        self.assertEqual(response.status_code, 302)

        flavors = Flavor.objects.all()
        self.assertEqual(len(flavors), 1)
