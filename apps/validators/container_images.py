from typing import NamedTuple, Protocol

import requests
from django.conf import settings
from requests.auth import HTTPBasicAuth

from studio.utils import get_logger

logger = get_logger(__name__)


class BaseRegistryAuth(Protocol):
    """
    Protocol for registry authentication classes.

    Defines methods to get the token service URL and retrieve a Bearer token.

    If you implement a new registry authenticator, it should conform to this protocol.
    In general, making a child of `DockerHubAuthenticator` should work.
    """

    def get_bearer_token(self, repo: str) -> str | None:
        ...


class ImageArchitectureTuple(NamedTuple):
    os: str
    """Operating system of the image, e.g., 'linux', 'windows'."""

    arch: str
    """CPU architecture of the image, e.g., 'amd64', 'arm64'."""


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
           See https://docs.github.com/en/packages/learn-github-packages/introduction-to-github-packages#authenticating-to-github-packages
           for details on how to create a PAT.
        """
        super().__init__(username, token)

    def get_token_service_url(self, repo: str) -> str:
        """
        Override to use GHCR's token service URL.
        """
        return f"https://ghcr.io/token?service=ghcr.io&scope=repository:{repo}:pull"


def get_manifest_list(
    *, registry_auth: BaseRegistryAuth, repository: str, reference: str, registry: str = "registry-1.docker.io"
):
    """
    Fetches the OCI manifest or manifest list for Docker Hub and GHCR.
    Returns the JSON manifest and the auth method used (Bearer token or Basic Auth).
    """
    headers = {
        "Accept": (
            "application/vnd.docker.distribution.manifest.list.v2+json,"
            "application/vnd.oci.image.index.v1+json,"
            "application/vnd.docker.distribution.manifest.v2+json,"
            "application/vnd.oci.image.manifest.v1+json"
        )
    }

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
    *, auth: BaseRegistryAuth, repo: str, refence: str, registry: str = "registry-1.docker.io"
) -> list[ImageArchitectureTuple]:
    """
    Retrieves the architectures of a Docker image from its manifest.
    :param auth: BaseRegistryAuth: Authenticator for the registry.
        One of DockerHubAuthenticator or GHCRAuthenticator.
    :param repo: Repository name in the format 'namespace/repo'.
    :param refence: Reference (tag or digest) of the image.
    :param registry: Registry URL, default is 'registry-1.docker.io'.
    :return: list[ImageArchitectureTuple]: List of architectures and OS for the image.
    """
    manifest = get_manifest_list(
        registry=registry,
        repository=repo,
        reference=refence,
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
