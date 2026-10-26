from urllib.parse import urlencode

import requests
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db.models import Model

from apps.validators.container_images import (
    ContainerImageValidationError,
    OCIRegistryPublicChecker,
    PublicImageAccessOutcome,
    RegistryHost,
    _get_manifest_lookup_error_code,
    _is_transient_registry_status,
    parse_image_reference,
    registry_host_to_str,
    validate_harbor_image_reference,
    validate_public_image,
)
from studio.utils import get_logger

logger = get_logger(__name__)


class HarborAuthenticator:
    """Request anonymous pull tokens from the configured Harbor instance."""

    def __init__(self, registry: str) -> None:
        self.registry = registry

    def get_token_service_url(self, repo: str) -> str:
        query = urlencode({"service": "harbor-registry", "scope": f"repository:{repo}:pull"})
        return f"https://{self.registry}/service/token?{query}"

    def get_bearer_token(self, repo: str) -> str | None:
        try:
            response = requests.get(self.get_token_service_url(repo), timeout=10, allow_redirects=False)
        except requests.RequestException as exc:
            raise ContainerImageValidationError(
                "Could not reach Harbor. Please try again later.", retryable=True, code="image_metadata_unavailable"
            ) from exc

        if response.status_code != 200:
            raise ContainerImageValidationError(
                "Could not obtain access to this Harbor image. Check that the project and image are public.",
                retryable=_is_transient_registry_status(response.status_code),
                code=_get_manifest_lookup_error_code(response.status_code),
            )
        try:
            data = response.json()
        except ValueError as exc:
            raise ContainerImageValidationError("Harbor returned an invalid token response.") from exc
        if not isinstance(data, dict):
            raise ContainerImageValidationError("Harbor returned an invalid token response.")
        token = data.get("token") or data.get("access_token")
        if not isinstance(token, str) or not token.strip():
            raise ContainerImageValidationError("Harbor did not return a pull token.")
        return token


def get_harbor_registry_host() -> str:
    return settings.HARBOR_REGISTRY_HOST.strip().lower()


def is_harbor_registry(registry: str) -> bool:
    host = get_harbor_registry_host()
    return bool(host) and registry.lower() == host


def get_deployment_image(image: str) -> str:
    """Route supported upstream images through Harbor without changing the saved source image."""
    if not image or not settings.HARBOR_PROXY_CACHE_ENABLED:
        return image

    host = get_harbor_registry_host()
    if not host:
        return image

    registry, repository, reference = parse_image_reference(image)
    if registry == RegistryHost.DOCKER_HUB:
        project = settings.HARBOR_DOCKERHUB_PROJECT
    elif registry == RegistryHost.GHCR:
        project = settings.HARBOR_GHCR_PROJECT
    else:
        return image

    if not project:
        return image

    separator = "@" if "@" in image else ":"
    return f"{host}/{project}/{repository}{separator}{reference}"


def is_harbor_image(image: str) -> bool:
    registry, _, _ = parse_image_reference(image)
    return is_harbor_registry(registry_host_to_str(registry))


def resolve_deployment_image(image: str) -> str:
    """Prefer the Harbor proxy, falling back to the source registry if it cannot be used."""
    proxy_image = get_deployment_image(image)
    if proxy_image == image:
        return image

    try:
        registry, repository, reference = validate_harbor_image_reference(proxy_image)
        checker = OCIRegistryPublicChecker(registry=registry, timeout=5, verify_manifest=True)
        access = checker.check_public_accessibility(repository=repository, reference=reference, max_5xx_retries=0)
        if access.outcome == PublicImageAccessOutcome.PUBLIC:
            return proxy_image
    except (ValidationError, requests.RequestException, ValueError) as error:
        logger.warning("Could not use the Harbor proxy for %s: %s", image, error)
        return image

    logger.warning("Harbor proxy image is unavailable; using the source image %s", image)
    return image


def remember_deployment_image(instance, source: str, image: str) -> None:
    info = dict(instance.info or {}) if isinstance(getattr(instance, "info", None), dict) else {}
    info["image_resolution"] = {"source": source, "proxy": get_deployment_image(source), "image": image}
    instance.info = info
    if is_harbor_image(image):
        logger.info("Using Harbor image %s for %s", image, source)


def reset_image_resolution(instance) -> None:
    if isinstance(getattr(instance, "info", None), dict):
        instance.info = {key: value for key, value in instance.info.items() if key != "image_resolution"}


def get_instance_deployment_image(instance, source: str) -> str:
    """Reuse the registry selected for this deployment across workers and Helm rendering."""
    proxy = get_deployment_image(source)
    info = getattr(instance, "info", None) or {}
    saved = info.get("image_resolution", {}) if isinstance(info, dict) else {}
    if (
        isinstance(saved, dict)
        and saved.get("source") == source
        and saved.get("proxy") == proxy
        and saved.get("image") in (source, proxy)
    ):
        return saved["image"]
    if proxy == source or getattr(instance, "latest_user_action", None) == "Draft":
        return source

    image = resolve_deployment_image(source)
    remember_deployment_image(instance, source, image)
    if isinstance(instance, Model) and instance.pk:
        instance.save(update_fields=["info"])
    return image


def validate_harbor_image(image: str):
    """Validate a public image in the configured Harbor registry."""
    return validate_public_image(image, registry_name="Harbor", require_project=True)
