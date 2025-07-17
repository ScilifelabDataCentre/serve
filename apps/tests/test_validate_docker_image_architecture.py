import pytest
import requests
from django.conf import settings

from apps.validators.container_images import (
    DockerHubAuthenticator,
    GHCRAuthenticator,
    ImageArchitectureTuple,
    get_image_architectures,
)


def test_ghcr_architecture_is_valid():
    architectures = get_image_architectures(
        auth=GHCRAuthenticator(),
        repo="scilifelabdatacentre/serve-jupyterlab",
        reference="250204-1056",
        registry="ghcr.io",
    )
    assert len(architectures) > 0
    assert architectures == [ImageArchitectureTuple(os="linux", arch="amd64")]


def test_get_anonymous_bearer_token():
    auth = GHCRAuthenticator()
    token = auth.get_token_service_url("scilifelabdatacentre/serve-jupyterlab")
    resp = requests.get(token)
    assert resp.status_code == 200, f"Failed to get anonymous bearer token: {resp.status_code} {resp.text}"
    assert "token" in resp.json(), "Token not found in response"


@pytest.mark.skipif(
    condition="settings.DOCKER_HUB_TOKEN is None",
)
def test_get_docker_hub_architecture_is_valid():
    auth = DockerHubAuthenticator(
        username=settings.DOCKER_HUB_USERNAME,
        token=settings.DOCKER_HUB_TOKEN,
    )
    architectures = get_image_architectures(
        auth=auth,
        repo="library/python",
        reference="3.14-rc-slim-bullseye",
    )
    assert len(architectures) > 0
    assert architectures == [
        ImageArchitectureTuple(os="linux", arch="amd64"),
        ImageArchitectureTuple(os="unknown", arch="unknown"),
        ImageArchitectureTuple(os="linux", arch="arm"),
        ImageArchitectureTuple(os="unknown", arch="unknown"),
        ImageArchitectureTuple(os="linux", arch="arm64"),
        ImageArchitectureTuple(os="unknown", arch="unknown"),
        ImageArchitectureTuple(os="linux", arch="386"),
        ImageArchitectureTuple(os="unknown", arch="unknown"),
    ]
