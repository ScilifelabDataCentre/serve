from unittest import skip

from django.test import TestCase

from studio.celery import app

from ..types_.kubernetes_deployment_manifest import KubernetesDeploymentManifest


class ValidKubernetesDeploymentManifestTestCase(TestCase):
    """Test case for a valid Kubernetes deployment."""

    DEPLOYMENT_ID = "unittest-valid"

    VALUES_DATA = r"""
        appconfig:
            allowContainerReuse: false
            image: ghcr.io/alfredeen/shiny-example:main-20241022-0849
            minimumSeatsAvailable: 1
            path: /
            port: 3839
            proxycontainerwaittime: 20000
            proxyheartbeatrate: 10000
            proxyheartbeattimeout: 60000
            seatsPerContainer: 1
            site_dir: /srv/shiny-server/
            appname: r9d95bb4a
            apps:
            volumeK8s: {}
            flavor:
            limits:
                cpu: 2000m
                ephemeral-storage: 5000Mi
                memory: 4Gi
            requests:
                cpu: 500m
                ephemeral-storage: 100Mi
                memory: 1Gi
            global:
            auth_domain: 127.0.0.1
            domain: studio.127.0.0.1.nip.io
            protocol: http
            name: Shiny test case 105
            namespace: default
            permission: project
            project:
            name: dp 241112
            slug: dp-241112-ono
            release: r9d95bb4a
            service:
            name: r9d95bb4a-shinyproxyapp
            storageClass: local-path
            subdomain: r9d95bb4a
            """

    def setUp(self) -> None:
        # Execute any Celery tasks synchronously
        app.conf.update(CELERY_ALWAYS_EAGER=True)

        self.kdm = KubernetesDeploymentManifest(override_deployment_id=self.DEPLOYMENT_ID)
        self.kdm.save_as_values_file(self.VALUES_DATA)

        # Verify that the file exists
        from pathlib import Path

        values_file = self.kdm.get_filepaths()["values_file"]
        self.assertTrue(Path(values_file).is_file())

    """
    Test method get_deployment_id
    """

    def test_get_deployment_id(self):
        actual = self.kdm.get_deployment_id()

        self.assertIsNotNone(actual)
        self.assertEqual(type(actual), str)
        self.assertEqual(actual, self.DEPLOYMENT_ID)

    """
    Test method check_chart_and_values_with_linter
    """

    @skip("Helm lint does not yet work in the container.")
    def test_check_chart_and_values_with_linter(self):
        chart = "oci://ghcr.io/scilifelabdatacentre/serve-charts/shinyproxy"
        values_file = self.kdm.get_filepaths()["values_file"]
        namespace = "default"

        output, error = self.kdm.check_chart_and_values_with_linter(chart, values_file, namespace)

        self.assertIsNone(error)
        self.assertIsNotNone(output)

    """
    Test method generate_manifest_yaml_from_template without saving to a file.
    """

    def test_generate_manifest_yaml_from_template(self):
        chart = "oci://ghcr.io/scilifelabdatacentre/serve-charts/shinyproxy"
        values_file = self.kdm.get_filepaths()["values_file"]
        namespace = "default"

        output, error = self.kdm.generate_manifest_yaml_from_template(chart, values_file, namespace, save_to_file=False)

        self.assertIsNone(error)
        self.assertIsNotNone(output)
        self.assertEqual(type(output), str)
        self.assertIn("apiVersion: v1", output)

    """
    Test method generate_manifest_yaml_from_template saving to file and finally validating the manifest.
    """

    @skip("kubectl apply will be replaced")
    def test_generate_and_validate_manifest_yaml_from_template(self):
        chart = "oci://ghcr.io/scilifelabdatacentre/serve-charts/shinyproxy"
        values_file = self.kdm.get_filepaths()["values_file"]
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

        # Validate the manifest file
        is_valid, output, validation_error = self.kdm.validate_manifest_file()

        self.assertTrue(is_valid, f"The manifest file is not valid. Error:{validation_error}. {output}")
        self.assertIsNone(validation_error)
        self.assertIsNotNone(output)
        self.assertEqual(type(output), str)

        # Finally delete the deployment file
        self.kdm._delete_deployment_files()

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


class BasicKubernetesDeploymentManifestTestCase(TestCase):
    """Test the basic functions of a Kubernetes deployment object."""

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
    Test method check_helm_version
    """

    def test_check_helm_version(self):
        actual = self.kdm.check_helm_version()

        self.assertIsNotNone(actual)
        self.assertEqual(type(actual), tuple)
        self.assertIn("version.BuildInfo", str(actual))
