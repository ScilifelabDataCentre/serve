from typing import Protocol

import requests
from requests.auth import HTTPBasicAuth
from django.conf import settings

from studio.utils import get_logger

logger = get_logger(__name__)


class BaseRegistryAuth(Protocol):
    def get_bearer_token(self, repo: str) -> str | None:
        ...


class DockerHubAuthenticator:
    def __init__(self, username: str, token: str) -> None:
        self._username = username 
        self._pat_token = token

    def get_token_service_url(self, repo: str) -> str:
        return (
            f"https://auth.docker.io/token"
            f"?service=registry.docker.io"
            f"&scope=repository:{repo}:pull"
        )
        
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
            logger.error("Failed to get Docker Hub token: {resp.status_code} {resp.text}")
            return None

        token = resp.json().get('token')
        if not token:
            logger.error("No token received in response: {resp.text}")
            return None

        return token
    

class GHCRAuthenticator:
    def get_bearer_token(self, repo: str) -> str | None:
        return settings.GITHUB_API_TOKEN
    

def get_manifest_list(*, registry_auth: BaseRegistryAuth, repository: str, reference: str, registry: str = "registry-1.docker.io"):
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


# TODO: Finist porting


def get_config_blob(registry, repo, digest, token=None, auth=None):
    """
    Fetches the config blob to read architecture/os for single-platform images.
    """
    url = f"https://{registry}/v2/{repo}/blobs/{digest}"
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    print(f"[*] Fetching config blob: {url}")
    resp = requests.get(url, headers=headers, auth=auth)
    if resp.status_code != 200:
        print(f"[!] Error fetching config blob: {resp.status_code} {resp.text}")
        sys.exit(1)

    return resp.json()


def print_architectures_from_manifest_list(manifest_list):
    manifests = manifest_list.get('manifests', [])
    if not manifests:
        print("\n[!] No platform manifests found in list!")
        return

    print("\n✅ Architectures in manifest list:")
    for m in manifests:
        platform = m.get('platform', {})
        arch = platform.get('architecture')
        os = platform.get('os')
        variant = platform.get('variant')
        line = f"- {arch} / {os}"
        if variant:
            line += f" / {variant}"
        print(line)

def print_architecture_from_config(config):
    arch = config.get("architecture")
    os = config.get("os")
    if arch and os:
        print("\n✅ Architecture for single-platform image:")
        print(f"- {arch} / {os}")
    else:
        print("\n[!] Could not determine architecture/OS from config!")


manifest, token, auth = get_manifest_list(
    registry=registry,
    repo=repo,
    reference=tag,
    username=username,
    password=password
)

media_type = manifest.get("mediaType")
print(f"\n[*] Manifest mediaType: {media_type}")

if manifest.get('manifests'):
    # Multi-arch manifest list
    print_architectures_from_manifest_list(manifest)

elif manifest.get('config'):
    # Single-platform manifest
    config_digest = manifest['config']['digest']
    print(f"\n[*] Single-platform image detected. Config digest: {config_digest}")

    config = get_config_blob(
        registry=registry,
        repo=repo,
        digest=config_digest,
        token=token,
        auth=auth
    )
    print_architecture_from_config(config)

else:
    print("\n[!] Unknown or unsupported manifest format!")

    