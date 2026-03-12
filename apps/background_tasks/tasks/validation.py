"""
Example validation tasks.

These tasks validate various aspects of app instances before deployment.
"""

from typing import Any

import requests

from apps.background_tasks.base import BaseBackgroundTask
from apps.background_tasks.registry import TASK_REGISTRY
from apps.background_tasks.utils import resolve_app_image
from apps.models.base import SocialMixin
from studio.utils import get_logger

logger = get_logger(__name__)

# App types that have SocialMixin (and thus source_code_url)
SOURCE_CODE_URL_APP_TYPES = [
    "customapp",
    "dashapp",
    "depictio",
    "gradio",
    "shinyapp",
    "shinyproxyapp",
    "streamlit",
    "tissuumaps",
]


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

    def execute(self, app_instance, **kwargs) -> dict[str, Any]:
        """Validate Docker image architecture."""
        from django.conf import settings

        from apps.validators.container_images import (
            DockerHubAuthenticator,
            GHCRAuthenticator,
            get_image_architectures,
        )

        # Extract image information from app instance using shared resolver
        image = resolve_app_image(app_instance)
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

        # Docker Hub requires "library/" namespace for official images
        if registry in (None, "", "docker.io", "index.docker.io", "registry-1.docker.io") and "/" not in repo:
            repo = f"library/{repo}"

        # Select registry authenticator
        if registry in (None, "", "docker.io", "index.docker.io", "registry-1.docker.io"):
            registry_host = "registry-1.docker.io"
            auth = DockerHubAuthenticator(settings.DOCKER_HUB_USERNAME, settings.DOCKER_HUB_TOKEN)
        elif registry == "ghcr.io":
            registry_host = "ghcr.io"
            auth = GHCRAuthenticator(settings.GITHUB_API_USERNAME, settings.GITHUB_API_TOKEN)
        else:
            logger.warning(
                "Skipping Docker image validation for unsupported registry '%s' (image=%s)",
                registry,
                image,
            )
            return {
                "valid": True,
                "skipped": True,
                "message": f"Skipping Docker image validation for unsupported registry '{registry}'",
                "image": image,
                "registry": registry,
                "repo": repo,
                "reference": reference,
            }

        # Validate architecture
        try:
            architectures = get_image_architectures(
                auth=auth,
                repo=repo,
                reference=reference,
                registry=registry_host,
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
                "registry": registry_host,
                "repo": repo,
                "reference": reference,
            }

        except Exception as e:
            logger.error(f"Failed to validate Docker image {image}: {e}")
            raise


@TASK_REGISTRY.register(
    name="validate_source_code_url",
    is_critical=False,
    execution_order=2,
    app_types=[
        "customapp",
        # "dashapp",
        # "depictio",
        # "gradio",
        # "shinyapp",
        # "shinyproxyapp",
        # "streamlit",
        # "tissuumaps",
    ],
)
class SourceCodeUrlValidator(BaseBackgroundTask):
    """
    Validates that the app's source_code_url (from SocialMixin) is reachable.

    Performs HTTP HEAD first; falls back to GET if HEAD is not supported.
    Non-2xx responses or timeouts are treated as warning or error depending on
    SOURCE_CODE_URL_VALIDATION_FAILURE_MODE ("warning" or "error").
    """

    max_retries = 1
    task_type = "validation"
    # Allow HTTP timeout + buffer for Celery soft limit
    timeout_seconds = 30

    def execute(self, app_instance, **kwargs) -> dict[str, Any]:
        from django.conf import settings

        if not isinstance(app_instance, SocialMixin):
            return {
                "valid": True,
                "message": "App type has no source_code_url; skip validation",
            }

        url = getattr(app_instance, "source_code_url", None)
        if not url or not url.strip():
            return {
                "valid": True,
                "message": "No source_code_url provided; skip validation",
            }

        timeout = getattr(
            settings,
            "SOURCE_CODE_URL_VALIDATION_TIMEOUT_SECONDS",
            10,
        )
        failure_mode = getattr(
            settings,
            "SOURCE_CODE_URL_VALIDATION_FAILURE_MODE",
            "warning",
        ).lower()
        if failure_mode not in ("warning", "error"):
            failure_mode = "warning"
        treat_as_error = failure_mode == "error"

        def fail(message: str, status_code: int | None = None) -> dict[str, Any]:
            if treat_as_error:
                detail = message
                if status_code is not None:
                    detail = f"{message} (HTTP {status_code})"
                raise ValueError(detail)
            return {
                "valid": True,
                "validation_warning": message,
                "status_code": status_code,
                "url": url,
            }

        try:
            # Prefer HEAD to avoid downloading body; allow_redirects to follow 3xx
            try:
                response = requests.head(
                    url,
                    timeout=timeout,
                    allow_redirects=True,
                    headers={"User-Agent": "ScilifelabServe-SourceCodeUrlValidator/1.0"},
                )
            except requests.RequestException as e:
                logger.warning("Source code URL HEAD failed for %s: %s", url, e)
                return fail(f"Source code URL unreachable: {e!s}", status_code=None)

            # Some servers respond with 405 Method Not Allowed for HEAD; try GET
            if response.status_code == 405:
                try:
                    response = requests.get(
                        url,
                        timeout=timeout,
                        allow_redirects=True,
                        headers={
                            "User-Agent": "ScilifelabServe-SourceCodeUrlValidator/1.0",
                        },
                        stream=True,
                    )
                    # Consume a minimal amount to avoid reading full body
                    response.close()
                except requests.RequestException as e:
                    logger.warning("Source code URL GET failed for %s: %s", url, e)
                    return fail(f"Source code URL unreachable: {e!s}", status_code=None)

            if not (200 <= response.status_code < 300):
                return fail(
                    f"Source code URL returned non-2xx: {response.status_code}",
                    status_code=response.status_code,
                )

            return {
                "valid": True,
                "url": url,
                "status_code": response.status_code,
            }

        except requests.Timeout:
            return fail(f"Source code URL request timed out after {timeout}s", status_code=None)

        except requests.RequestException as e:
            return fail(f"Source code URL request failed: {e!s}", status_code=None)


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

    def execute(self, app_instance, **kwargs) -> dict[str, Any]:
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
