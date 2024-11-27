from django.test import TestCase

from ..types_.kubernetes_deployment_manifest import KubernetesDeploymentManifest


class ValidKubernetesDeploymentManifestTestCase(TestCase):
    """Test case for a valid Kubernetes deployment."""

    def setUp(self) -> None:
        self.kdm = KubernetesDeploymentManifest()

    def test_get_deployment_id(self):
        actual = self.kdm.get_deployment_id()

        self.assertIsNotNone(actual)
        self.assertEqual(type(actual), str)
        self.assertEqual(len(actual), 52)

    def test_check_helm_version(self):
        actual = self.kdm.check_helm_version()

        self.assertIsNotNone(actual)
        self.assertEqual(type(actual), tuple)
        self.assertIn("version.BuildInfo", str(actual))
