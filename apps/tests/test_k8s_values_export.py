"""Unit tests for k8s values export and helm command generation functions."""

from unittest.mock import MagicMock, patch

import pytest
import yaml
from django.contrib.auth import get_user_model
from django.test import TestCase

from projects.models import Flavor, Project

from ..helpers import (
    deep_merge_dict,
    export_k8s_values_to_yaml,
    generate_helm_install_command,
    get_merged_k8s_values,
)
from ..models import Apps, BaseAppInstance, DashInstance, K8sUserAppStatus, Subdomain

User = get_user_model()


class DeepMergeDictTestCase(TestCase):
    """Test cases for deep_merge_dict function."""

    def test_simple_merge(self):
        """Test merging two simple dictionaries."""
        base = {"a": 1, "b": 2}
        override = {"b": 3, "c": 4}
        result = deep_merge_dict(base, override)
        expected = {"a": 1, "b": 3, "c": 4}
        self.assertEqual(result, expected)

    def test_nested_merge(self):
        """Test merging nested dictionaries."""
        base = {"a": {"x": 1, "y": 2}, "b": 3}
        override = {"a": {"y": 4, "z": 5}, "c": 6}
        result = deep_merge_dict(base, override)
        expected = {"a": {"x": 1, "y": 4, "z": 5}, "b": 3, "c": 6}
        self.assertEqual(result, expected)

    def test_deeply_nested_merge(self):
        """Test merging deeply nested dictionaries."""
        base = {"level1": {"level2": {"level3": {"a": 1, "b": 2}}}}
        override = {"level1": {"level2": {"level3": {"b": 3, "c": 4}}}}
        result = deep_merge_dict(base, override)
        expected = {"level1": {"level2": {"level3": {"a": 1, "b": 3, "c": 4}}}}
        self.assertEqual(result, expected)

    def test_override_replaces_non_dict_values(self):
        """Test that override replaces non-dict values."""
        base = {"a": {"x": 1}, "b": 2}
        override = {"a": "replaced", "b": 3}
        result = deep_merge_dict(base, override)
        expected = {"a": "replaced", "b": 3}
        self.assertEqual(result, expected)

    def test_empty_base(self):
        """Test merging with empty base dictionary."""
        base = {}
        override = {"a": 1, "b": 2}
        result = deep_merge_dict(base, override)
        self.assertEqual(result, override)

    def test_empty_override(self):
        """Test merging with empty override dictionary."""
        base = {"a": 1, "b": 2}
        override = {}
        result = deep_merge_dict(base, override)
        self.assertEqual(result, base)

    def test_base_not_modified(self):
        """Test that base dictionary is not modified."""
        base = {"a": 1, "b": 2}
        override = {"b": 3}
        original_base = base.copy()
        deep_merge_dict(base, override)
        self.assertEqual(base, original_base)


class GetMergedK8sValuesTestCase(TestCase):
    """Test cases for get_merged_k8s_values function."""

    def setUp(self):
        """Set up test fixtures."""
        self.user = User.objects.create_user("testuser", "test@example.com", "password")
        self.project = Project.objects.create_project(name="test-project", owner=self.user, description="")
        self.app = Apps.objects.create(name="Test App", slug="testapp")
        self.subdomain = Subdomain.objects.create(subdomain="test-subdomain", project=self.project)
        self.instance = DashInstance.objects.create(
            app=self.app,
            project=self.project,
            owner=self.user,
            name="test-instance",
            subdomain=self.subdomain,
            chart="test-chart:1.0.0",
        )

    def test_get_merged_k8s_values_without_override(self):
        """Test getting merged values without override."""
        # Set k8s_values
        self.instance.k8s_values = {"name": "test", "namespace": "default"}
        self.instance.save()

        result = get_merged_k8s_values(self.instance, ensure_up_to_date=False)
        self.assertIn("name", result)
        self.assertEqual(result["name"], "test")

    def test_get_merged_k8s_values_with_override(self):
        """Test getting merged values with override."""
        self.instance.k8s_values = {"name": "test", "namespace": "default", "config": {"port": 8000}}
        self.instance.k8s_values_override = {"config": {"port": 9000, "host": "localhost"}}
        self.instance.save()

        result = get_merged_k8s_values(self.instance, ensure_up_to_date=False)
        self.assertEqual(result["config"]["port"], 9000)  # Override takes precedence
        self.assertEqual(result["config"]["host"], "localhost")  # New key from override
        self.assertEqual(result["name"], "test")  # Base value preserved

    def test_get_merged_k8s_values_ensure_up_to_date(self):
        """Test that ensure_up_to_date calls set_k8s_values."""
        with patch.object(self.instance, "set_k8s_values") as mock_set:
            get_merged_k8s_values(self.instance, ensure_up_to_date=True)
            mock_set.assert_called_once()

    def test_get_merged_k8s_values_no_ensure_up_to_date(self):
        """Test that ensure_up_to_date=False doesn't call set_k8s_values."""
        with patch.object(self.instance, "set_k8s_values") as mock_set:
            get_merged_k8s_values(self.instance, ensure_up_to_date=False)
            mock_set.assert_not_called()

    def test_get_merged_k8s_values_none_k8s_values(self):
        """Test handling when k8s_values is None."""
        self.instance.k8s_values = None
        self.instance.save()

        result = get_merged_k8s_values(self.instance, ensure_up_to_date=False)
        self.assertEqual(result, {})


class GenerateHelmInstallCommandTestCase(TestCase):
    """Test cases for generate_helm_install_command function."""

    def setUp(self):
        """Set up test fixtures."""
        self.user = User.objects.create_user("testuser", "test@example.com", "password")
        self.project = Project.objects.create_project(name="test-project", owner=self.user, description="")
        self.app = Apps.objects.create(name="Test App", slug="testapp")
        self.subdomain = Subdomain.objects.create(subdomain="test-subdomain", project=self.project)
        self.instance = DashInstance.objects.create(
            app=self.app,
            project=self.project,
            owner=self.user,
            name="test-instance",
            subdomain=self.subdomain,
            chart="test-chart:1.0.0",
        )
        # Set up k8s_values
        self.instance.k8s_values = {
            "subdomain": "test-subdomain",
            "namespace": "test-namespace",
        }
        self.instance.save()

    def test_generate_helm_install_command_from_instance(self):
        """Test generating command from instance."""
        command = generate_helm_install_command(instance=self.instance)
        self.assertIn("helm upgrade", command)
        self.assertIn("test-subdomain", command)
        self.assertIn("test-namespace", command)
        self.assertIn("test-chart:1.0.0", command)
        self.assertIn("-f <values-file>", command)

    def test_generate_helm_install_command_from_parameters(self):
        """Test generating command from direct parameters."""
        command = generate_helm_install_command(
            release_name="my-release",
            chart="my-chart",
            namespace="my-namespace",
            values_file="/path/to/values.yaml",
        )
        self.assertIn("helm upgrade", command)
        self.assertIn("my-release", command)
        self.assertIn("my-chart", command)
        self.assertIn("my-namespace", command)
        self.assertIn("-f /path/to/values.yaml", command)

    def test_generate_helm_install_command_with_version(self):
        """Test generating command with version."""
        command = generate_helm_install_command(
            release_name="my-release",
            chart="my-chart",
            namespace="my-namespace",
            version="1.2.3",
        )
        self.assertIn("--version 1.2.3", command)
        self.assertIn("--repository-cache", command)

    def test_generate_helm_install_command_volumek8s_no_force(self):
        """Test that volumek8s charts don't use --force flag."""
        command = generate_helm_install_command(
            release_name="my-release",
            chart="volumek8s:1.0.0",
            namespace="my-namespace",
        )
        self.assertIn("helm upgrade --install", command)
        self.assertNotIn("--force", command)

    def test_generate_helm_install_command_non_volumek8s_with_force(self):
        """Test that non-volumek8s charts use --force flag."""
        command = generate_helm_install_command(
            release_name="my-release",
            chart="regular-chart:1.0.0",
            namespace="my-namespace",
        )
        self.assertIn("helm upgrade --force --install", command)

    def test_generate_helm_install_command_ghcr_chart(self):
        """Test generating command for GHCR chart."""
        command = generate_helm_install_command(
            release_name="my-release",
            chart="ghcr.io/owner/repo:v1.0.0",
            namespace="my-namespace",
        )
        self.assertIn("oci://ghcr.io/owner/repo", command)
        self.assertIn("--version v1.0.0", command)
        self.assertIn("--repository-cache", command)

    def test_generate_helm_install_command_oci_chart_with_version(self):
        """Test generating command for OCI chart with version in format."""
        command = generate_helm_install_command(
            release_name="my-release",
            chart="oci://registry.example.com/chart:v1.0.0",
            namespace="my-namespace",
        )
        self.assertIn("registry.example.com/chart", command)
        self.assertIn("--version v1.0.0", command)

    def test_generate_helm_install_command_parameters_override_instance(self):
        """Test that direct parameters override instance values."""
        command = generate_helm_install_command(
            instance=self.instance,
            release_name="override-release",
            namespace="override-namespace",
        )
        self.assertIn("override-release", command)
        self.assertIn("override-namespace", command)

    def test_generate_helm_install_command_missing_required_params(self):
        """Test that missing required parameters raise ValueError."""
        with self.assertRaises(ValueError):
            generate_helm_install_command(release_name=None, chart=None)

    def test_generate_helm_install_command_default_namespace(self):
        """Test that default namespace is used when not provided."""
        command = generate_helm_install_command(release_name="my-release", chart="my-chart")
        self.assertIn("--namespace default", command)


class ExportK8sValuesToYamlTestCase(TestCase):
    """Test cases for export_k8s_values_to_yaml function."""

    def setUp(self):
        """Set up test fixtures."""
        self.user = User.objects.create_user("testuser", "test@example.com", "password")
        self.project = Project.objects.create_project(name="test-project", owner=self.user, description="")
        self.app = Apps.objects.create(name="Test App", slug="testapp")
        self.subdomain = Subdomain.objects.create(subdomain="test-subdomain", project=self.project)
        self.instance = DashInstance.objects.create(
            app=self.app,
            project=self.project,
            owner=self.user,
            name="test-instance",
            subdomain=self.subdomain,
            chart="test-chart:1.0.0",
        )
        self.instance.k8s_values = {
            "name": "test-instance",
            "subdomain": "test-subdomain",
            "namespace": "default",
        }
        self.instance.save()

    def test_export_k8s_values_to_yaml_single_instance(self):
        """Test exporting YAML for a single instance."""
        with patch.object(self.instance, "set_k8s_values"):
            result = export_k8s_values_to_yaml([self.instance])

        # Should contain YAML content
        self.assertIn("test-instance", result)
        self.assertIn("test-subdomain", result)

        # Should contain helm command comments
        self.assertIn("# Helm install commands", result)
        self.assertIn("helm upgrade", result)

        # Should be valid YAML
        parsed = yaml.safe_load(result.split("\n\n")[-1])  # Get YAML part after comments
        self.assertIsInstance(parsed, dict)

    def test_export_k8s_values_to_yaml_multiple_instances(self):
        """Test exporting YAML for multiple instances."""
        # Create second instance
        subdomain2 = Subdomain.objects.create(subdomain="test-subdomain-2", project=self.project)
        instance2 = DashInstance.objects.create(
            app=self.app,
            project=self.project,
            owner=self.user,
            name="test-instance-2",
            subdomain=subdomain2,
            chart="test-chart:2.0.0",
        )
        instance2.k8s_values = {"name": "test-instance-2", "subdomain": "test-subdomain-2"}
        instance2.save()

        with patch.object(self.instance, "set_k8s_values"), patch.object(instance2, "set_k8s_values"):
            result = export_k8s_values_to_yaml([self.instance, instance2])

        # Should contain both instances
        self.assertIn("test-instance", result)
        self.assertIn("test-instance-2", result)

        # Should contain helm commands for both
        self.assertIn("# Helm install commands", result)
        # Count helm upgrade commands (should be 2)
        self.assertEqual(result.count("helm upgrade"), 2)

        # Should be valid YAML
        parsed = yaml.safe_load(result.split("\n\n")[-1])
        self.assertIsInstance(parsed, dict)
        self.assertEqual(len(parsed), 2)

    def test_export_k8s_values_to_yaml_empty_list(self):
        """Test that empty list raises ValueError."""
        with self.assertRaises(ValueError) as context:
            export_k8s_values_to_yaml([])
        self.assertIn("No app instances provided", str(context.exception))

    def test_export_k8s_values_to_yaml_with_override(self):
        """Test exporting with k8s_values_override."""
        self.instance.k8s_values_override = {"config": {"port": 9000}}
        self.instance.save()

        with patch.object(self.instance, "set_k8s_values"):
            result = export_k8s_values_to_yaml([self.instance])

        # Should contain merged values
        parsed = yaml.safe_load(result.split("\n\n")[-1])
        instance_key = f"{self.instance.name}_{self.instance.id}"
        self.assertIn(instance_key, parsed)
        # The override should be merged in
        self.assertIn("config", parsed[instance_key])

    def test_export_k8s_values_to_yaml_yaml_structure(self):
        """Test that exported YAML has correct structure."""
        with patch.object(self.instance, "set_k8s_values"):
            result = export_k8s_values_to_yaml([self.instance])

        # Should start with comments
        lines = result.split("\n")
        self.assertTrue(lines[0].startswith("#"))

        # Should have helm command comment
        self.assertTrue(any("# Helm install commands" in line for line in lines))

        # Should have instance key comment
        instance_key = f"{self.instance.name}_{self.instance.id}"
        self.assertTrue(any(instance_key in line for line in lines))

        # YAML should be parseable
        yaml_part = "\n".join([line for line in lines if not line.startswith("#") or line.strip() == ""])
        parsed = yaml.safe_load(yaml_part)
        self.assertIsInstance(parsed, dict)
        self.assertIn(instance_key, parsed)
