import pytest
from django.contrib.auth import get_user_model
from django.db.models import Q, QuerySet
from django.test import TestCase, override_settings

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


class AppInstanceManagerTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("foo1", "foo@test.com", "bar")
        self.project = Project.objects.create_project(
            name="test-perm-app-instance-manager", owner=self.user, description=""
        )
        app = Apps.objects.create(name="Persistent Volume", slug="volumeK8s")

        self.instances = []
        for i, model_class in enumerate(MODELS_LIST):
            subdomain = Subdomain.objects.create(subdomain=f"test_{i}")
            instance = BaseAppInstance.objects.create(
                owner=self.user,
                name=f"test_app_instance_{i}",
                app=app,
                project=self.project,
                subdomain=subdomain,
            )
            self.instances.append(instance)

    # ---------- get_app_instances_of_project ---------- #

    def test_get_app_instances_of_project(self):
        project = Project.objects.create_project(
            name="test-perm-app-instance_manager-2", owner=self.user, description=""
        )

        app = Apps.objects.create(name="Combiner", slug="combiner")

        subdomain = Subdomain.objects.create(subdomain="test_internal")
        instance = BaseAppInstance.objects.create(
            owner=self.user,
            name="test_app_instance_internal",
            app=app,
            project=project,
            subdomain=subdomain,
        )

        result = BaseAppInstance.objects.get_app_instances_of_project(self.user, self.project)

        self.assertEqual(len(result), len(MODELS_LIST))

        instance.project = self.project
        instance.save()

        result = BaseAppInstance.objects.get_app_instances_of_project(self.user, self.project)

        self.assertEqual(len(result), len(MODELS_LIST) + 1)

        instance.access = "private"
        instance.save()

        result = BaseAppInstance.objects.get_app_instances_of_project(self.user, self.project)

        self.assertEqual(len(result), len(MODELS_LIST) + 1)

    def test_get_app_instances_of_project_limit(self):
        result = BaseAppInstance.objects.get_app_instances_of_project(self.user, self.project, limit=3)

        self.assertEqual(len(result), 3)

        result = BaseAppInstance.objects.get_app_instances_of_project(self.user, self.project)

        self.assertEqual(len(result), len(MODELS_LIST))

    def test_get_app_instances_of_project_filter(self):
        app = Apps.objects.create(name="Combiner", slug="combiner")
        subdomain = Subdomain.objects.create(subdomain="test_internal")
        _ = BaseAppInstance.objects.create(
            owner=self.user,
            name="test_app_instance_internal",
            app=app,
            project=self.project,
            subdomain=subdomain,
        )

        def filter_func(slug):
            return Q(app__slug=slug)

        result = BaseAppInstance.objects.get_app_instances_of_project(
            self.user, self.project, filter_func=filter_func("volumeK8s")
        )

        self.assertEqual(len(result), len(MODELS_LIST))

        result = BaseAppInstance.objects.get_app_instances_of_project(self.user, self.project)

        self.assertEqual(len(result), len(MODELS_LIST) + 1)

        result = BaseAppInstance.objects.get_app_instances_of_project(
            self.user,
            self.project,
            filter_func=filter_func("non-existing-slug"),
        )

        self.assertEqual(len(result), 0)

    def test_get_app_instances_of_project_order_by(self):
        result = BaseAppInstance.objects.get_app_instances_of_project(self.user, self.project, order_by="name")

        self.assertEqual(len(result), len(MODELS_LIST))
        self.assertEqual(result.first().name, "test_app_instance_0")
        self.assertEqual(result.last().name, f"test_app_instance_{len(MODELS_LIST)-1}")

        result = BaseAppInstance.objects.get_app_instances_of_project(self.user, self.project, order_by="-name")

        self.assertEqual(len(result), len(MODELS_LIST))
        self.assertEqual(result.first().name, f"test_app_instance_{len(MODELS_LIST)-1}")
        self.assertEqual(result.last().name, "test_app_instance_0")

    # ---------- get_app_instances_of_project ---------- #


class AppInstanceManagerDeleteAppTestCase(TestCase):
    """Tests the AppInstanceManager model manager by deleting an app instance."""

    def setUp(self):
        self.user = User.objects.create_user("foo1", "foo@test.com", "bar")
        self.project = Project.objects.create_project(name="test-delete-app-instance", owner=self.user, description="")
        self.app = Apps.objects.create(name="Serve App", slug="serve-app")

        k8s_user_app_status = K8sUserAppStatus.objects.create(status="Running")

        self.app_instance = BaseAppInstance.objects.create(
            latest_user_action="Creating",
            k8s_user_app_status=k8s_user_app_status,
            owner=self.user,
            app=self.app,
            project=self.project,
        )

    def test_get_app_instances_not_deleted(self):
        """Tests method get_app_instances_not_deleted"""

        result = BaseAppInstance.objects.get_app_instances_not_deleted()

        self.assertIsInstance(result, QuerySet)
        self.assertEqual(len(result), 1)

        # Set app instance to status Deleted to mimimic deleting an app and retry
        # Merely setting the latest_user_action should be sufficient to make the delete
        # filter exclude this app instance.
        self.app_instance.latest_user_action = "Deleting"
        self.app_instance.save()

        result = BaseAppInstance.objects.get_app_instances_not_deleted()

        self.assertIsInstance(result, QuerySet)
        self.assertEqual(len(result), 0)


@pytest.mark.parametrize(
    "latest_user_action, k8s_user_app_status, expected_app_status",
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
        ("Creating", "CrashLoopBackoff", "Error"),
        ("Creating", "ErrImagePull", "Error"),
        ("Creating", "PostStartHookError", "Error"),
        ("Changing", "CrashLoopBackoff", "Error"),
        ("Changing", "ErrImagePull", "Error"),
        ("Changing", "PostStartHookError", "Error"),
        # Running
        ("Creating", "Running", "Running"),
        ("Changing", "Running", "Running"),
        # Deleting
        ("Deleting", "ContainerCreating", "Deleted"),
        ("Deleting", "PodInitializing", "Deleted"),
        ("Deleting", "NotFound", "Deleted"),
        ("Deleting", "CrashLoopBackoff", "Deleted"),
        ("Deleting", "ErrImagePull", "Deleted"),
        ("Deleting", "PostStartHookError", "Deleted"),
        ("Deleting", "Running", "Deleted"),
    ],
)
@pytest.mark.django_db
def test_with_app_status(latest_user_action, k8s_user_app_status, expected_app_status):
    """Tests the AppInstanceManager model manager annotation atn_app_status."""

    # Setup: create an app instance
    user = User.objects.create_user("foo1", "foo@test.com", "bar")
    project = Project.objects.create_project(name="test-app-status-codes", owner=user, description="")
    app = Apps.objects.create(name="Serve App", slug="serve-app")

    k8s_user_app_status = K8sUserAppStatus.objects.create(status=k8s_user_app_status)

    app_instance = BaseAppInstance.objects.create(
        latest_user_action=latest_user_action,
        k8s_user_app_status=k8s_user_app_status,
        owner=user,
        app=app,
        project=project,
    )

    # Apply the annotation
    annotated_app = BaseAppInstance.objects.with_app_status().get(id=app_instance.id)

    # Verify the annotated values
    assert annotated_app.atn_app_status == expected_app_status
