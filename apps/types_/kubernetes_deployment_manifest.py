import subprocess
import uuid
from datetime import datetime

import kubernetes_validate
import yaml


class KubernetesDeploymentManifest:
    """Represents a k8s deployment manifest"""

    _deployment_id = None
    _manifest_content = None

    def __init__(self, override_deployment_id: str = None):
        if override_deployment_id:
            self._deployment_id = override_deployment_id
        else:
            # Generate and set a unique deployment id
            # Example pattern: "20241126_085112_02500f53-7435-49a2-a5c2-66443e677a33"
            now = datetime.now().strftime("%Y%m%d_%H%M%S")
            self._deployment_id = f"{now}_{str(uuid.uuid4())}"

    def get_filepaths(self) -> dict[str, str]:
        """Returns two filepaths for this deployment for the values file and deployment file."""
        deployment_fileid = self.get_deployment_id()
        values_file = f"charts/values/{deployment_fileid}.yaml"
        deployment_file = f"charts/values/{deployment_fileid}_deployment.yaml"
        _paths = {"values_file": values_file, "deployment_file": deployment_file}
        return _paths

    def get_deployment_id(self) -> str:
        """Gets the unique deployment id"""
        return self._deployment_id

    def save_as_values_file(self, values_data: str) -> None:
        """Saves values data to a yaml file."""
        values_file = self.get_filepaths()["values_file"]
        with open(values_file, "w") as f:
            f.write(values_data)

    def generate_manifest_yaml_from_template(
        self, chart: str, values_file: str, namespace: str, save_to_file: bool = False
    ) -> tuple[str | None, str | None]:
        """
        Generate the manifest yaml for this deployment.
        The Helm command should be run as a Celery task but Celery lacks support for class methods.
        Therefore we import the Helm command function from the tasks module.
        When run in unit tests, this needs to use syncronously using CELERY_ALWAYS_EAGER
        """

        from ..tasks import helm_template

        output, error = helm_template(chart, values_file, namespace)

        if not error:
            if save_to_file:
                deployment_file = self.get_filepaths()["deployment_file"]
                with open(deployment_file, "w") as f:
                    f.write(output)

        return output, error

    def _delete_deployment_file(self) -> None:
        """Removes the deployment file if it exist."""
        files = self.kdm.get_filepaths()
        from pathlib import Path

        deployment_file = files["deployment_file"]

        if Path(deployment_file).is_file():
            subprocess.run(["rm", "-f", deployment_file])

    def validate_manifest(self, manifest_data: str) -> dict[bool, str]:
        """
        Validates manifest documents for this deployment.
        Uses kubernetes-validate to validate in-memory.

        Returns:
        dict[bool,str]: is_valid, output
        """
        invalid_docs = []

        documents = list(yaml.safe_load_all(manifest_data))

        for doc in documents:
            try:
                print(f"Validating document {doc['kind']}")

                kubernetes_validate.validate(doc, "1.22", strict=True)

            except kubernetes_validate.ValidationError as e:
                invalid_docs.append(doc["kind"])
                print(f"The kubernetes-validate tool found errors: {e}")

            except Exception as e:
                invalid_docs.append(doc["kind"])
                print(f"An error occurred during validation: {e}")

            output = f"Nr of docs with errors {len(invalid_docs)} of {len(documents)}"
            print(output)

        is_valid = len(invalid_docs) == 0

        return is_valid, output

    def validate_manifest_file(self) -> dict[bool, str, str]:
        """
        Validates the manifest file for this deployment.

        TODO: Replace kubectl apply with kubernetes-validate

        Returns:
        dict[bool,str,str]: is_valid, output, validation_error
        """
        from ..tasks import kubectl_apply_dry

        output, error = kubectl_apply_dry(self.get_filepaths()["deployment_file"], target_strategy="client")

        if error:
            return False, output, error

        if output is not None and "error:" in output:
            return False, output, error

        return True, output, error

    def extract_kubernetes_pod_patches_from_manifest(self):
        """Extracts a section of the manifest yaml known as kubernetes-pod-patches"""
        pass

    def validate_kubernetes_pod_patches_yaml(self):
        """Validates the kubernetes-pod-patches section"""
        pass

    def check_helm_version(self) -> tuple[str | None, str | None]:
        """Verifies that the Helm CLI is installed and accessible."""

        command = "helm version"
        # Execute the command
        try:
            result = subprocess.run(command.split(" "), check=True, text=True, capture_output=True)
            return result.stdout, None
        except subprocess.CalledProcessError as e:
            return e.stdout, e.stderr
