from django.contrib.auth import get_user_model
from django.test import TestCase
from guardian.shortcuts import assign_perm, remove_perm

from apps.models import AppInstance, Apps
from projects.models import Project
from scripts.app_instance_permissions import run

from .system_version import SystemVersion

User = get_user_model()


class AppInstancePermissionScriptTestCase(TestCase):
    def get_data(self, user, access):
        project = Project.objects.create_project(name="test-perm", owner=user, description="", repository="")
        app = Apps.objects.create(name="FEDn Combiner")

        app_instance = AppInstance.objects.create(
            access=access,
            owner=user,
            name="test_app_instance_private",
            app=app,
            project=project,
        )

        return [project, app, app_instance]

    def test_permissions_are_added(self):
        user = User.objects.create_user("foo1", "foo@test.com", "bar")

        project, app, app_instance = self.get_data(user, "private")

        remove_perm("can_access_app", user, app_instance)

        run()

        has_perm = user.has_perm("can_access_app", app_instance)

        self.assertTrue(has_perm)

    def test_permissions_are_removed(self):
        user = User.objects.create_user("foo1", "foo@test.com", "bar")

        project, app, app_instance = self.get_data(user, "project")

        assign_perm("can_access_app", user, app_instance)

        run()

        has_perm = user.has_perm("can_access_app", app_instance)

        self.assertFalse(has_perm)


# Tests for the system version
def test_system_version_verify_singleton():
    actual1 = SystemVersion()
    assert actual1.get_init_counter() == 1
    actual2 = SystemVersion()
    assert actual2.get_init_counter() == 1
    assert actual1 is actual2


def test_system_version_verify_pyproject_is_parsed():
    actual = SystemVersion().get_pyproject_is_parsed()
    assert actual is True


def test_system_version_get_version_text():
    actual = SystemVersion().get_version_text()
    assert actual == "unset"


def test_system_version_get_build_date():
    actual = SystemVersion().get_build_date()
    assert actual == ""


def test_system_version_get_gitref():
    actual = SystemVersion().get_gitref()
    assert actual == ""


def test_system_version_get_imagetag():
    actual = SystemVersion().get_imagetag()
    assert actual == ""
