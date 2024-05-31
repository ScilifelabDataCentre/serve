from django.contrib.auth import get_user_model
from django.db.models import Q
from django.test import TestCase, override_settings

from projects.models import Project

from ..models import (
    Apps,
    BaseAppInstance,
    CustomAppInstance,
    FilemanagerInstance,
    JupyterInstance,
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


class AppInstaceManagerTestCase(TestCase):
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
