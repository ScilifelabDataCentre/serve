from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase

from common.models import UserProfile
from common.privileges import (
    PRIVILEGED_USERS_GROUP,
    has_privileged_access,
    is_privileged_user,
)
from projects.models import Project

User = get_user_model()


def make_privileged(user):
    profile, _ = UserProfile.objects.get_or_create(user=user)
    profile.is_privileged = True
    profile.save()

    return User.objects.get(pk=user.pk)


class IsPrivilegedUserTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("plain", "plain@test.com", "bar")

    def test_a_plain_user_is_not_privileged(self):
        self.assertFalse(is_privileged_user(self.user))

    def test_the_profile_flag_makes_a_user_privileged(self):
        self.assertTrue(is_privileged_user(make_privileged(self.user)))

    def test_the_group_makes_a_user_privileged(self):
        group = Group.objects.create(name=PRIVILEGED_USERS_GROUP)
        group.permissions.add(
            Permission.objects.get(
                codename="privileged_user", content_type=ContentType.objects.get_for_model(UserProfile)
            )
        )
        self.user.groups.add(group)

        self.assertTrue(is_privileged_user(User.objects.get(pk=self.user.pk)))

    def test_an_admin_is_not_a_privileged_user(self):
        superuser = User.objects.create_superuser("admin", "admin@test.com", "bar")

        self.assertFalse(is_privileged_user(superuser))

    def test_a_user_without_a_profile_is_not_privileged(self):
        UserProfile.objects.filter(user=self.user).delete()

        self.assertFalse(is_privileged_user(User.objects.get(pk=self.user.pk)))


class HasPrivilegedAccessTestCase(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("owner", "owner@test.com", "bar")
        self.project = Project.objects.create_project(name="owned", owner=self.owner, description="")

    def test_a_privileged_owner_has_access_but_a_plain_owner_does_not(self):
        self.assertFalse(has_privileged_access(self.owner, self.project))
        self.assertTrue(has_privileged_access(make_privileged(self.owner), self.project))

    def test_an_admin_has_access_anywhere_without_a_grant(self):
        superuser = User.objects.create_superuser("admin", "admin@test.com", "bar")

        self.assertTrue(has_privileged_access(superuser, self.project))

    def test_a_privileged_non_owner_needs_a_grant(self):
        other = make_privileged(User.objects.create_user("other", "other@test.com", "bar"))

        self.assertFalse(has_privileged_access(other, self.project))

        self.project.privileged_users.add(other)

        self.assertTrue(has_privileged_access(other, self.project))

    def test_a_grant_to_a_user_who_is_not_privileged_is_inert(self):
        other = User.objects.create_user("other", "other@test.com", "bar")
        self.project.privileged_users.add(other)

        self.assertFalse(has_privileged_access(other, self.project))
