from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.test import TestCase
from django.urls import reverse

from apps.models import Apps, VolumeInstance
from projects.models import Project, PersistentVolumeMountPath

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
        self.app = Apps.objects.create(
            name="Test App",
            slug="test-app",
            description="Test app for storage settings"
        )
        
        # Create a volume instance
        self.volume = VolumeInstance.objects.create(
            name="test-volume",
            project=self.project,
            size=10,
            app=self.app
        )
        
        # Create mount paths explicitly
        self.default_mount_path = PersistentVolumeMountPath.objects.create(
            volume=self.volume,
            mount_path="/home/data",
            is_default=True
        )
        self.shiny_mount_path = PersistentVolumeMountPath.objects.create(
            volume=self.volume,
            mount_path="/srv/shiny-server/data/",
            is_default=False
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
        
        new_paths = [
            "/home/data",  # Keep default
            "/home/project",
            "/srv/data"
        ]
        
        response = self.client.post(url, {
            f"paths_{self.volume.id}": new_paths
        }, follow=True)
        
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
            "/srv/data"
        ]
        
        response = self.client.post(url, {
            f"paths_{self.volume.id}": invalid_paths
        }, follow=True)
        
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
        
        response = self.client.post(url, {
            f"paths_{self.volume.id}": [""]
        }, follow=True)
        
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
        
        duplicate_paths = [
            "/home/data",
            "/home/data",  # Duplicate
            "/srv/data",
            "/srv/data"  # Duplicate
        ]
        
        response = self.client.post(url, {
            f"paths_{self.volume.id}": duplicate_paths
        }, follow=True)
        
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
        
        paths = [
            "/home/data/",  # Trailing slash
            "/home/Project Data",  # Spaces
            "/srv/data/"  # Trailing slash
        ]
        
        response = self.client.post(url, {
            f"paths_{self.volume.id}": paths
        }, follow=True)
        
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
            "/var/data",   # Invalid - wrong prefix
            "/etc/data"    # Invalid - wrong prefix
        ]
        
        response = self.client.post(url, {
            f"paths_{self.volume.id}": invalid_paths
        }, follow=True)
        
        self.assertEqual(response.status_code, 200)
        messages = list(get_messages(response.wsgi_request))
        self.assertEqual(len(messages), 1)
        self.assertIn("Path /var/data must start with", str(messages[0]))
        
        # Verify paths were not updated
        updated_paths = list(self.volume.mount_paths.values_list("mount_path", flat=True))
        self.assertEqual(len(updated_paths), 2)  # Still has original paths
        self.assertIn("/home/data", updated_paths)
        self.assertIn("/srv/shiny-server/data/", updated_paths)

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
            ("/srv/app-data", None)
        ]
        
        for test_path, expected_error in test_cases:
            response = self.client.post(url, {
                f"paths_{self.volume.id}": ["/home/data", test_path]  # Include default path
            }, follow=True)
            
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
