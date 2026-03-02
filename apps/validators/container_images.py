import re
import time
from dataclasses import dataclass
from enum import StrEnum
from typing import NamedTuple, Protocol
from urllib.parse import urlparse

import requests
from django.conf import settings
from requests.auth import HTTPBasicAuth

from studio.utils import get_logger

logger = get_logger(__name__)

# Constants

ACCEPT_MANIFEST = ", ".join(
    [
        "application/vnd.oci.image.manifest.v1+json",
        "application/vnd.oci.image.index.v1+json",
        "application/vnd.docker.distribution.manifest.v2+json",
        "application/vnd.docker.distribution.manifest.list.v2+json",
    ]
)


# Types and Protocols
class BaseRegistryAuth(Protocol):
    """
    Protocol for registry authentication classes.

    Defines methods to get the token service URL and retrieve a Bearer token.

    If you implement a new registry authenticator, it should conform to this protocol.
    In general, making a child of `DockerHubAuthenticator` should work.
    """

    def get_bearer_token(self, repo: str) -> str | None:
        ...


class RegistryHost(StrEnum):
    DOCKER_HUB = "registry-1.docker.io"
    GHCR = "ghcr.io"


@dataclass
class CachedToken:
    token: str
    expires_at: float


class ImageArchitectureTuple(NamedTuple):
    os: str
    """Operating system of the image, e.g., 'linux', 'windows'."""

    arch: str
    """CPU architecture of the image, e.g., 'amd64', 'arm64'."""


# Validation context (shared by all validators)
@dataclass
class ContainerImageContext:
    """
    Resolved container image info for validators.

    Use get_container_image_context(app_instance) to build this once; then
    DockerImageValidator and ImagePublicValidator can share the same resolution,
    parsing, and registry auth lookup.
    """

    image: str | None
    """Resolved image reference, or None if app has no image."""

    registry_host: RegistryHost | str | None
    repo: str
    reference: str
    registry_host_str: str
    auth: BaseRegistryAuth | None
    """Authenticator for this registry (from settings), or None if unsupported or no image."""

    @property
    def has_image(self) -> bool:
        return self.image is not None

    @property
    def is_supported_registry(self) -> bool:
        return self.auth is not None


# Validator classes
class DockerHubAuthenticator:
    """Handles authentication for DockerHub Container Registry."""

    def __init__(self, username: str | None, token: str | None) -> None:
        """
        Initializes the Registry Authenticator with a username and a Personal Access Token (PAT).

        Username and token are mandatory for Docker Hub, but for some other registries it's not.

        :param username: Registry username. If None, anonymous access is used.
        :param token: Personal Access Token (PAT) for authentication.
           See https://docs.docker.com/docker-hub/access-tokens/ for details on how to create a PAT.
        """
        self._username = username
        self._pat_token = token

    def get_token_service_url(self, repo: str) -> str:
        return f"https://auth.docker.io/token?service=registry.docker.io&scope=repository:{repo}:pull"

    def get_bearer_token(self, repo: str) -> str | None:
        """
        Always use Docker Hub's token service to get a Bearer token.
        Supports anonymous access (public images) or user+PAT for private.
        """
        logger.info("Requesting Docker Hub Bearer token...")
        token_service_url = self.get_token_service_url(repo=repo)

        if not self._username or not self._pat_token:
            # If no username or PAT is provided, use anonymous access
            logger.info("Using anonymous access for token exchange")
            resp = requests.get(token_service_url)
        else:
            logger.info("Using Basic Auth (username/PAT) for token exchange")
            resp = requests.get(token_service_url, auth=HTTPBasicAuth(self._username, self._pat_token))

        if resp.status_code != 200:
            logger.error(f"Failed to get Bearer token: {resp.status_code} {resp.text}")
            return None

        token = resp.json().get("token")
        if not token:
            logger.error(f"No token received in response: {resp.text}")
            return None

        return token


class GHCRAuthenticator(DockerHubAuthenticator):
    def __init__(self, username: str | None = None, token: str | None = None) -> None:
        """
        Initializes the GHCR Authenticator with a username and a Personal Access Token (PAT).

        :param username: Registry username. If None, anonymous access is used.
        :param token: Personal Access Token (PAT) for authentication.
           See https://docs.github.com/en/packages/learn-github-packages/introduction-to-github-packages#
           authenticating-to-github-packages
           for details on how to create a PAT.
        """
        super().__init__(username, token)

    def get_token_service_url(self, repo: str) -> str:
        """
        Override to use GHCR's token service URL.
        """
        return f"https://ghcr.io/token?service=ghcr.io&scope=repository:{repo}:pull"


class OCIRegistryPublicChecker:
    """
    Registry-agnostic checker for anonymous image pullability.
    """

    def __init__(self, registry: str, timeout: float = 10.0):
        if not registry.startswith("http"):
            registry = f"https://{registry}"
        self.registry = registry.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self._token_cache: dict[tuple[str, str, str], CachedToken] = {}

    @staticmethod
    def _parse_www_authenticate(header: str | None) -> dict[str, str] | None:
        if not header or not header.lower().startswith("bearer "):
            return None
        params = dict(re.findall(r'(\w+)="([^"]+)"', header))
        if not params.get("realm"):
            return None
        return params

    @staticmethod
    def _cache_key(realm: str, service: str, scope: str) -> tuple[str, str, str]:
        return (realm, service or "", scope or "")

    def _get_cached_token(self, realm: str, service: str, scope: str) -> str | None:
        key = self._cache_key(realm, service, scope)
        cached = self._token_cache.get(key)
        if not cached:
            return None
        if time.time() >= (cached.expires_at - 10):
            self._token_cache.pop(key, None)
            return None
        return cached.token

    def _store_token(self, realm: str, service: str, scope: str, token: str, expires_in: int | None) -> None:
        ttl = int(expires_in) if expires_in is not None else 120
        self._token_cache[self._cache_key(realm, service, scope)] = CachedToken(
            token=token,
            expires_at=time.time() + ttl,
        )

    def _fetch_token(self, realm: str, service: str, scope: str) -> str | None:
        cached = self._get_cached_token(realm, service, scope)
        if cached:
            return cached

        params: dict[str, str] = {}
        if service:
            params["service"] = service
        if scope:
            params["scope"] = scope

        resp = self.session.get(realm, params=params, timeout=self.timeout)
        if resp.status_code != 200:
            return None

        data = resp.json()
        token = data.get("token") or data.get("access_token")
        if not token:
            return None

        self._store_token(realm, service, scope, token, data.get("expires_in"))
        return token

    def _request_manifest(
        self, repository: str, reference: str, token: str | None, use_head: bool
    ) -> requests.Response:
        headers = {"Accept": ACCEPT_MANIFEST}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        url = f"{self.registry}/v2/{repository}/manifests/{reference}"
        method = self.session.head if use_head else self.session.get
        # Follow redirects to avoid false negatives behind registry/proxy redirects.
        return method(url, headers=headers, timeout=self.timeout, allow_redirects=True)

    def is_public(self, repository: str, reference: str = "latest") -> bool:
        for use_head in (True, False):
            response = self._request_manifest(repository, reference, token=None, use_head=use_head)

            if response.status_code == 200:
                return True

            if response.status_code == 404:
                return False

            if response.status_code in (405, 406):
                if use_head:
                    continue
                return False

            if response.status_code != 401:
                return False

            auth_header = (
                response.headers.get("WWW-Authenticate")
                or response.headers.get("Www-Authenticate")
                or response.headers.get("www-authenticate")
            )
            params = self._parse_www_authenticate(auth_header)
            if not params:
                return False

            realm = params.get("realm", "")
            service = params.get("service", "")
            scope = params.get("scope", "")

            token = self._fetch_token(realm, service, scope)
            if not token:
                return False

            retry_response = self._request_manifest(repository, reference, token=token, use_head=use_head)
            if retry_response.status_code == 200:
                return True
            if retry_response.status_code == 404:
                return False
            if retry_response.status_code != 401:
                return False

            # Token may have expired/revoked in-flight; refresh once.
            self._token_cache.pop(self._cache_key(realm, service, scope), None)
            token = self._fetch_token(realm, service, scope)
            if not token:
                return False

            final_response = self._request_manifest(repository, reference, token=token, use_head=use_head)
            return final_response.status_code == 200

        return False


# Utility functions for validators
def get_container_image_context(app_instance) -> ContainerImageContext:
    """
    Resolve and parse container image from app instance, and resolve registry auth.

    Reused by DockerImageValidator and ImagePublicValidator so resolution, parsing,
    and auth logic live in one place.
    """
    image = resolve_image_reference(app_instance)
    if not image:
        return ContainerImageContext(
            image=None,
            registry_host=None,
            repo="",
            reference="",
            registry_host_str="",
            auth=None,
        )
    registry_host, repo, reference = parse_image_reference(image)
    registry_host_str = registry_host_to_str(registry_host)
    auth = get_authenticator_for_registry(registry_host)
    return ContainerImageContext(
        image=image,
        registry_host=registry_host,
        repo=repo,
        reference=reference,
        registry_host_str=registry_host_str,
        auth=auth,
    )


def resolve_image_reference(app_instance) -> str | None:
    """
    Resolve an image reference from different app instance types.

    - Custom apps store the image in `app_instance.image`
    - Jupyter/RStudio store the image in `app_instance.environment.get_full_image_reference()`
    - Fallback: use `app_instance.k8s_values["appconfig"]["image"]` if present
    """
    image = getattr(app_instance, "image", None)
    if image:
        return image

    environment = getattr(app_instance, "environment", None)
    if environment and hasattr(environment, "get_full_image_reference"):
        env_image = environment.get_full_image_reference()
        if env_image:
            return env_image

    k8s_values = getattr(app_instance, "k8s_values", None) or {}
    if isinstance(k8s_values, dict):
        appconfig = k8s_values.get("appconfig") or {}
        if isinstance(appconfig, dict):
            k8s_image = appconfig.get("image")
            if k8s_image:
                return k8s_image

    return None


def registry_host_to_str(registry: RegistryHost | str) -> str:
    return registry.value if isinstance(registry, RegistryHost) else registry


def get_authenticator_for_registry(registry: RegistryHost | str) -> BaseRegistryAuth | None:
    """
    Return the appropriate registry authenticator for the given registry, using Django settings.

    Use this in validators so registry auth (Docker Hub vs GHCR credentials) is chosen in one place.
    Returns None for unsupported registries.
    """
    if isinstance(registry, RegistryHost):
        reg = registry
    else:
        reg_str = (registry or "").lower()
        if reg_str in (RegistryHost.DOCKER_HUB.value, "docker.io", "index.docker.io"):
            reg = RegistryHost.DOCKER_HUB
        elif reg_str == RegistryHost.GHCR.value:
            reg = RegistryHost.GHCR
        else:
            return None

    if reg == RegistryHost.DOCKER_HUB:
        return DockerHubAuthenticator(settings.DOCKER_HUB_USERNAME, settings.DOCKER_HUB_TOKEN)
    if reg == RegistryHost.GHCR:
        return GHCRAuthenticator(settings.GITHUB_API_USERNAME, settings.GITHUB_API_TOKEN)
    return None


def parse_image_reference(image: str) -> tuple[RegistryHost | str, str, str]:
    """
    Parse an OCI image reference into registry host, repository, and tag/digest reference.
    """
    image = image.strip()
    # Handle optional scheme from accidental input like "https://ghcr.io/org/repo:tag".
    if "://" in image:
        parsed = urlparse(image)
        image = f"{parsed.netloc}{parsed.path}".strip("/")

    parts = image.split("/")
    first = parts[0] if parts else ""
    # A registry hostname must be followed by a repository path segment.
    # Without "/", "python:3.12" is an image:tag, not "registry/repo".
    has_registry = len(parts) > 1 and ("." in first or ":" in first or first == "localhost")

    if has_registry:
        registry: RegistryHost | str = first
        repository_and_ref = "/".join(parts[1:])
    else:
        registry = RegistryHost.DOCKER_HUB
        repository_and_ref = image

    if "@" in repository_and_ref:
        repository, reference = repository_and_ref.rsplit("@", 1)
    else:
        last_segment = repository_and_ref.rsplit("/", 1)[-1]
        if ":" in last_segment:
            repository, reference = repository_and_ref.rsplit(":", 1)
        else:
            repository, reference = repository_and_ref, "latest"

    if isinstance(registry, str):
        registry = {
            "docker.io": RegistryHost.DOCKER_HUB,
            "index.docker.io": RegistryHost.DOCKER_HUB,
            RegistryHost.DOCKER_HUB.value: RegistryHost.DOCKER_HUB,
            RegistryHost.GHCR.value: RegistryHost.GHCR,
        }.get(registry.lower(), registry)

    # Docker Hub official images use implicit library namespace.
    if registry == RegistryHost.DOCKER_HUB and "/" not in repository:
        repository = f"library/{repository}"

    return registry, repository, reference


def get_manifest_list(
    *, registry_auth: BaseRegistryAuth, repository: str, reference: str, registry: str = "registry-1.docker.io"
):
    """
    Fetches the OCI manifest or manifest list for Docker Hub and GHCR.
    Returns the JSON manifest and the auth method used (Bearer token or Basic Auth).
    """
    headers = {"Accept": ACCEPT_MANIFEST}

    token = registry_auth.get_bearer_token(repository)
    headers["Authorization"] = f"Bearer {token}"

    url = f"https://{registry}/v2/{repository}/manifests/{reference}"
    logger.info(f"Fetching manifest from: {url}")

    resp = requests.get(url, headers=headers)
    if resp.status_code != 200:
        logger.error(f"Error fetching manifest: {resp.status_code} {resp.text}")
        return None

    return resp.json()


def get_config_blob(*, auth: BaseRegistryAuth, repo: str, digest: str, registry: str = "registry-1.docker.io"):
    """
    Fetches the config blob to read architecture/os for single-platform images.
    """
    url = f"https://{registry}/v2/{repo}/blobs/{digest}"
    headers = {}
    token = auth.get_bearer_token(repo)
    headers["Authorization"] = f"Bearer {token}"

    logger.info(f"Fetching config blob: {url}")
    resp = requests.get(url, headers=headers)
    if resp.status_code != 200:
        logger.error(f"Error fetching config blob: {resp.status_code} {resp.text}")
        return None

    return resp.json()


def _get_architectures_from_manifest_list(manifest_list) -> list[ImageArchitectureTuple] | None:
    manifests = manifest_list.get("manifests", [])
    if not manifests:
        logger.info("No platform manifests found in list!")
        return None

    logger.info("✅ Architectures in manifest list:")
    architectures = []
    for m in manifests:
        platform = m.get("platform", {})
        arch = platform.get("architecture")
        os = platform.get("os")
        architectures.append(ImageArchitectureTuple(os=os, arch=arch))
    logger.info(f"Found {len(architectures)} architectures in manifest list: {architectures}")
    return architectures


def _get_architecture_from_config(config) -> list[ImageArchitectureTuple] | None:
    arch = config.get("architecture")
    os = config.get("os")
    if arch and os:
        result = ImageArchitectureTuple(os=os, arch=arch)
        logger.info(f"✅ Found architecture for single-platform image: {result}")
        return [result]
    else:
        logger.warning("Could not determine architecture/OS from config!")
    return None


def get_image_architectures(
    *, auth: BaseRegistryAuth, repo: str, reference: str, registry: str = "registry-1.docker.io"
) -> list[ImageArchitectureTuple]:
    """
    Retrieves the architectures of a Docker image from its manifest.
    :param auth: BaseRegistryAuth: Authenticator for the registry.
        One of DockerHubAuthenticator or GHCRAuthenticator.
    :param repo: Repository name in the format 'namespace/repo'.
    :param reference: Reference (tag or digest) of the image.
    :param registry: Registry URL, default is 'registry-1.docker.io'.
    :return: list[ImageArchitectureTuple]: List of architectures and OS for the image.
    """
    manifest = get_manifest_list(
        registry=registry,
        repository=repo,
        reference=reference,
        registry_auth=auth,
    )

    media_type = manifest.get("mediaType")
    logger.info(f"Manifest mediaType: {media_type}")
    architectures = []

    if manifest.get("manifests"):
        # Multi-arch manifest list
        architectures = _get_architectures_from_manifest_list(manifest)
    elif manifest.get("config"):
        # Single-platform manifest
        config_digest = manifest["config"]["digest"]
        logger.info(f"Single-platform image detected. Config digest: {config_digest}")

        config = get_config_blob(registry=registry, repo=repo, digest=config_digest, auth=auth)
        architectures = _get_architecture_from_config(config)

    else:
        logger.error("Unknown or unsupported manifest format!")

    return architectures
