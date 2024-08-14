from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.test import TestCase

from projects.models import Project

from ..models import (
    Apps,
    AppStatus,
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


class AppInstanceTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("foo1", "foo@test.com", "bar")

    def get_data(self, access):
        project = Project.objects.create_project(name="test-perm", owner=self.user, description="")
        app = Apps.objects.create(name="Serve App", slug="serve-app")

        app_instance_list = []
        for i, model_class in enumerate(MODELS_LIST):
            subdomain = Subdomain.objects.create(subdomain=f"test_internal_{i}")
            app_status = AppStatus.objects.create(status="Created")

            app_instance = model_class.objects.create(
                access=access,
                owner=self.user,
                name="test_app_instance_private",
                app=app,
                project=project,
                subdomain=subdomain,
                app_status=app_status,
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
