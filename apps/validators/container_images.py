from typing import NamedTuple, Protocol

import requests
from django.conf import settings
from requests.auth import HTTPBasicAuth

from studio.utils import get_logger

logger = get_logger(__name__)


class BaseRegistryAuth(Protocol):
    def get_bearer_token(self, repo: str) -> str | None:
        ...


class ImageArchitectureTuple(NamedTuple):
    os: str
    arch: str


class DockerHubAuthenticator:
    def __init__(self, username: str, token: str) -> None:
        self._username = username
        self._pat_token = token

    def get_token_service_url(self, repo: str) -> str:
        return f"https://auth.docker.io/token" f"?service=registry.docker.io" f"&scope=repository:{repo}:pull"

    def get_bearer_token(self, repo: str) -> str | None:
        """
        Always use Docker Hub's token service to get a Bearer token.
        Supports anonymous access (public images) or user+PAT for private.
        """
        logger.info("Requesting Docker Hub Bearer token...")
        token_service_url = self.get_token_service_url(repo=repo)

        logger.info("Using Basic Auth (username/PAT) for token exchange")
        resp = requests.get(token_service_url, auth=HTTPBasicAuth(self._username, self._pat_token))

        if resp.status_code != 200:
            logger.error(f"Failed to get Docker Hub token: {resp.status_code} {resp.text}")
            return None

        token = resp.json().get("token")
        if not token:
            logger.error(f"No token received in response: {resp.text}")
            return None

        return token


class GHCRAuthenticator(DockerHubAuthenticator):
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
    return architectures


def _get_architecture_from_config(config) -> list[ImageArchitectureTuple] | None:
    arch = config.get("architecture")
    os = config.get("os")
    if arch and os:
        logger.info("✅ Found architecture for single-platform image:")
        return [ImageArchitectureTuple(os=os, arch=arch)]
    else:
        logger.warning("Could not determine architecture/OS from config!")
    return None


def get_image_architecture(
    *, auth: BaseRegistryAuth, repo: str, refence: str, registry: str = "registry-1.docker.io"
) -> list[ImageArchitectureTuple]:
    manifest = get_manifest_list(
        registry=registry,
        repository=repo,
        reference=refence,
        registry_auth=auth,
    )

    media_type = manifest.get("mediaType")
    logger.info(f"Manifest mediaType: {media_type}")
    architectures = None

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
