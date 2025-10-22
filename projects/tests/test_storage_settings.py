from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.test import TestCase, override_settings
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


class StorageRequestTestCase(TestCase):
    """Test cases for storage request functionality"""

    def setUp(self):
        # Create regular user and superuser
        self.user = User.objects.create_user(
            TEST_USER["username"], TEST_USER["email"], TEST_USER["password"], first_name="Test", last_name="User"
        )
        self.project = Project.objects.create_project(name="test-storage", owner=self.user, description="")
        self.app = Apps.objects.create(name="Test App", slug="test-app", description="Test app for storage")
        self.volume = VolumeInstance.objects.create(name="test-volume", project=self.project, size=10, app=self.app)

    def test_request_storage_get(self):
        """Test GET request for storage request modal"""
        self.client.login(username=TEST_USER["email"], password=TEST_USER["password"])
        url = reverse(
            "projects:request_storage", kwargs={"project_slug": self.project.slug, "volume_id": self.volume.id}
        )

        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "projects/partials/settings/storage_request_modal.html")

        # Test modal content
        self.assertContains(response, "Request Additional Storage")
        self.assertContains(response, str(self.volume.size))
        self.assertContains(response, 'min="1"')  # Only lower limit constraint
        self.assertContains(response, 'type="number"')

        # Test reason type options
        self.assertContains(response, 'value="project_requirements">Project requirements increased</option>')
        self.assertContains(response, 'value="tissuumaps">I require more storage for TissUUmaps</option>')
        self.assertContains(response, 'value="future_needs">I will need more data in the future</option>')
        self.assertContains(response, 'value="other">Other</option>')

    def test_request_storage_post_valid(self):
        """Test successful storage request submission with different reason types and sizes"""
        self.client.login(username=TEST_USER["email"], password=TEST_USER["password"])
        url = reverse(
            "projects:request_storage", kwargs={"project_slug": self.project.slug, "volume_id": self.volume.id}
        )

        test_cases = [
            {
                "data": {
                    "requested_size": "500",  # Test large storage request (no upper limit)
                    "request_reason_type": "project_requirements",
                },
                "expected_reason": "Project requirements increased",
            },
            {
                "data": {
                    "requested_size": "30",
                    "request_reason_type": "tissuumaps",
                },
                "expected_reason": "I require more storage for TissUUmaps",
            },
            {
                "data": {
                    "requested_size": "40",
                    "request_reason_type": "future_needs",
                },
                "expected_reason": "I will need more data in the future",
            },
            {
                "data": {
                    "requested_size": "50",
                    "request_reason_type": "other",
                    "request_reason": "Custom reason here",
                },
                "expected_reason": "Custom reason here",
            },
        ]

        for test_case in test_cases:
            with patch("projects.views.send_email_task.delay") as mock_email:
                response = self.client.post(url, test_case["data"])

                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "success")
                mock_email.assert_called_once()

                # Verify email content
                call_args = mock_email.call_args[1]
                self.assertIn("Storage Increase Request", call_args["subject"])
                self.assertIn("test-storage", call_args["subject"])
                self.assertIn(test_case["data"]["requested_size"], call_args["message"])
                self.assertIn(test_case["expected_reason"], call_args["message"])
                self.assertIn("Test User", call_args["message"])  # Full name
                self.assertIn(TEST_USER["email"], call_args["message"])

    def test_request_storage_post_invalid_size(self):
        """Test storage request with invalid size"""
        self.client.login(username=TEST_USER["email"], password=TEST_USER["password"])
        url = reverse(
            "projects:request_storage", kwargs={"project_slug": self.project.slug, "volume_id": self.volume.id}
        )

        test_cases = [
            # Test size validation
            {
                "data": {"requested_size": "0", "request_reason_type": "project_requirements"},
                "expected_error": "Requested size must be no less than 1 GB",
            },
            {
                "data": {"requested_size": "-5", "request_reason_type": "project_requirements"},
                "expected_error": "Requested size must be no less than 1 GB",
            },
            {
                "data": {"requested_size": "abc", "request_reason_type": "project_requirements"},
                "expected_error": "Requested size must be no less than 1 GB",
            },
            {
                "data": {"requested_size": "1.5", "request_reason_type": "project_requirements"},
                "expected_error": "Requested size must be no less than 1 GB",
            },
            # Test missing fields
            {
                "data": {"request_reason_type": "project_requirements"},
                "expected_error": "Please provide both the requested size and reason type",
            },
            {
                "data": {"requested_size": "20"},
                "expected_error": "Please provide both the requested size and reason type",
            },
            # Test other reason type without custom reason
            {
                "data": {"requested_size": "20", "request_reason_type": "other"},
                "expected_error": "Please provide a custom reason when selecting &#x27;Other&#x27;.",
            },
            # Test empty strings
            {
                "data": {"requested_size": "", "request_reason_type": "project_requirements"},
                "expected_error": "Please provide both the requested size and reason type",
            },
            {
                "data": {"requested_size": "20", "request_reason_type": ""},
                "expected_error": "Please provide both the requested size and reason type",
            },
        ]

        for test_case in test_cases:
            with patch("projects.views.send_email_task.delay") as mock_email:
                response = self.client.post(url, test_case["data"])

                self.assertEqual(response.status_code, 200)
                self.assertContains(response, test_case["expected_error"])
                mock_email.assert_not_called()

    def test_request_storage_post_reason_types(self):
        """Test storage request with different reason types"""
        self.client.login(username=TEST_USER["email"], password=TEST_USER["password"])
        url = reverse(
            "projects:request_storage", kwargs={"project_slug": self.project.slug, "volume_id": self.volume.id}
        )

        test_cases = [
            # Valid predefined reasons (no custom reason needed)
            {
                "data": {"requested_size": "20", "request_reason_type": "project_requirements"},
                "expected_success": True,
                "expected_reason": "Project requirements increased",
            },
            {
                "data": {"requested_size": "20", "request_reason_type": "tissuumaps"},
                "expected_success": True,
                "expected_reason": "I require more storage for TissUUmaps",
            },
            {
                "data": {"requested_size": "20", "request_reason_type": "future_needs"},
                "expected_success": True,
                "expected_reason": "I will need more data in the future",
            },
            # Other with custom reason
            {
                "data": {
                    "requested_size": "20",
                    "request_reason_type": "other",
                    "request_reason": "Custom reason here",
                },
                "expected_success": True,
                "expected_reason": "Custom reason here",
            },
            # Invalid cases
            {
                "data": {"requested_size": "20", "request_reason_type": "other"},
                "expected_success": False,
                "expected_error": "Please provide a custom reason when selecting &#x27;Other&#x27;.",
            },
            {
                "data": {"requested_size": "20"},
                "expected_success": False,
                "expected_error": "Please provide both the requested size and reason type",
            },
        ]

        for test_case in test_cases:
            with patch("projects.views.send_email_task.delay") as mock_email:
                response = self.client.post(url, test_case["data"])

                if test_case["expected_success"]:
                    self.assertEqual(response.status_code, 200)
                    self.assertContains(response, "success")
                    mock_email.assert_called_once()

                    # Verify the correct reason is used in the email
                    call_args = mock_email.call_args[1]
                    self.assertIn(test_case["expected_reason"], call_args["message"])
                else:
                    self.assertEqual(response.status_code, 200)
                    self.assertContains(response, test_case["expected_error"])
                    mock_email.assert_not_called()

    def test_request_storage_unauthorized(self):
        """Test storage request from unauthorized user"""
        url = reverse(
            "projects:request_storage", kwargs={"project_slug": self.project.slug, "volume_id": self.volume.id}
        )

        # Test unauthenticated access
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)  # Redirects to login

        response = self.client.post(url, {"requested_size": "20", "request_reason": "Need more storage"})
        self.assertEqual(response.status_code, 302)  # Redirects to login

        # Test with different user
        other_user = User.objects.create_user("other", "other@test.com", "password")
        self.client.login(username="other@test.com", password="password")

        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)  # Forbidden

        response = self.client.post(url, {"requested_size": "20", "request_reason": "Need more storage"})
        self.assertEqual(response.status_code, 403)  # Forbidden

    def test_request_storage_invalid_volume(self):
        """Test storage request for non-existent volume"""
        self.client.login(username=TEST_USER["email"], password=TEST_USER["password"])
        url = reverse(
            "projects:request_storage",
            kwargs={"project_slug": self.project.slug, "volume_id": 99999},  # Non-existent volume
        )

        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

        response = self.client.post(url, {"requested_size": "20", "request_reason": "Need more storage"})
        self.assertEqual(response.status_code, 404)

    @override_settings(DEFAULT_FROM_EMAIL="serve@test.com", EMAIL_FROM="noreply@test.com")
    def test_request_storage_email_settings_and_errors(self):
        """Test email settings and error handling"""
        self.client.login(username=TEST_USER["email"], password=TEST_USER["password"])
        url = reverse(
            "projects:request_storage", kwargs={"project_slug": self.project.slug, "volume_id": self.volume.id}
        )

        # Test successful email with correct settings
        with patch("projects.views.send_email_task.delay") as mock_email:
            response = self.client.post(url, {"requested_size": "20", "request_reason_type": "project_requirements"})

            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "success")
            mock_email.assert_called_once()
            call_args = mock_email.call_args[1]
            self.assertEqual(call_args["recipient_list"], ["serve@test.com"])
            self.assertEqual(call_args["from_email"], "noreply@test.com")

            # Verify email template content
            self.assertIn(f"Project: {self.project.name}", call_args["subject"])
            self.assertIn("Requested Additional Size: 20 GB", call_args["message"])
            self.assertIn("Project requirements increased", call_args["message"])
            self.assertIn(f"Name: {self.user.get_full_name()}", call_args["message"])
            self.assertIn(f"Username: {self.user.username}", call_args["message"])
            self.assertIn(f"Email: {self.user.email}", call_args["message"])

        # Test email sending failure
        with patch("projects.views.send_email_task.delay", side_effect=Exception("Email error")):
            response = self.client.post(url, {"requested_size": "20", "request_reason_type": "project_requirements"})

            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "Failed to submit your request")
            self.assertContains(response, "Please try again later")
