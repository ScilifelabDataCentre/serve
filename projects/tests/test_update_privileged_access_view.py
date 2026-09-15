from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from guardian.shortcuts import assign_perm

from common.models import UserProfile

from ..models import Project

User = get_user_model()

PASSWORD = "tesT12345@"


def make_privileged(user):
    profile, _ = UserProfile.objects.get_or_create(user=user)
    profile.is_privileged = True
    profile.save()

    return User.objects.get(pk=user.pk)


def add_member(project, user):
    project.authorized.add(user)
    assign_perm("can_view_project", user, project)


class UpdatePrivilegedAccessViewTestCase(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("owner@test.com", "owner@test.com", PASSWORD)
        self.project = Project.objects.create_project(name="access-proj", owner=self.owner, description="")

        self.facility = make_privileged(User.objects.create_user("facility@test.com", "facility@test.com", PASSWORD))
        add_member(self.project, self.facility)

        self.url = f"/projects/{self.project.slug}/project/access/privileged/"

    def login(self, email):
        client = Client()
        self.assertEqual(client.post("/accounts/login/", {"username": email, "password": PASSWORD}).status_code, 302)

        return client

    def test_the_owner_can_grant_and_revoke(self):
        client = self.login(self.owner.email)

        self.assertEqual(
            client.post(self.url, {"selected_user": self.facility.username, "action": "grant"}).status_code, 302
        )
        self.assertIn(self.facility, self.project.privileged_users.all())

        self.assertEqual(
            client.post(self.url, {"selected_user": self.facility.username, "action": "revoke"}).status_code, 302
        )
        self.assertNotIn(self.facility, self.project.privileged_users.all())

    def test_a_member_cannot_grant_it_to_themselves(self):
        response = self.login(self.facility.email).post(
            self.url, {"selected_user": self.facility.username, "action": "grant"}
        )

        self.assertEqual(response.status_code, 403)
        self.assertNotIn(self.facility, self.project.privileged_users.all())

    def test_a_granted_member_still_cannot_grant_others(self):
        self.project.privileged_users.add(self.facility)
        other = make_privileged(User.objects.create_user("other@test.com", "other@test.com", PASSWORD))
        add_member(self.project, other)

        response = self.login(self.facility.email).post(self.url, {"selected_user": other.username, "action": "grant"})

        self.assertEqual(response.status_code, 403)
        self.assertNotIn(other, self.project.privileged_users.all())

    def test_a_user_who_is_not_privileged_cannot_be_granted(self):
        plain = User.objects.create_user("plain@test.com", "plain@test.com", PASSWORD)
        add_member(self.project, plain)

        response = self.login(self.owner.email).post(self.url, {"selected_user": plain.username, "action": "grant"})

        self.assertEqual(response.status_code, 302)
        self.assertNotIn(plain, self.project.privileged_users.all())
