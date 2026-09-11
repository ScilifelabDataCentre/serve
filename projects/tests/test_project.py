import base64
import concurrent.futures
import threading
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.db import close_old_connections
from django.test import TestCase, TransactionTestCase, override_settings

from common.models import UserProfile

from ..exceptions import ProjectLimitReachedException
from ..models import Flavor, Project, ProjectManager

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
            cpu_req="100m",
            cpu_lim="1000m",
            mem_req="0.5Gi",
            mem_lim="1Gi",
            ephmem_req="200Mi",
            ephmem_lim="500Mi",
            gpu_req=1,
            gpu_lim=1,
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

        with self.assertRaisesMessage(ProjectLimitReachedException, "User not allowed to create project"):
            _ = Project.objects.create_project(name="test-perm", owner=user, description="")

    @override_settings(PROJECTS_PER_USER_LIMIT=1)
    def test_created_project_counts_towards_limit(self):
        user = User.objects.get(username=test_member["email"])

        Project.objects.create(
            name="creating-project", slug="creating-project", owner=user, description="", status="created"
        )

        self.assertFalse(Project.objects.user_can_create(user))

    @override_settings(PROJECTS_PER_USER_LIMIT=1)
    def test_deleted_and_archived_projects_do_not_count_towards_limit(self):
        user = User.objects.get(username=test_member["email"])

        Project.objects.create(
            name="deleted-project", slug="deleted-project", owner=user, description="", status="deleted"
        )
        Project.objects.create(
            name="archived-project", slug="archived-project", owner=user, description="", status="archived"
        )

        self.assertTrue(Project.objects.user_can_create(user))

    @override_settings(PROJECTS_PER_USER_LIMIT=0)
    def test_admin_can_create(self):
        superuser = User.objects.create_superuser("superuser", "test@example.com", "123")

        result = Project.objects.user_can_create(superuser)
        self.assertTrue(result)

        user = User.objects.get(username=test_member["email"])

        result = Project.objects.user_can_create(user)
        self.assertFalse(result)

    @override_settings(PROJECTS_PER_USER_LIMIT=1)
    def test_privileged_user_can_create_past_the_limit(self):
        user = User.objects.get(username=test_member["email"])
        _ = Project.objects.create(name="test-perm1", owner=user, description="")

        self.assertFalse(Project.objects.user_can_create(user))

        profile, _ = UserProfile.objects.get_or_create(user=user)
        profile.is_privileged = True
        profile.save()

        self.assertTrue(Project.objects.user_can_create(User.objects.get(pk=user.pk)))

    @override_settings(PROJECTS_PER_USER_LIMIT=0)
    def test_privileged_user_can_create_when_the_limit_is_zero(self):
        user = User.objects.get(username=test_member["email"])
        profile, _ = UserProfile.objects.get_or_create(user=user)
        profile.is_privileged = True
        profile.save()
        user = User.objects.get(pk=user.pk)

        self.assertTrue(Project.objects.user_can_create(user))
        self.assertIsNotNone(Project.objects.create_project(name="priv-proj", owner=user, description=""))

    def test_flavor_to_dict_without_gpu(self):
        flavor_dict = self.flavor.to_dict(gpu_enabled_app=False)
        self.assertNotIn("nvidia.com/gpu", flavor_dict["flavor"]["requests"])
        self.assertNotIn("nvidia.com/gpu", flavor_dict["flavor"]["limits"])

    def test_flavor_to_dict_with_gpu(self):
        flavor_dict = self.flavor.to_dict(gpu_enabled_app=True)
        self.assertIn("nvidia.com/gpu", flavor_dict["flavor"]["requests"])
        self.assertIn("nvidia.com/gpu", flavor_dict["flavor"]["limits"])


class ProjectCreationConcurrencyTestCase(TransactionTestCase):
    def setUp(self):
        self.user = User.objects.create_user("concurrent-user", "concurrent@test.com", "bar")

    @override_settings(PROJECTS_PER_USER_LIMIT=2)
    def test_concurrent_project_creation_cannot_exceed_limit(self):
        Project.objects.create_project(name="existing-project", owner=self.user, description="")

        barrier = threading.Barrier(2)
        thread_state = threading.local()
        original_generate_passkey = ProjectManager.generate_passkey

        def synchronized_generate_passkey(manager, length=20):
            if not getattr(thread_state, "synchronized", False):
                thread_state.synchronized = True
                barrier.wait(timeout=5)
            return original_generate_passkey(manager, length)

        def create_project(name):
            close_old_connections()
            try:
                owner = User.objects.get(pk=self.user.pk)
                project = Project.objects.create_project(name=name, owner=owner, description="")
                return project.pk
            except ProjectLimitReachedException:
                return None
            finally:
                close_old_connections()

        with patch.object(ProjectManager, "generate_passkey", synchronized_generate_passkey):
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                results = list(executor.map(create_project, ("concurrent-one", "concurrent-two")))

        self.assertEqual(sum(project_pk is not None for project_pk in results), 1)
        self.assertEqual(Project.objects.filter(owner=self.user, status__in=("created", "active")).count(), 2)
