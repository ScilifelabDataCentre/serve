from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from common.admin import UserAdmin
from common.models import UserProfile

User = get_user_model()

PASSWORD = "tesT12345@"


class PrivilegedUserAdminFormTestCase(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser("admin@test.com", "admin@test.com", PASSWORD)
        self.user = User.objects.create_user("member@test.com", "member@test.com", PASSWORD)
        self.profile = UserProfile.objects.create(user=self.user)

        self.client = Client()
        self.client.force_login(self.admin)
        self.change_url = f"/admin/auth/user/{self.user.pk}/change/"

    def form_data(self, **overrides):
        data = {
            "username": self.user.username,
            "email": self.user.email,
            "first_name": "",
            "last_name": "",
            "is_active": "on",
            "date_joined_0": self.user.date_joined.strftime("%Y-%m-%d"),
            "date_joined_1": self.user.date_joined.strftime("%H:%M:%S"),
            "userprofile-TOTAL_FORMS": "1",
            "userprofile-INITIAL_FORMS": "1",
            "userprofile-MIN_NUM_FORMS": "0",
            "userprofile-MAX_NUM_FORMS": "1",
            "userprofile-0-id": str(self.profile.pk),
            "userprofile-0-user": str(self.user.pk),
            "userprofile-0-affiliations": "[]",
            "userprofile-0-note": self.profile.note,
            "userprofile-0-why_account_needed": self.profile.why_account_needed,
            "userprofile-0-orcid_id": self.profile.orcid_id,
            "emailverificationtable-TOTAL_FORMS": "0",
            "emailverificationtable-INITIAL_FORMS": "0",
            "emailverificationtable-MIN_NUM_FORMS": "0",
            "emailverificationtable-MAX_NUM_FORMS": "1",
        }
        data.update(overrides)

        return data

    def test_the_flag_sits_after_superuser_status_in_the_permissions_fieldset(self):
        permissions = dict((name, options) for name, options in UserAdmin.fieldsets)["Permissions"]

        self.assertEqual(
            permissions["fields"].index("is_privileged"),
            permissions["fields"].index("is_superuser") + 1,
        )

    def test_the_box_writes_through_to_the_profile_both_ways(self):
        self.assertEqual(self.client.post(self.change_url, self.form_data(is_privileged="on")).status_code, 302)
        self.assertTrue(UserProfile.objects.get(user=self.user).is_privileged)

        self.assertEqual(self.client.post(self.change_url, self.form_data()).status_code, 302)
        self.assertFalse(UserProfile.objects.get(user=self.user).is_privileged)

    def test_editing_the_profile_inline_does_not_revert_the_flag(self):
        response = self.client.post(
            self.change_url,
            self.form_data(is_privileged="on", **{"userprofile-0-note": "Bioimage facility staff"}),
        )

        self.assertEqual(response.status_code, 302)

        profile = UserProfile.objects.get(user=self.user)
        self.assertEqual(profile.note, "Bioimage facility staff")
        self.assertTrue(profile.is_privileged)

    def test_an_admin_is_not_shown_as_privileged_in_the_list(self):
        self.assertFalse(UserAdmin(User, None).get_is_privileged(self.admin))
