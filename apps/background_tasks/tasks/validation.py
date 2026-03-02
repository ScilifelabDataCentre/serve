"""
Example validation tasks.

These tasks validate various aspects of app instances before deployment.
"""

from typing import Any, Dict

from apps.background_tasks.base import BaseBackgroundTask
from apps.background_tasks.registry import TASK_REGISTRY
from studio.utils import get_logger

logger = get_logger(__name__)


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
        from django.conf import settings

        from apps.validators.container_images import (
            DockerHubAuthenticator,
            GHCRAuthenticator,
            RegistryHost,
            get_image_architectures,
            parse_image_reference,
            registry_host_to_str,
            resolve_image_reference,
        )

        # Extract image information from app instance
        image = resolve_image_reference(app_instance)
        logger.info("Processing image %s", image)
        if not image:
            return {
                "valid": True,
                "message": "No image to validate",
                "resolved_from": {
                    "has_image_attr": hasattr(app_instance, "image"),
                    "has_environment": bool(getattr(app_instance, "environment", None)),
                    "has_k8s_values": bool(getattr(app_instance, "k8s_values", None)),
                },
            }

        registry_host, repo, reference = parse_image_reference(image)
        registry_host_str = registry_host_to_str(registry_host)

        # Select registry authenticator
        if registry_host == RegistryHost.DOCKER_HUB:
            auth = DockerHubAuthenticator(settings.DOCKER_HUB_USERNAME, settings.DOCKER_HUB_TOKEN)
        elif registry_host == RegistryHost.GHCR:
            auth = GHCRAuthenticator(settings.GITHUB_API_USERNAME, settings.GITHUB_API_TOKEN)
        else:
            logger.warning(
                "Skipping Docker image validation for unsupported registry '%s' (image=%s)",
                registry_host_str,
                image,
            )
            return {
                "valid": True,
                "skipped": True,
                "message": f"Skipping Docker image validation for unsupported registry '{registry_host_str}'",
                "image": image,
                "registry": registry_host_str,
                "repo": repo,
                "reference": reference,
            }

        # Validate architecture
        try:
            architectures = get_image_architectures(
                auth=auth,
                repo=repo,
                reference=reference,
                registry=registry_host_str,
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
                "registry": registry_host_str,
                "repo": repo,
                "reference": reference,
            }

        except Exception as e:
            logger.error(f"Failed to validate Docker image {image}: {e}")
            raise


@TASK_REGISTRY.register(
    name="validate_image_public",
    is_critical=True,
    execution_order=0,
    app_types=["customapp", "jupyter", "rstudio"],
)
class ImagePublicValidator(BaseBackgroundTask):
    """
    Validate that the configured container image is anonymously pullable.
    """

    max_retries = 1
    task_type = "validation"
    timeout_seconds = 60

    def execute(self, app_instance, **kwargs) -> Dict[str, Any]:
        import requests

        from apps.validators.container_images import (
            OCIRegistryPublicChecker,
            parse_image_reference,
            registry_host_to_str,
            resolve_image_reference,
        )

        image = resolve_image_reference(app_instance)
        logger.info("Checking public accessibility for image %s", image)
        if not image:
            return {
                "valid": True,
                "message": "No image to validate",
                "resolved_from": {
                    "has_image_attr": hasattr(app_instance, "image"),
                    "has_environment": bool(getattr(app_instance, "environment", None)),
                    "has_k8s_values": bool(getattr(app_instance, "k8s_values", None)),
                },
            }

        registry_host, repo, reference = parse_image_reference(image)
        registry_host_str = registry_host_to_str(registry_host)
        checker = OCIRegistryPublicChecker(registry=registry_host_str, timeout=10.0)

        try:
            is_public = checker.is_public(repository=repo, reference=reference)
        except requests.RequestException as exc:
            logger.error("Public image validation failed for %s: %s", image, exc)
            raise ValueError(f"Failed to validate image accessibility for '{image}': {exc}") from exc

        if not is_public:
            raise ValueError(
                f"Container image '{image}' is not publicly pullable from registry '{registry_host_str}'. "
                "Please use a public image or publish the image before deployment."
            )

        return {
            "valid": True,
            "image": image,
            "registry": registry_host_str,
            "repo": repo,
            "reference": reference,
            "public": True,
        }


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
