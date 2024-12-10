import base64

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase, override_settings

from ..models import Flavor, Project

User = get_user_model()

test_user = {"username": "admin", "email": "foo@test.com", "password": "bar"}

test_member = {"username": "member", "email": "member@test.com", "password": "bar"}


class ProjectTestCase(TestCase):
    def setUp(self):
        user = User.objects.create_user(test_user["username"], test_user["email"], test_user["password"])
        Project.objects.create(
            name="test-secret",
            slug="test-secret",
            owner=user,
            project_key="a2V5",
            project_secret="c2VjcmV0",
        )
        _ = Project.objects.create_project(name="test-perm", owner=user, description="")
        user = User.objects.create_user(test_member["username"], test_member["email"], test_member["password"])
        self.flavor = Flavor.objects.create(
            cpu_req="500m",
            cpu_lim="1000m",
            mem_req="0.5Gi",
            mem_lim="1Gi",
            ephmem_req="200Mi",
            ephmem_lim="500Mi",
            gpu_req="1",
            gpu_lim="1",
            name="1 vCPU, 0.5 GB RAM",
            project=None,
        )

    def test_decrypt_key(self):
        project = Project.objects.filter(name="test-secret").first()

        def decrypt_key(key):
            base64_bytes = key.encode("ascii")
            result = base64.b64decode(base64_bytes)
            return result.decode("ascii")

        self.assertEqual(decrypt_key(project.project_key), "key")
        self.assertEqual(decrypt_key(project.project_secret), "secret")

    def test_owner_can_view_permission(self):
        """
        Ensure that project owner has 'can_view_project' permission
        """
        project = Project.objects.get(name="test-perm")
        self.assertTrue(project.owner.has_perm("can_view_project", project))

    def test_member_can_view_permission(self):
        """
        Ensure that non-project member don't have 'can_view_project' permission
        """
        user = User.objects.get(username=test_member["email"])
        project = Project.objects.get(name="test-perm")
        self.assertFalse(user.has_perm("can_view_project", project))

    @override_settings(PROJECTS_PER_USER_LIMIT=1)
    def test_user_can_create(self):
        user = User.objects.get(username=test_member["email"])
        result = Project.objects.user_can_create(user)

        self.assertTrue(result)

        _ = Project.objects.create(name="test-perm1", owner=user, description="")

        result = Project.objects.user_can_create(user)

        self.assertFalse(result)

    @override_settings(PROJECTS_PER_USER_LIMIT=None)
    def test_user_can_create_should_handle_none(self):
        user = User.objects.get(username=test_member["email"])
        result = Project.objects.user_can_create(user)

        self.assertTrue(result)

        _ = Project.objects.create(name="test-perm1", owner=user, description="")

        result = Project.objects.user_can_create(user)

        self.assertTrue(result)

    @override_settings(PROJECTS_PER_USER_LIMIT=0)
    def test_user_can_create_should_handle_zero(self):
        user = User.objects.get(username=test_member["email"])
        result = Project.objects.user_can_create(user)

        self.assertFalse(result)

    @override_settings(PROJECTS_PER_USER_LIMIT=1)
    def test_user_can_create_with_permission(self):
        content_type = ContentType.objects.get_for_model(Project)
        project_permissions = Permission.objects.filter(content_type=content_type)

        add_permission = next(
            (perm for perm in project_permissions if perm.codename == "add_project"),
            None,
        )

        user = User.objects.get(username=test_member["email"])

        _ = Project.objects.create(name="test-perm1", owner=user, description="")

        result = Project.objects.user_can_create(user)

        self.assertFalse(result)

        user.user_permissions.add(add_permission)
        user = User.objects.get(username=test_member["email"])

        result = Project.objects.user_can_create(user)

        self.assertTrue(result)

    @override_settings(PROJECTS_PER_USER_LIMIT=1)
    def test_create_project_raises_exception(self):
        user = User.objects.get(username=test_member["email"])

        _ = Project.objects.create(name="test-perm1", owner=user, description="")

        with self.assertRaisesMessage(Exception, "User not allowed to create project"):
            _ = Project.objects.create_project(name="test-perm", owner=user, description="")

    @override_settings(PROJECTS_PER_USER_LIMIT=0)
    def test_admin_can_create(self):
        superuser = User.objects.create_superuser("superuser", "test@example.com", "123")

        result = Project.objects.user_can_create(superuser)
        self.assertTrue(result)

        user = User.objects.get(username=test_member["email"])

        result = Project.objects.user_can_create(user)
        self.assertFalse(result)

    def test_flavor_to_dict_without_gpu(self):
        flavor_dict = self.flavor.to_dict(app_slug="some-app")
        self.assertNotIn("nvidia.com/gpu", flavor_dict["flavor"]["requests"])
        self.assertNotIn("nvidia.com/gpu", flavor_dict["flavor"]["limits"])

    def test_flavor_to_dict_with_gpu(self):
        flavor_dict = self.flavor.to_dict(app_slug="jupyter-lab")
        self.assertIn("nvidia.com/gpu", flavor_dict["flavor"]["requests"])
        self.assertIn("nvidia.com/gpu", flavor_dict["flavor"]["limits"])
