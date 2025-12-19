"""
Example validation tasks.

These tasks validate various aspects of app instances before deployment.
"""

from typing import Any, Dict

from apps.background_tasks.base import BaseBackgroundTask
from apps.background_tasks.registry import TASK_REGISTRY
from studio.utils import get_logger

logger = get_logger(__name__)


# Example task - not registered by default
# Uncomment the decorator to activate
@TASK_REGISTRY.register(
    name="validate_docker_image", is_critical=True, execution_order=1, app_types=["customapp", "jupyter", "rstudio"]
)
class DockerImageValidator(BaseBackgroundTask):
    """
    Validates that Docker image has correct architecture.

    Uses the existing validator from apps/validators/container_images.py
    """

    max_retries = 2
    task_type = "validation"
    timeout_seconds = 180

    def execute(self, app_instance, **kwargs) -> Dict[str, Any]:
        """Validate Docker image architecture."""
        from apps.validators.container_images import (
            GHCRAuthenticator,
            get_image_architectures,
        )

        # Extract image information from app instance
        image = getattr(app_instance, "image", None)
        if not image:
            return {"valid": True, "message": "No image to validate"}

        # Parse image string (format: registry/repo:tag or repo:tag)
        parts = image.split("/")
        if len(parts) >= 2:
            registry = parts[0]
            repo = "/".join(parts[1:]).split(":")[0]
            reference = image.split(":")[-1] if ":" in image else "latest"
        else:
            registry = None
            repo = image.split(":")[0]
            reference = image.split(":")[-1] if ":" in image else "latest"

        # Validate architecture
        try:
            auth = GHCRAuthenticator()
            architectures = get_image_architectures(
                auth=auth, repo=repo, reference=reference, registry=registry or "ghcr.io"
            )

            # Check for amd64 architecture
            amd64_found = any(arch.arch == "amd64" for arch in architectures)

            if not amd64_found:
                raise ValueError(
                    f"Docker image {image} does not support amd64 architecture. "
                    f"Found: {[arch.arch for arch in architectures]}"
                )

            return {
                "valid": True,
                "architectures": [{"os": arch.os, "arch": arch.arch} for arch in architectures],
                "image": image,
            }

        except Exception as e:
            logger.error(f"Failed to validate Docker image {image}: {e}")
            raise


# Example task - not registered by default
# @TASK_REGISTRY.register(
#     name='validate_subdomain',
#     is_critical=True,
#     execution_order=0,
# )
class SubdomainValidator(BaseBackgroundTask):
    """
    Validates subdomain availability and format.
    """

    max_retries = 1
    task_type = "validation"

    def execute(self, app_instance, **kwargs) -> Dict[str, Any]:
        """Validate subdomain."""
        from apps.types_.subdomain import SubdomainCandidateName

        subdomain = app_instance.subdomain
        if not subdomain:
            raise ValueError("App instance has no subdomain")

        project_id = app_instance.project.id
        candidate = SubdomainCandidateName(subdomain.subdomain, project_id)

        if not candidate.is_valid():
            raise ValueError(f"Subdomain '{subdomain.subdomain}' is not valid")

        return {
            "valid": True,
            "subdomain": subdomain.subdomain,
            "project_id": project_id,
        }
