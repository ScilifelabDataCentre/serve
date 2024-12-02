from pathlib import Path
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
            image: ghcr.io/somerepo/shiny:v1
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
    Test method validate_manifest.
    This first runs generate manifest yaml to have manifest to validate.
    It runs everything in memory without creating files (except for the values file).
    """

    def test_validate_manifest(self):
        # First generate the manifest yaml
        chart = "oci://ghcr.io/scilifelabdatacentre/serve-charts/shinyproxy"
        values_file = self.kdm.get_filepaths()["values_file"]
        namespace = "default"

        output, error = self.kdm.generate_manifest_yaml_from_template(chart, values_file, namespace, save_to_file=False)

        self.assertIsNone(error)
        self.assertIsNotNone(output)
        self.assertEqual(type(output), str)
        self.assertIn("apiVersion: v1", output)

        # Validate the manifest documents
        is_valid, output = self.kdm.validate_manifest(output)

        if not is_valid:
            print(output)

        self.assertTrue(is_valid)

    """
    Test method extract_kubernetes_pod_patches_from_manifest
    """

    def test_extract_kubernetes_pod_patches_from_manifest(self):
        # First generate the manifest yaml
        chart = "oci://ghcr.io/scilifelabdatacentre/serve-charts/shinyproxy"
        values_file = self.kdm.get_filepaths()["values_file"]
        namespace = "default"

        output, error = self.kdm.generate_manifest_yaml_from_template(chart, values_file, namespace, save_to_file=False)

        self.assertIsNone(error)
        self.assertIsNotNone(output)

        # Then extract the kubernetes-pod-patches section
        actual = self.kdm.extract_kubernetes_pod_patches_from_manifest(output)

        self.assertIsNotNone(actual, f"The manifest input was: {output}")
        self.assertEqual(type(actual), str, f"The returned data is {actual}")
        self.assertTrue(actual.startswith("- op: add"), f"The returned text is {actual}")
        self.assertTrue(actual.endswith("name: tmp-release-name-shiny-configmap"), f"Text is:{actual}")
        self.assertGreater(len(actual), 500)
        self.assertLess(len(actual), 1000)

    """
    Test method validate_kubernetes_pod_patches_yaml
    """

    def test_validate_kubernetes_pod_patches_yaml(self):
        kpp_text = r"""
          - op: add
            path: /spec/securityContext
            value:
              runAsUser: 999
              runAsGroup: 999
              runAsNonRoot: true
              allowPrivilegeEscalation: false
              privileged: false
          - op: add
            path: /spec/volumes
            value:
            - name: tmp-release-name-shiny-configmap
              configMap:
                name: tmp-release-name-shiny-configmap
                items:
                - key: shiny-server.conf
                  path: shiny-server.conf
          - op: add
            path: /spec/containers/0/volumeMounts
            value:
            - mountPath: /etc/shiny-server/shiny-server.conf
              subPath: shiny-server.conf
              name: tmp-release-name-shiny-configmap
"""

        is_valid, output = self.kdm.validate_kubernetes_pod_patches_yaml(kpp_text)

        self.assertTrue(is_valid, f"The input should be valid. {output}")
        self.assertIsNone(output)

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


class ValidateExistingKubernetesDeploymentManifestTestCase(TestCase):
    """Validate any existing deployment files in the charts/values directory."""

    def test_validate_manifests(self):
        deployment_files = list(Path("charts/values").glob("*_deployment.yaml"))

        print(f"Nr of manifest files to validate: {len(deployment_files)}")

        for file in deployment_files:
            f = open(file, "r")
            manifest_data = f.read()

            kdm = KubernetesDeploymentManifest()

            # Validate the manifest documents
            print(f"Validating deployment file {file}")
            is_valid, output = kdm.validate_manifest(manifest_data)

            if not is_valid:
                print(output)

            if "invalid" in file.name:
                # Files named with invalid in the filename as expected to be invalid
                self.assertFalse(is_valid)
            else:
                self.assertTrue(is_valid)


class InvalidKubernetesDeploymentManifestTestCase(TestCase):
    """Test case for an INVALID Kubernetes deployment."""

    DEPLOYMENT_ID = "unittest-invalid"

    DEPLOYMENT_DATA = r"""
---
# Source: shinyproxy/templates/configmap.yaml
apiVersion: v1
kind: ConfigMap
metadata:
name: r9d95bb4a-shinyproxy-configmap
labels:
    helm.sh/chart: shinyproxy-1.4.2
    app.kubernetes.io/name: shinyproxy
    app.kubernetes.io/instance: r9d95bb4a
    app.kubernetes.io/version: "0.1"
    app.kubernetes.io/managed-by: Helm

data:
application.yml: |
    management:
    server:
        port: 9091
    server:
    secure-cookies: true
    proxy:
    authentication: none
    container-backend: kubernetes
    heartbeat-rate: 10000
    heartbeat-timeout: 60000
    container-wait-time: 20000
    kubernetes:
        internal-networking: true
        namespace: default
        image-pull-policy: IfNotPresent
    hide-navbar: true
    landing-page: /app/r9d95bb4a
    livenessProbe: {}
    logo-url: https://www.openanalytics.eu/shinyproxy/logo.png
    port: 8080
    readinessProbe: {}
    same-site-cookie: None
    specs:
    - container-cmd:
        - /usr/bin/shiny-server
        container-cpu-limit: 2000m
        container-cpu-request: 500m
        container-image: ghcr.io/somerepo/shiny:v1
        container-memory-limit: 4Gi
        container-memory-request: 1Gi
        port: 3839
        id:  r9d95bb4a
        display-name:
        description:
        minimum-seats-available: 1
        seats-per-container: 1
        allow-container-re-use: false
        labels:
        sp.instance: r9d95bb4a
        allow-internet-egress: "true"
        shinyproxy-app: r9d95bb4a
        kubernetes-pod-patches: |
        - op: add
            path: /spec/securityContext
            value:BAD-HERE
            runAsUser: 999
            runAsGroup: 999
            runAsNonRoot: true
            allowPrivilegeEscalation: false
            privileged: false
        - op: add
            path: /spec/volumes
            value:
            - name: r9d95bb4a-shiny-configmap
            configMap:
                name: r9d95bb4a-shiny-configmap
                items:
                - key: shiny-server.conf
                path: shiny-server.conf
        - op: add
            path: /spec/containers/0/volumeMounts
            value:
            - mountPath: /etc/shiny-server/shiny-server.conf
            subPath: shiny-server.conf
            name: r9d95bb4a-shiny-configmap

    title: Serve Shiny Proxy
---
# Source: shinyproxy/templates/shiny-configmap.yaml
# This configmap relates to the shiny app pod spawned by the shinyproxy deployment
apiVersion: v1
kind: ConfigMap
metadata:
name: r9d95bb4a-shiny-configmap
namespace: default
data:
shiny-server.conf: |-
    # Instruct Shiny Server to run applications as the user "shiny"
    run_as shiny;
    http_keepalive_timeout 600;
    # Define a server that listens on user defined port
    server {
    listen 3839 0.0.0.0;
    # Define a location at the base URL
    location / {
        # Host the directory of Shiny Apps stored in this directory
        site_dir /srv/shiny-server/;
        # Log all Shiny output to files in this directory
        log_dir /var/log/shiny-server;
        directory_index on;
        app_init_timeout 600;
        app_idle_timeout 600;
    }
    app_init_timeout 600;
    app_idle_timeout 600;
    }
---
# Source: shinyproxy/templates/service.yaml
apiVersion: v1
kind: Service
metadata:
name: r9d95bb4a-shinyproxyapp
namespace: default
labels:
    run: r9d95bb4a-shinyapp
spec:
ports:
- protocol: TCP
    port: 80
    targetPort: 8080
selector:
    release: r9d95bb4a
---
# Source: shinyproxy/templates/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
name: r9d95bb4a
namespace: default
annotations:
    reloader.stakater.com/auto: "true"
spec:
replicas: 1
selector:
    matchLabels:
    release: r9d95bb4a
    app: shinyproxy-deployment
    project: dp-241112-ono
    type: app
    pod: serve
template:
    metadata:
    annotations:
        prometheus.io/scrape: "true"
        prometheus.io/path: /metrics
        # prometheus.io/port: "8501"
    labels:
        release: r9d95bb4a
        access: project
        app: shinyproxy-deployment
        project: dp-241112-ono
        site-dir: srv-shiny-server
        networking/allow-internet-egress: "true"
        networking/allow-egress-to-studio-web: "true"
        allow-api-access: "true"
        type: app
        pod: serve
    spec:
    securityContext:
        fsGroup: 1000
        seccompProfile:
        type: RuntimeDefault
    serviceAccountName: default-shinyproxy
    containers:
    - name: serve
        image: ghcr.io/scilifelabdatacentre/serve-shinyproxy:v1
        # BAD entries here:
        ports:
        - containerPort: 8080

        non-existing-label: BAD
        volumeMounts:
        - name: application-conf-r9d95bb4a
            mountPath: /opt/shinyproxy/config
        imagePullPolicy: IfNotPresent
        securityContext:
        allowPrivilegeEscalation: false
        capabilities:
            drop:
            - all
        privileged: false
        runAsGroup: 1000
        runAsNonRoot: true
        runAsUser: 1000
        resources:
        limits:
            cpu: 300m
            memory: 800Mi
        requests:
            cpu: 200m
            memory: 512Mi
        readinessProbe:
        tcpSocket:
            port: 8080
        initialDelaySeconds: 60
        periodSeconds: 15
    volumes:
    - name: application-conf-r9d95bb4a
        configMap:
        name: r9d95bb4a-shinyproxy-configmap
    dnsPolicy: ClusterFirst
---
# Source: shinyproxy/templates/ingress.yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
name: r9d95bb4a-ingress
namespace: default
labels:
    io.kompose.service: r9d95bb4a-ingress
annotations:
        nginx.ingress.kubernetes.io/proxy-body-size: 2000m
spec:
rules:
    - host: r9d95bb4a.studio.127.0.0.1.nip.io
    http:
        paths:
        - path: /
        backend:
            service:
            name: r9d95bb4a-shinyproxyapp
            port:
                number: 80
        pathType: ImplementationSpecific
tls:
    - secretName: prod-ingress
    hosts:
        - studio.127.0.0.1.nip.io
            """

    def setUp(self) -> None:
        # Execute any Celery tasks synchronously
        app.conf.update(CELERY_ALWAYS_EAGER=True)

        self.kdm = KubernetesDeploymentManifest(override_deployment_id=self.DEPLOYMENT_ID)

    """
    Test method validate_manifest.
    It runs everything in memory without creating files (except for the values file).
    """

    def test_validate_manifest(self):
        # Validate the manifest documents
        is_valid, output = self.kdm.validate_manifest(self.DEPLOYMENT_DATA)

        if is_valid:
            print(output)

        self.assertFalse(is_valid)

    """
    Test method validate_kubernetes_pod_patches_yaml with invalid input
    """

    def test_validate_kubernetes_pod_patches_yaml(self):
        kpp_text = r"""
          - op: add
            path: /spec/securityContext
            value:
              runAsUser: 999
              runAsGroup: 999
              runAsNonRoot: true
              allowPrivilegeEscalation: false
              privileged: false
          - op: add
            path BAD-HERE /spec/volumes
            value:
            - name: tmp-release-name-shiny-configmap
              configMap:
                name: tmp-release-name-shiny-configmap
                items:
                - key: shiny-server.conf
                  path: shiny-server.conf
          - op: add
            path: /spec/containers/0/volumeMounts
            value:
            - mountPath: /etc/shiny-server/shiny-server.conf
              subPath: shiny-server.conf
              name: tmp-release-name-shiny-configmap
"""

        is_valid, output = self.kdm.validate_kubernetes_pod_patches_yaml(kpp_text)

        self.assertFalse(is_valid, f"The input should be invalid. {output}")
        self.assertIsNotNone(output)
