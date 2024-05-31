from datetime import datetime, timedelta, timezone

import pytest
from django.contrib.auth import get_user_model
from django.test import TestCase
from guardian.shortcuts import assign_perm, remove_perm

from apps.models import Apps, AppStatus, JupyterInstance, Subdomain
from common.models import EmailVerificationTable, UserProfile
from projects.models import Project
from scripts.app_instance_permissions import run

from .helpers import do_delete_account, do_pause_account
from .system_version import SystemVersion

User = get_user_model()


class AppInstancePermissionScriptTestCase(TestCase):
    def get_data(self, user, access):
        project = Project.objects.create_project(name="test-perm", owner=user, description="")
        app = Apps.objects.create(name="FEDn Combiner")

        subdomain = Subdomain.objects.create(subdomain="test_internal")
        app_status = AppStatus.objects.create(status="Created")
        app_instance = JupyterInstance.objects.create(
            access=access,
            owner=user,
            name="test_app_instance_private",
            app=app,
            project=project,
            subdomain=subdomain,
            app_status=app_status,
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


@pytest.mark.django_db
def test_do_delete_account():
    """
    Test function helpers.do_delete_account()
    """
    test_user = {"username": "foo@test.com", "email": "foo@test.com", "password": "bar"}
    user = User.objects.create_user(test_user["username"], test_user["email"], test_user["password"])
    assert user is not None and user.id > 0
    assert user.is_active is True

    profile = UserProfile(user=user, is_approved=True)
    profile.save()
    assert profile.deleted_on is None

    user_id = user.id
    user_account_deleted = do_delete_account(user_id)

    assert user_account_deleted is True

    user = User.objects.get(pk=user_id)

    assert user.is_active is False
    assert user.userprofile.deleted_on >= datetime.now(timezone.utc) - timedelta(seconds=10)


@pytest.mark.django_db
def test_do_pause_account():
    """
    Test function helpers.do_pause_account()
    """
    test_user = {"username": "foo@test.com", "email": "foo@test.com", "password": "bar"}
    user = User.objects.create_user(test_user["username"], test_user["email"], test_user["password"])
    assert user is not None and user.id > 0
    assert user.is_active is True

    profile = UserProfile(user=user, is_approved=True)
    profile.save()

    user_id = user.id
    user_account_paused = do_pause_account(user_id)

    assert user_account_paused is True

    user = User.objects.get(pk=user_id)
    email_verification_table = EmailVerificationTable.objects.filter(user_id=user_id).first()

    assert user.is_active is False
    assert email_verification_table is None


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
