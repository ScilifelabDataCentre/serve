from django.test import TestCase

from studio.celery import app

from ..types_.kubernetes_deployment_manifest import KubernetesDeploymentManifest


class ValidKubernetesDeploymentManifestTestCase(TestCase):
    """Test case for a valid Kubernetes deployment."""

    def setUp(self) -> None:
        # Execute any Celery tasks synchronously
        app.conf.update(CELERY_ALWAYS_EAGER=True)

        self.kdm = KubernetesDeploymentManifest()

    """
    Test method get_deployment_id
    """

    def test_get_deployment_id(self):
        actual = self.kdm.get_deployment_id()

        self.assertIsNotNone(actual)
        self.assertEqual(type(actual), str)
        self.assertEqual(len(actual), 52)

    """
    Test method generate_manifest_yaml_from_template
    """

    def test_generate_manifest_yaml_from_template(self):
        chart = "oci://ghcr.io/scilifelabdatacentre/serve-charts/shinyproxy"
        values_file = "charts/values/20241126_085112_02500f53-7435-49a2-a5c2-66443e677a33.yaml"
        namespace = "default"

        output, error = self.kdm.generate_manifest_yaml_from_template(chart, values_file, namespace, save_to_file=True)

        self.assertIsNone(error)
        self.assertIsNotNone(output)
        self.assertEqual(type(output), str)
        self.assertIn("apiVersion: v1", output)

        # Verify the current working dir
        import os

        cwd = os.getcwd()
        self.assertEqual(cwd, "/app")

        # Verify the saved file exists and contains content
        deployment_file = self.kdm.get_filepaths()["deployment_file"]
        from pathlib import Path

        self.assertTrue(Path(deployment_file).is_file())

        f = open(deployment_file, "r")
        filecontent = f.read()
        self.assertIsNotNone(filecontent)
        self.assertEqual(filecontent, output)

    """
    Test method get_filepaths
    """

    def test_get_file_paths(self):
        actual = self.kdm.get_filepaths()

        self.assertIsNotNone(actual)
        self.assertEqual(type(actual), dict)

        # Verify the values filepath
        self.assertIsNotNone(actual["values_file"])
        self.assertEqual(type(actual["values_file"]), str)
        self.assertIn(".yaml", actual["values_file"])
        # Verify the deployment filepath
        self.assertIsNotNone(actual["deployment_file"])
        self.assertEqual(type(actual["deployment_file"]), str)
        self.assertIn("_deployment.yaml", actual["deployment_file"])

    """
    Test method check_helm_version
    """

    def test_check_helm_version(self):
        actual = self.kdm.check_helm_version()

        self.assertIsNotNone(actual)
        self.assertEqual(type(actual), tuple)
        self.assertIn("version.BuildInfo", str(actual))
