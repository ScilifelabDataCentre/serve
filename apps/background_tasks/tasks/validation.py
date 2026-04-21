"""
Example validation tasks.

These tasks validate various aspects of app instances before deployment.
"""

from typing import Any, Dict

import requests

from apps.app_registry import APP_REGISTRY
from apps.background_tasks.base import BaseBackgroundTask
from apps.background_tasks.registry import TASK_REGISTRY
from apps.validators.container_images import (
    ContainerImageContext,
    ContainerImageValidationError,
)
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


def _concrete_app_instance_for_social_fields(app_instance):
    """
    BackgroundTask.app_instance points at BaseAppInstance; subclass fields (e.g.
    source_code_url from SocialMixin) live on the child table. Re-fetch by concrete
    model so those attributes are loaded.
    """
    slug = getattr(app_instance.app, "slug", None) or ""
    model = APP_REGISTRY.get_orm_model(slug)
    if model is None:
        return app_instance
    try:
        return model.objects.get(pk=app_instance.pk)
    except model.DoesNotExist:
        return app_instance


IMAGE_COMPATIBILITY_APP_TYPES = [
    "customapp",
    "dashapp",
    "jupyter-lab",
    "rstudio",
    "shinyproxyapp",
    "shinyapp",
    "gradio",
    "streamlit",
]


class TaskUIError(ContainerImageValidationError):
    """Validation error with a stable UI payload for the progress page."""

    def __init__(self, message: str, *, ui_error: Dict[str, str], retryable: bool = False):
        super().__init__(message, retryable=retryable)
        self.ui_error = ui_error


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


def _build_ui_error(*, code: str, summary: str, image_reference: str = "", note: str = "") -> Dict[str, str]:
    return {
        "code": code,
        "summary": summary,
        "image_reference": image_reference,
        "note": note,
    }


def _build_public_image_ui_error(image_reference: str) -> Dict[str, str]:
    return _build_ui_error(
        code="image_not_public",
        summary="We could not find this container image.",
        image_reference=image_reference,
        note="Make sure the image is publicly available.",
    )


def _build_docker_image_ui_error(error: Exception, image_reference: str) -> Dict[str, str]:
    resolved_image_reference = getattr(error, "context", {}).get("image_reference") or image_reference

    if getattr(error, "code", "") == "image_unsupported_architecture":
        return _build_ui_error(
            code="image_unsupported_architecture",
            summary="This container image does not support amd64.",
            image_reference=resolved_image_reference,
            note="Make sure the image is built for amd64.",
        )

    return _build_ui_error(
        code=getattr(error, "code", "image_validation_failed"),
        summary="We could not find this container image.",
        image_reference=resolved_image_reference,
        note="Make sure the image exists and is built for amd64.",
    )


@TASK_REGISTRY.register(
    name="validate_docker_image",
    is_critical=True,
    execution_order=1,
    app_types=IMAGE_COMPATIBILITY_APP_TYPES,
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
        from apps.validators.container_images import (
            get_container_image_context,
            get_image_architectures,
        )

        ctx = get_container_image_context(app_instance)
        logger.info("Processing image %s", ctx.image)
        if not ctx.has_image:
            return _validation_result_no_image(app_instance)
        if not ctx.is_supported_registry:
            logger.info(
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
                raise TaskUIError(
                    f"Docker image {ctx.image} does not support amd64 architecture. "
                    f"Found: {[arch.arch for arch in architectures]}",
                    ui_error=_build_ui_error(
                        code="image_unsupported_architecture",
                        summary="This container image does not support amd64.",
                        image_reference=ctx.image,
                        note="Make sure the image is built for amd64.",
                    ),
                )

            return {
                "valid": True,
                "architectures": [{"os": arch.os, "arch": arch.arch} for arch in architectures],
                "image": ctx.image,
                "registry": ctx.registry_host_str,
                "repo": ctx.repo,
                "reference": ctx.reference,
            }

        except ContainerImageValidationError as exc:
            if isinstance(exc, TaskUIError):
                raise
            raise TaskUIError(
                str(exc),
                retryable=bool(getattr(exc, "retryable", False)),
                ui_error=_build_docker_image_ui_error(exc, ctx.image),
            ) from exc
        except Exception as e:
            logger.error("Failed to validate Docker image %s: %s", ctx.image, e)
            raise

    def should_retry(self, error: Exception, retry_count: int) -> bool:
        if isinstance(error, ContainerImageValidationError):
            return bool(getattr(error, "retryable", False))
        return super().should_retry(error, retry_count)


@TASK_REGISTRY.register(
    name="validate_image_public",
    is_critical=True,
    execution_order=0,
    app_types=IMAGE_COMPATIBILITY_APP_TYPES,
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
            raise TaskUIError(
                f"Could not verify that container image '{ctx.image}' is publicly pullable: "
                f"registry '{ctx.registry_host_str}' is unreachable or returned a server error "
                f"({access.detail}). Please retry later.",
                retryable=True,
                ui_error=_build_public_image_ui_error(ctx.image),
            )

        if access.outcome != PublicImageAccessOutcome.PUBLIC:
            reason = access.detail or "Registry did not allow anonymous manifest access"
            status_hint = f" [HTTP {access.status_code}]" if access.status_code is not None else ""
            raise TaskUIError(
                f"Container image '{ctx.image}' is not publicly pullable from registry '{ctx.registry_host_str}'"
                f"{status_hint}. {reason} "
                "Use a public image or ensure the image is published for anonymous pulls before deployment.",
                ui_error=_build_public_image_ui_error(ctx.image),
            )

        return {
            "valid": True,
            "image": ctx.image,
            "registry": ctx.registry_host_str,
            "repo": ctx.repo,
            "reference": ctx.reference,
            "public": True,
        }

    def should_retry(self, error: Exception, retry_count: int) -> bool:
        if isinstance(error, ContainerImageValidationError):
            return bool(getattr(error, "retryable", False))
        return super().should_retry(error, retry_count)


@TASK_REGISTRY.register(
    name="validate_source_code_url",
    is_critical=False,
    execution_order=2,
    app_types=[
        "customapp",
        "dashapp",
        # "depictio",
        "gradio",
        "shinyapp",
        "shinyproxyapp",
        "streamlit",
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

        concrete = _concrete_app_instance_for_social_fields(app_instance)
        url = getattr(concrete, "source_code_url", None)
        if not url or not str(url).strip():
            return {
                "valid": True,
                "skipped": True,
                "reason": "no source code URL",
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
                logger.info("Source code URL HEAD failed for %s: %s", url, e)
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
                    logger.info("Source code URL GET failed for %s: %s", url, e)
                    return fail(f"Source code URL unreachable: {e!s}", status_code=None)

            if not (200 <= response.status_code < 300):
                return fail(
                    f"Source code URL returned unreachable. Response code: {response.status_code}",
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
