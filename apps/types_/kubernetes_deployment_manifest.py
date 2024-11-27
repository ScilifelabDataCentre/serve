import subprocess
import uuid
from datetime import datetime


class KubernetesDeploymentManifest:
    """Represents a k8s deployment manifest"""

    _deployment_id = None
    _path = None
    _manifest_content = None

    def __init__(self):
        # Generate and set a unique deployment id
        # Example pattern: "20241126_085112_02500f53-7435-49a2-a5c2-66443e677a33"
        now = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._deployment_id = f"{now}_{str(uuid.uuid4())}"

    def get_deployment_id(self):
        """Gets the unique deployment id"""
        return self._deployment_id

    def check_helm_version(self):
        """Verifies that the Helm CLI is installed and accessible."""
        command = "helm version"
        # Execute the command
        try:
            result = subprocess.run(command.split(" "), check=True, text=True, capture_output=True)
            return result.stdout, None
        except subprocess.CalledProcessError as e:
            return e.stdout, e.stderr

    def generate_manifest_yaml_from_template(self, chart, values_file, namespace, save_to_file=False):
        """Generate the manifest yaml for this deployment"""

        # Base command
        command = f"helm template tmp-release-name {chart} {values_file} --namespace {namespace}"
        # TODO: Run the command
        return command

    def validate_manifest_file(self):
        """Validates the manifest file for this deployment"""
        pass

    def extract_kubernetes_pod_patches_from_manifest(self):
        """Extracts a section of the manifest yaml known as kubernetes-pod-patches"""
        pass

    def validate_kubernetes_pod_patches_yaml(self):
        """Validates the kubernetes-pod-patches section"""
        pass
