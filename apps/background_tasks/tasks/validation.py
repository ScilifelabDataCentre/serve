"""
Example validation tasks.

These tasks validate various aspects of app instances before deployment.
"""

from typing import Any, Dict

from apps.background_tasks.base import BaseBackgroundTask
from apps.background_tasks.registry import TASK_REGISTRY
from apps.validators.container_images import ContainerImageContext
from studio.utils import get_logger

logger = get_logger(__name__)


def _validation_result_no_image(app_instance) -> Dict[str, Any]:
    """Shared 'no image to validate' result for container image validators."""
    return {
        "valid": True,
        "message": "No image to validate",
        "resolved_from": {
            "has_image_attr": hasattr(app_instance, "image"),
            "has_environment": bool(getattr(app_instance, "environment", None)),
            "has_k8s_values": bool(getattr(app_instance, "k8s_values", None)),
        },
    }


def _validation_result_skipped_unsupported_registry(ctx: ContainerImageContext) -> Dict[str, Any]:
    """Shared 'skipped unsupported registry' result for container image validators."""
    return {
        "valid": True,
        "skipped": True,
        "message": f"Skipping Docker image validation for unsupported registry '{ctx.registry_host_str}'",
        "image": ctx.image,
        "registry": ctx.registry_host_str,
        "repo": ctx.repo,
        "reference": ctx.reference,
    }


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
            get_container_image_context,
            get_image_architectures,
        )

        ctx = get_container_image_context(app_instance)
        logger.info("Processing image %s", ctx.image)
        if not ctx.has_image:
            return _validation_result_no_image(app_instance)
        if not ctx.is_supported_registry:
            logger.warning(
                "Skipping Docker image validation for unsupported registry '%s' (image=%s)",
                ctx.registry_host_str,
                ctx.image,
            )
            return _validation_result_skipped_unsupported_registry(ctx)

        # Validate architecture
        try:
            architectures = get_image_architectures(
                auth=ctx.auth,
                repo=ctx.repo,
                reference=ctx.reference,
                registry=ctx.registry_host_str,
            )

            # Check for amd64 architecture
            amd64_found = any(arch.arch == "amd64" for arch in architectures)

            if not amd64_found:
                raise ValueError(
                    f"Docker image {ctx.image} does not support amd64 architecture. "
                    f"Found: {[arch.arch for arch in architectures]}"
                )

            return {
                "valid": True,
                "architectures": [{"os": arch.os, "arch": arch.arch} for arch in architectures],
                "image": ctx.image,
                "registry": ctx.registry_host_str,
                "repo": ctx.repo,
                "reference": ctx.reference,
            }

        except Exception as e:
            logger.error("Failed to validate Docker image %s: %s", ctx.image, e)
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
    # Allow time for OCIRegistryPublicChecker slow retries on HTTP 5xx (linear backoff + manifest calls).
    timeout_seconds = 120

    def execute(self, app_instance, **kwargs) -> Dict[str, Any]:
        from apps.validators.container_images import (
            OCIRegistryPublicChecker,
            PublicImageAccessOutcome,
            get_container_image_context,
        )

        ctx = get_container_image_context(app_instance)
        logger.info("Checking public accessibility for image %s", ctx.image)
        if not ctx.has_image:
            return _validation_result_no_image(app_instance)

        checker = OCIRegistryPublicChecker(registry=ctx.registry_host_str, timeout=10.0)
        access = checker.check_public_accessibility(repository=ctx.repo, reference=ctx.reference)

        if access.outcome == PublicImageAccessOutcome.REGISTRY_UNAVAILABLE:
            logger.error(
                "Public image check inconclusive for %s (registry %s): %s",
                ctx.image,
                ctx.registry_host_str,
                access.detail,
            )
            raise ValueError(
                f"Could not verify that container image '{ctx.image}' is publicly pullable: "
                f"registry '{ctx.registry_host_str}' is unreachable or returned a server error "
                f"({access.detail}). Please retry later."
            )

        if access.outcome != PublicImageAccessOutcome.PUBLIC:
            reason = access.detail or "Registry did not allow anonymous manifest access"
            status_hint = f" [HTTP {access.status_code}]" if access.status_code is not None else ""
            raise ValueError(
                f"Container image '{ctx.image}' is not publicly pullable from registry '{ctx.registry_host_str}'"
                f"{status_hint}. {reason} "
                "Use a public image or ensure the image is published for anonymous pulls before deployment."
            )

        return {
            "valid": True,
            "image": ctx.image,
            "registry": ctx.registry_host_str,
            "repo": ctx.repo,
            "reference": ctx.reference,
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
