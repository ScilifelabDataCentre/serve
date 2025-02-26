import pytest
from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.test import TestCase

from projects.models import Project

from ..models import (
    Apps,
    BaseAppInstance,
    CustomAppInstance,
    FilemanagerInstance,
    JupyterInstance,
    K8sUserAppStatus,
    RStudioInstance,
    ShinyInstance,
    Subdomain,
    TissuumapsInstance,
    VSCodeInstance,
)

User = get_user_model()

MODELS_LIST = [
    JupyterInstance,
    RStudioInstance,
    VSCodeInstance,
    FilemanagerInstance,
    ShinyInstance,
    TissuumapsInstance,
    CustomAppInstance,
]


class AppInstancePermissionsTestCase(TestCase):
    """Test case for app instance permissions."""

    def setUp(self):
        self.user = User.objects.create_user("foo1", "foo@test.com", "bar")

    def get_data(self, access):
        project = Project.objects.create_project(name="test-perm", owner=self.user, description="")
        app = Apps.objects.create(name="Serve App", slug="serve-app")

        app_instance_list = []
        for i, model_class in enumerate(MODELS_LIST):
            subdomain = Subdomain.objects.create(subdomain=f"test_internal_{i}")
            k8s_user_app_status = K8sUserAppStatus.objects.create()

            app_instance = model_class.objects.create(
                access=access,
                owner=self.user,
                name="test_app_instance_private",
                app=app,
                project=project,
                subdomain=subdomain,
                k8s_user_app_status=k8s_user_app_status,
            )
            app_instance_list.append(app_instance)

        return app_instance_list

    def test_permission_created_if_private(self):
        app_instance_list = self.get_data("private")

        result_list = [self.user.has_perm("can_access_app", app_instance) for app_instance in app_instance_list]
        print(result_list)
        self.assertTrue(all(result_list))

    def test_permission_do_note_created_if_project(self):
        app_instance_list = self.get_data("project")

        result_list = [self.user.has_perm("can_access_app", app_instance) for app_instance in app_instance_list]
        print(result_list)
        self.assertFalse(any(result_list))

    def test_permission_create_if_changed_to_private(self):
        app_instance_list = self.get_data("project")

        result_list = [self.user.has_perm("can_access_app", app_instance) for app_instance in app_instance_list]
        print(result_list)
        self.assertFalse(any(result_list))

        for app_instance in app_instance_list:
            app_instance.access = "private"
            app_instance.save()

        result_list = [self.user.has_perm("can_access_app", app_instance) for app_instance in app_instance_list]
        print(result_list)
        self.assertTrue(all(result_list))

    def test_permission_remove_if_changed_from_project(self):
        app_instance_list = self.get_data("private")

        result_list = [self.user.has_perm("can_access_app", app_instance) for app_instance in app_instance_list]
        print(result_list)
        self.assertTrue(all(result_list))

        for app_instance in app_instance_list:
            app_instance.access = "project"
            app_instance.save()

        result_list = [self.user.has_perm("can_access_app", app_instance) for app_instance in app_instance_list]
        print(result_list)
        self.assertFalse(any(result_list))


class AppInstanceStatusTestCase(TestCase):
    """Test case for some common app instance status properties."""

    def setUp(self):
        self.user = User.objects.create_user("foo1", "foo@test.com", "bar")

    def get_data(self, latest_user_action, k8s_status):
        project = Project.objects.create_project(name="test-status", owner=self.user, description="")
        app = Apps.objects.create(name="Serve App", slug="serve-app")

        subdomain = Subdomain.objects.create(subdomain="test_internal")
        k8s_user_app_status = K8sUserAppStatus.objects.create(status=k8s_status)

        app_instance = BaseAppInstance.objects.create(
            owner=self.user,
            name="test_app_instance_status",
            app=app,
            project=project,
            subdomain=subdomain,
            latest_user_action=latest_user_action,
            k8s_user_app_status=k8s_user_app_status,
        )

        return app_instance

    def test_app_status_if_creating_none(self):
        app_instance = self.get_data("Creating", None)

        self.assertEqual(app_instance.get_app_status(), "Creating")
        self.assertEqual(app_instance.get_status_group(), "warning")

    def test_app_status_if_creating_running(self):
        app_instance = self.get_data("Creating", "Running")

        self.assertEqual(app_instance.get_app_status(), "Running")
        self.assertEqual(app_instance.get_status_group(), "success")

    def test_app_status_if_changing_errimagepull(self):
        app_instance = self.get_data("Changing", "ErrImagePull")

        self.assertEqual(app_instance.get_app_status(), "Error")
        self.assertEqual(app_instance.get_status_group(), "danger")

    def test_app_status_if_deleting_running(self):
        app_instance = self.get_data("Deleting", "Running")

        self.assertEqual(app_instance.get_app_status(), "Deleted")
        self.assertEqual(app_instance.get_status_group(), "danger")


@pytest.mark.parametrize(
    "latest_user_action, k8s_user_app_status, expected",
    [
        # Creating / Changing
        ("Creating", "ContainerCreating", "Creating"),
        ("Creating", "PodInitializing", "Creating"),
        ("Changing", "ContainerCreating", "Changing"),
        ("Changing", "PodInitializing", "Changing"),
        # Error (NotFound)
        ("Creating", "NotFound", "Error (NotFound)"),
        ("Changing", "NotFound", "Error (NotFound)"),
        # Error
        ("Creating", "CrashLoopBackOff", "Error"),
        ("Creating", "ErrImagePull", "Error"),
        ("Creating", "PostStartHookError", "Error"),
        ("Changing", "CrashLoopBackOff", "Error"),
        ("Changing", "ErrImagePull", "Error"),
        ("Changing", "PostStartHookError", "Error"),
        # Running
        ("Creating", "Running", "Running"),
        ("Changing", "Running", "Running"),
        # Deleting
        ("Deleting", "ContainerCreating", "Deleted"),
        ("Deleting", "PodInitializing", "Deleted"),
        ("Deleting", "NotFound", "Deleted"),
        ("Deleting", "CrashLoopBackOff", "Deleted"),
        ("Deleting", "ErrImagePull", "Deleted"),
        ("Deleting", "PostStartHookError", "Deleted"),
        ("Deleting", "Running", "Deleted"),
        # SystemDeleting
        ("SystemDeleting", "ContainerCreating", "Deleted"),
        ("SystemDeleting", "PodInitializing", "Deleted"),
        ("SystemDeleting", "NotFound", "Deleted"),
        ("SystemDeleting", "CrashLoopBackOff", "Deleted"),
        ("SystemDeleting", "ErrImagePull", "Deleted"),
        ("SystemDeleting", "PostStartHookError", "Deleted"),
        ("SystemDeleting", "Running", "Deleted"),
    ],
)
def test_convert_to_app_status(latest_user_action, k8s_user_app_status, expected):
    """Tests the static method BaseAppInstance.convert_to_app_status"""
    assert BaseAppInstance.convert_to_app_status(latest_user_action, k8s_user_app_status) == expected
