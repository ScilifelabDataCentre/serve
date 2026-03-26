from unittest.mock import Mock, patch

import pytest
import requests
from django.conf import settings

from apps.background_tasks.tasks.validation import DockerImageValidator
from apps.validators.container_images import (
    ContainerImageValidationError,
    DockerHubAuthenticator,
    GHCRAuthenticator,
    ImageArchitectureTuple,
    get_image_architectures,
)


@pytest.mark.integration
def test_ghcr_architecture_is_valid():
    architectures = get_image_architectures(
        auth=GHCRAuthenticator(),
        repo="scilifelabdatacentre/serve-jupyterlab",
        reference="250204-1056",
        registry="ghcr.io",
    )
    assert len(architectures) > 0
    assert architectures == [ImageArchitectureTuple(os="linux", arch="amd64")]


@pytest.mark.integration
def test_get_anonymous_bearer_token():
    auth = GHCRAuthenticator()
    token = auth.get_token_service_url("scilifelabdatacentre/serve-jupyterlab")
    resp = requests.get(token)
    assert resp.status_code == 200, f"Failed to get anonymous bearer token: {resp.status_code} {resp.text}"
    assert "token" in resp.json(), "Token not found in response"


@pytest.mark.integration
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


def test_missing_image_returns_friendly_validation_error():
    auth = Mock()
    auth.get_bearer_token.return_value = "token"
    response = Mock(status_code=404, text='{"errors":[{"code":"MANIFEST_UNKNOWN"}]}')

    with patch("apps.validators.container_images.requests.get", return_value=response):
        with pytest.raises(ContainerImageValidationError, match="could not find the container image"):
            get_image_architectures(
                auth=auth,
                repo="scilifelabdatacentre/missing-image",
                reference="does-not-exist",
                registry="ghcr.io",
            )


def test_docker_image_validator_does_not_retry_missing_image_errors():
    validator = DockerImageValidator()

    assert validator.should_retry(ContainerImageValidationError("missing image"), retry_count=0) is False


def test_docker_image_validator_retries_transient_registry_errors():
    validator = DockerImageValidator()

    assert validator.should_retry(
        ContainerImageValidationError("temporary registry outage", retryable=True),
        retry_count=0,
    ) is True


def test_transient_manifest_lookup_errors_are_marked_retryable():
    auth = Mock()
    auth.get_bearer_token.return_value = "token"
    response = Mock(status_code=503, text="service unavailable")

    with patch("apps.validators.container_images.requests.get", return_value=response):
        with pytest.raises(ContainerImageValidationError) as excinfo:
            get_image_architectures(
                auth=auth,
                repo="scilifelabdatacentre/example-image",
                reference="latest",
                registry="ghcr.io",
            )

    assert excinfo.value.retryable is True
