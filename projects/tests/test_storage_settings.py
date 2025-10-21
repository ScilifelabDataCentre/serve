from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.test import TestCase
from django.urls import reverse

from apps.models import Apps, VolumeInstance
from projects.models import PersistentVolumeMountPath, Project

User = get_user_model()

TEST_USER = {"username": "foo1", "email": "foo@test.com", "password": "bar"}
TEST_SUPERUSER = {"username": "superuser", "email": "superuser@test.com", "password": "bar"}


class StorageSettingsTestCase(TestCase):
    def setUp(self):
        # Create regular user and superuser
        self.user = User.objects.create_user(TEST_USER["username"], TEST_USER["email"], TEST_USER["password"])
        self.superuser = User.objects.create_superuser(
            TEST_SUPERUSER["username"], TEST_SUPERUSER["email"], TEST_SUPERUSER["password"]
        )

        # Create a test project
        self.project = Project.objects.create_project(name="test-storage", owner=self.user, description="")

        # Create a test app
        self.app = Apps.objects.create(name="Test App", slug="test-app", description="Test app for storage settings")

        # Create a volume instance
        self.volume = VolumeInstance.objects.create(name="test-volume", project=self.project, size=10, app=self.app)

        # Create mount paths explicitly
        self.default_mount_path = PersistentVolumeMountPath.objects.create(
            volume=self.volume, mount_path="/home/data", is_default=True
        )
        self.shiny_mount_path = PersistentVolumeMountPath.objects.create(
            volume=self.volume, mount_path="/srv/shiny-server/data/", is_default=False
        )

    def test_storage_settings_access(self):
        """Test access to storage settings page"""
        url = reverse("projects:settings", kwargs={"project_slug": self.project.slug})

        # Test unauthenticated access
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)  # Redirects to login

        # Test authenticated regular user access
        self.client.login(username=TEST_USER["email"], password=TEST_USER["password"])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        # Test superuser access
        self.client.login(username=TEST_SUPERUSER["email"], password=TEST_SUPERUSER["password"])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_update_storage_settings_valid_paths(self):
        """Test updating storage settings with valid paths"""
        self.client.login(username=TEST_USER["email"], password=TEST_USER["password"])

        url = reverse("projects:update_storage_settings", kwargs={"project_slug": self.project.slug})

        new_paths = ["/home/data", "/home/project", "/srv/data"]  # Keep default

        response = self.client.post(url, {f"paths_{self.volume.id}": new_paths}, follow=True)

        self.assertEqual(response.status_code, 200)
        messages = list(get_messages(response.wsgi_request))
        self.assertEqual(len(messages), 1)
        self.assertIn("Storage settings saved", str(messages[0]))

        # Verify paths were updated
        updated_paths = list(self.volume.mount_paths.values_list("mount_path", flat=True))
        self.assertEqual(len(updated_paths), 3)
        for path in new_paths:
            self.assertIn(path, updated_paths)

    def test_update_storage_settings_invalid_paths(self):
        """Test updating storage settings with invalid paths"""
        self.client.login(username=TEST_USER["email"], password=TEST_USER["password"])

        url = reverse("projects:update_storage_settings", kwargs={"project_slug": self.project.slug})

        invalid_paths = [
            "/home/data",  # Keep default
            "/invalid/path",  # Invalid - doesn't start with /home or /srv
            "/srv/data",
        ]

        response = self.client.post(url, {f"paths_{self.volume.id}": invalid_paths}, follow=True)

        self.assertEqual(response.status_code, 200)
        messages = list(get_messages(response.wsgi_request))
        self.assertEqual(len(messages), 1)
        self.assertIn("Path /invalid/path must start with", str(messages[0]))

        # Verify paths were not updated
        updated_paths = list(self.volume.mount_paths.values_list("mount_path", flat=True))
        self.assertEqual(len(updated_paths), 2)  # Still has original paths
        self.assertIn("/home/data", updated_paths)
        self.assertIn("/srv/shiny-server/data/", updated_paths)

    def test_update_storage_settings_empty_paths(self):
        """Test updating storage settings with empty paths"""
        self.client.login(username=TEST_USER["email"], password=TEST_USER["password"])

        url = reverse("projects:update_storage_settings", kwargs={"project_slug": self.project.slug})

        response = self.client.post(url, {f"paths_{self.volume.id}": [""]}, follow=True)

        self.assertEqual(response.status_code, 200)
        messages = list(get_messages(response.wsgi_request))
        self.assertEqual(len(messages), 1)
        self.assertIn("Storage settings saved", str(messages[0]))

        # Verify only default path remains
        updated_paths = list(self.volume.mount_paths.values_list("mount_path", flat=True))
        self.assertEqual(len(updated_paths), 1)
        self.assertEqual(updated_paths[0], "/home/data")  # Default path remains

    def test_update_storage_settings_duplicate_paths(self):
        """Test updating storage settings with duplicate paths"""
        self.client.login(username=TEST_USER["email"], password=TEST_USER["password"])

        url = reverse("projects:update_storage_settings", kwargs={"project_slug": self.project.slug})

        duplicate_paths = ["/home/data", "/home/data", "/srv/data", "/srv/data"]  # Duplicate  # Duplicate

        response = self.client.post(url, {f"paths_{self.volume.id}": duplicate_paths}, follow=True)

        self.assertEqual(response.status_code, 200)
        messages = list(get_messages(response.wsgi_request))
        self.assertEqual(len(messages), 1)
        self.assertIn("Storage settings saved", str(messages[0]))

        # Verify duplicates were removed
        updated_paths = list(self.volume.mount_paths.values_list("mount_path", flat=True))
        self.assertEqual(len(updated_paths), 2)
        self.assertIn("/home/data", updated_paths)
        self.assertIn("/srv/data", updated_paths)

    def test_update_storage_settings_path_normalization(self):
        """Test path normalization in storage settings"""
        self.client.login(username=TEST_USER["email"], password=TEST_USER["password"])

        url = reverse("projects:update_storage_settings", kwargs={"project_slug": self.project.slug})

        paths = ["/home/data/", "/home/Project Data", "/srv/data/"]  # Trailing slash  # Spaces  # Trailing slash

        response = self.client.post(url, {f"paths_{self.volume.id}": paths}, follow=True)

        self.assertEqual(response.status_code, 200)
        messages = list(get_messages(response.wsgi_request))
        self.assertEqual(len(messages), 1)
        self.assertIn("Storage settings saved", str(messages[0]))

        # Verify paths were normalized
        updated_paths = list(self.volume.mount_paths.values_list("mount_path", flat=True))
        self.assertEqual(len(updated_paths), 3)
        self.assertIn("/home/data", updated_paths)
        self.assertIn("/home/projectdata", updated_paths)
        self.assertIn("/srv/data", updated_paths)

    def test_invalid_path_prefix(self):
        """Test that paths must start with /home or /srv"""
        self.client.login(username=TEST_USER["email"], password=TEST_USER["password"])

        url = reverse("projects:update_storage_settings", kwargs={"project_slug": self.project.slug})

        invalid_paths = [
            "/home/data",  # Valid
            "/var/data",  # Invalid - wrong prefix
            "/etc/data",  # Invalid - wrong prefix
        ]

        response = self.client.post(url, {f"paths_{self.volume.id}": invalid_paths}, follow=True)

        self.assertEqual(response.status_code, 200)
        messages = list(get_messages(response.wsgi_request))
        self.assertEqual(len(messages), 1)
        self.assertIn("Path /var/data must start with", str(messages[0]))

        # Verify paths were not updated
        updated_paths = list(self.volume.mount_paths.values_list("mount_path", flat=True))
        self.assertEqual(len(updated_paths), 2)  # Still has original paths
        self.assertIn("/home/data", updated_paths)
        self.assertIn("/srv/shiny-server/data/", updated_paths)

    @patch("apps.helpers.create_instance_from_form")
    def test_increase_volume_size_success(self, mock_create_instance):
        """Test successful volume size increase to 5GB"""
        self.client.login(username=TEST_USER["email"], password=TEST_USER["password"])

        # Create a volume with size less than 5GB
        small_volume = VolumeInstance.objects.create(name="small-volume", project=self.project, size=2, app=self.app)

        url = reverse(
            "projects:increase_volume_size", kwargs={"project_slug": self.project.slug, "volume_id": small_volume.id}
        )

        response = self.client.post(url)
        self.assertEqual(response.status_code, 200, response.content)

        # Verify response content
        self.assertJSONEqual(
            response.content.decode(), {"message": "Volume size increased to 5GB and redeployment initiated"}
        )

        # Verify volume size was updated
        small_volume.refresh_from_db()
        self.assertEqual(small_volume.size, 5)

    def test_increase_volume_size_already_at_limit(self):
        """Test volume size increase when already at or above 5GB"""
        self.client.login(username=TEST_USER["email"], password=TEST_USER["password"])

        # Create a volume with size already at 5GB
        large_volume = VolumeInstance.objects.create(name="large-volume", project=self.project, size=5, app=self.app)

        url = reverse(
            "projects:increase_volume_size", kwargs={"project_slug": self.project.slug, "volume_id": large_volume.id}
        )

        response = self.client.post(url)
        self.assertEqual(response.status_code, 400)

        # Verify response content
        self.assertJSONEqual(response.content.decode(), {"error": "Volume size is already 5GB or larger"})

        # Verify volume size was not changed
        large_volume.refresh_from_db()
        self.assertEqual(large_volume.size, 5)

    def test_increase_volume_size_unauthorized(self):
        """Test volume size increase with unauthorized user"""
        # Create another user and project
        other_user = User.objects.create_user("other", "other@test.com", "password")
        other_project = Project.objects.create_project(name="other-project", owner=other_user, description="")

        # Create a volume in the other project
        other_volume = VolumeInstance.objects.create(name="other-volume", project=other_project, size=2, app=self.app)

        # Login as original user
        self.client.login(username=TEST_USER["email"], password=TEST_USER["password"])

        url = reverse(
            "projects:increase_volume_size", kwargs={"project_slug": other_project.slug, "volume_id": other_volume.id}
        )

        response = self.client.post(url)
        self.assertEqual(response.status_code, 403)  # Forbidden

        # Verify volume size was not changed
        other_volume.refresh_from_db()
        self.assertEqual(other_volume.size, 2)

    def test_increase_volume_size_nonexistent(self):
        """Test volume size increase with non-existent volume"""
        self.client.login(username=TEST_USER["email"], password=TEST_USER["password"])

        url = reverse(
            "projects:increase_volume_size",
            kwargs={"project_slug": self.project.slug, "volume_id": 99999},  # Non-existent ID
        )

        response = self.client.post(url)
        self.assertEqual(response.status_code, 404)  # Not Found

    def test_increase_volume_size_get_method(self):
        """Test volume size increase with GET method instead of POST"""
        self.client.login(username=TEST_USER["email"], password=TEST_USER["password"])

        url = reverse(
            "projects:increase_volume_size", kwargs={"project_slug": self.project.slug, "volume_id": self.volume.id}
        )

        response = self.client.get(url)
        self.assertEqual(response.status_code, 400)  # Bad Request

    def test_path_validation_rules(self):
        """Test various path validation rules"""
        self.client.login(username=TEST_USER["email"], password=TEST_USER["password"])

        url = reverse("projects:update_storage_settings", kwargs={"project_slug": self.project.slug})

        test_cases = [
            # Invalid paths
            ("home/data", 'Path home/data must start with "/home" or "/srv"'),
            ("srv/data", 'Path srv/data must start with "/home" or "/srv"'),
            ("/usr/data", 'Path /usr/data must start with "/home" or "/srv"'),
            ("/var/log", 'Path /var/log must start with "/home" or "/srv"'),
            # Valid paths - these should not trigger errors
            ("/home/data", None),
            ("/home/project/data", None),
            ("/srv/data", None),
            ("/srv/project/data", None),
            ("/home/user123", None),
            ("/srv/app-data", None),
        ]

        for test_path, expected_error in test_cases:
            response = self.client.post(
                url, {f"paths_{self.volume.id}": ["/home/data", test_path]}, follow=True  # Include default path
            )

            messages = list(get_messages(response.wsgi_request))

            if expected_error:
                self.assertEqual(len(messages), 1)
                self.assertIn(expected_error, str(messages[0]))

                # Verify paths were not updated
                updated_paths = list(self.volume.mount_paths.values_list("mount_path", flat=True))
                self.assertEqual(len(updated_paths), 2)  # Still has original paths
                self.assertIn("/home/data", updated_paths)
                self.assertIn("/srv/shiny-server/data/", updated_paths)
            else:
                # For valid paths, verify they were added
                if len(messages) > 0:
                    self.assertIn("Storage settings saved", str(messages[0]))
                updated_paths = list(self.volume.mount_paths.values_list("mount_path", flat=True))
                self.assertIn(test_path, updated_paths)
