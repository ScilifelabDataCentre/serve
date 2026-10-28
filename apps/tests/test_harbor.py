from types import SimpleNamespace
from unittest.mock import Mock
from urllib.parse import parse_qs, urlparse

import pytest
import requests
from django.test import override_settings

from apps.harbor import (
    HarborAuthenticator,
    get_deployment_image,
    get_harbor_registry_host,
    is_harbor_registry,
    resolve_deployment_image,
)
from apps.validators.container_images import (
    ContainerImageValidationError,
    ImageArchitectureTuple,
    PublicImageAccessOutcome,
    PublicImageAccessResult,
    get_authenticator_for_registry,
    get_container_image_context,
    get_image_architectures,
)

HOST = "harbor.serve-dev.scilifelab.se"


@pytest.fixture(autouse=True)
def harbor_configuration(monkeypatch):
    checker = Mock()
    checker.check_public_accessibility.return_value = PublicImageAccessResult(PublicImageAccessOutcome.PUBLIC)
    monkeypatch.setattr("apps.harbor.OCIRegistryPublicChecker", Mock(return_value=checker))
    with override_settings(
        HARBOR_REGISTRY_HOST=HOST,
        HARBOR_PROXY_CACHE_ENABLED=True,
        HARBOR_DOCKERHUB_PROJECT="docker.io",
        HARBOR_GHCR_PROJECT="ghcr.io",
    ):
        yield checker


@pytest.mark.parametrize(
    ("source", "repository", "reference"),
    [
        ("alpine", "docker.io/library/alpine", ":latest"),
        ("alpine:3", "docker.io/library/alpine", ":3"),
        ("docker.io/alpine:3", "docker.io/library/alpine", ":3"),
        ("registry-1.docker.io/library/alpine:3", "docker.io/library/alpine", ":3"),
        ("index.docker.io/team/app:v1", "docker.io/team/app", ":v1"),
        ("team/app:v1", "docker.io/team/app", ":v1"),
        ("ghcr.io/team/nested/app:v1", "ghcr.io/team/nested/app", ":v1"),
        ("ghcr.io/team/app@sha256:abc123", "ghcr.io/team/app", "@sha256:abc123"),
        ("docker.io/library/alpine@sha256:abc123", "docker.io/library/alpine", "@sha256:abc123"),
    ],
)
def test_map_upstream_image(source, repository, reference):
    assert get_deployment_image(source) == f"{HOST}/{repository}{reference}"


@pytest.mark.parametrize("image", ["", "quay.io/team/app:v1", "localhost:5000/app:v1", f"{HOST}/ghcr.io/team/app:v1"])
def test_other_registries_and_harbor_are_unchanged(image):
    assert get_deployment_image(image) == image


def test_mapping_is_idempotent():
    image = get_deployment_image("alpine:3")
    assert get_deployment_image(image) == image


def test_proxy_cache_is_opt_in():
    with override_settings(HARBOR_PROXY_CACHE_ENABLED=False):
        assert get_deployment_image("alpine:3") == "alpine:3"
        assert get_deployment_image("ghcr.io/team/app:v1") == "ghcr.io/team/app:v1"


def test_configurable_project_names():
    with override_settings(HARBOR_DOCKERHUB_PROJECT="proxy-dockerhub", HARBOR_GHCR_PROJECT="proxy-ghcr"):
        assert get_deployment_image("alpine:3") == f"{HOST}/proxy-dockerhub/library/alpine:3"
        assert get_deployment_image("ghcr.io/team/app:v1") == f"{HOST}/proxy-ghcr/team/app:v1"


def test_runtime_helpers_do_not_check_configuration_or_call_harbor(monkeypatch):
    request = Mock(side_effect=AssertionError("Runtime helpers must not call Harbor."))
    monkeypatch.setattr("requests.get", request)
    with override_settings(HARBOR_REGISTRY_HOST=f"  {HOST.upper()}  "):
        assert get_harbor_registry_host() == HOST
        assert is_harbor_registry(HOST)
        assert get_deployment_image("alpine:3") == f"{HOST}/docker.io/library/alpine:3"
    request.assert_not_called()


def test_hostname_reader_does_not_validate_settings():
    with override_settings(HARBOR_REGISTRY_HOST="https://wrong.example.com/path"):
        assert get_harbor_registry_host() == "https://wrong.example.com/path"


@pytest.mark.parametrize("source", ["docker.io/library/alpine:3", "ghcr.io/team/app:v1"])
def test_available_proxy_is_used(source, harbor_configuration):
    assert resolve_deployment_image(source) == get_deployment_image(source)
    harbor_configuration.check_public_accessibility.assert_called_once()
    assert harbor_configuration.check_public_accessibility.call_args.kwargs["max_5xx_retries"] == 0


@pytest.mark.parametrize("source", ["docker.io/library/alpine:3", "ghcr.io/team/app:v1"])
@pytest.mark.parametrize("outcome", [PublicImageAccessOutcome.PRIVATE, PublicImageAccessOutcome.REGISTRY_UNAVAILABLE])
def test_unavailable_proxy_falls_back_to_source(source, outcome, harbor_configuration):
    harbor_configuration.check_public_accessibility.return_value = PublicImageAccessResult(outcome)
    assert resolve_deployment_image(source) == source


@pytest.mark.parametrize("error", [requests.Timeout, requests.exceptions.InvalidURL, ValueError])
def test_proxy_request_error_falls_back_to_source(error, harbor_configuration):
    harbor_configuration.check_public_accessibility.side_effect = error
    assert resolve_deployment_image("alpine:3") == "alpine:3"


@pytest.mark.parametrize(
    "configuration",
    [
        {"HARBOR_REGISTRY_HOST": ""},
        {"HARBOR_REGISTRY_HOST": "https://harbor.example.com"},
        {"HARBOR_DOCKERHUB_PROJECT": ""},
        {"HARBOR_DOCKERHUB_PROJECT": "../wrong"},
        {"HARBOR_PROXY_CACHE_ENABLED": False},
    ],
)
def test_missing_or_invalid_proxy_configuration_uses_source(configuration, harbor_configuration):
    with override_settings(**configuration):
        assert resolve_deployment_image("alpine:3") == "alpine:3"
    harbor_configuration.check_public_accessibility.assert_not_called()


def test_direct_harbor_and_other_registries_are_not_resolved(harbor_configuration):
    for image in (f"{HOST}/project/app:v1", "quay.io/team/app:v1", ""):
        assert resolve_deployment_image(image) == image
    harbor_configuration.check_public_accessibility.assert_not_called()


@pytest.mark.parametrize("source", ["docker.io/library/alpine:3", "ghcr.io/team/app:v1"])
def test_background_validation_uses_source_auth_when_proxy_fails(source, harbor_configuration):
    harbor_configuration.check_public_accessibility.return_value = PublicImageAccessResult(
        PublicImageAccessOutcome.REGISTRY_UNAVAILABLE
    )
    app = SimpleNamespace(image=source, environment=None, k8s_values={})
    context = get_container_image_context(app)
    assert context.image == source
    assert not isinstance(context.auth, HarborAuthenticator)
    assert app.image == source


def test_harbor_hostname_matches_exactly():
    assert is_harbor_registry(HOST)
    assert not is_harbor_registry(f"{HOST}.example.com")
    assert not is_harbor_registry("ghcr.io")
    with override_settings(HARBOR_REGISTRY_HOST=""):
        assert not is_harbor_registry(HOST)


def test_harbor_authenticator_is_available_without_proxy_mapping():
    with override_settings(HARBOR_PROXY_CACHE_ENABLED=False):
        assert isinstance(get_authenticator_for_registry(HOST), HarborAuthenticator)
    assert get_authenticator_for_registry("unconfigured.example.com") is None


def test_harbor_token_request(monkeypatch):
    request = Mock(return_value=Mock(status_code=200, json=lambda: {"token": "pull-token"}))
    monkeypatch.setattr("apps.harbor.requests.get", request)
    assert HarborAuthenticator(HOST).get_bearer_token("ghcr.io/team/app") == "pull-token"
    url = urlparse(request.call_args.args[0])
    assert url.scheme == "https"
    assert url.netloc == HOST
    assert url.path == "/service/token"
    assert parse_qs(url.query) == {"service": ["harbor-registry"], "scope": ["repository:ghcr.io/team/app:pull"]}
    assert request.call_args.kwargs == {"timeout": 10, "allow_redirects": False}


@pytest.mark.parametrize(("status", "retryable"), [(401, False), (403, False), (429, True), (503, True)])
def test_harbor_token_failure(monkeypatch, status, retryable):
    monkeypatch.setattr("apps.harbor.requests.get", Mock(return_value=Mock(status_code=status)))
    with pytest.raises(ContainerImageValidationError) as error:
        HarborAuthenticator(HOST).get_bearer_token("project/app")
    assert error.value.retryable is retryable


def test_harbor_token_timeout(monkeypatch):
    monkeypatch.setattr("apps.harbor.requests.get", Mock(side_effect=requests.Timeout))
    with pytest.raises(ContainerImageValidationError) as error:
        HarborAuthenticator(HOST).get_bearer_token("project/app")
    assert error.value.retryable is True


@pytest.mark.parametrize("data", [{}, {"access_token": "pull-token"}])
def test_harbor_token_response(monkeypatch, data):
    monkeypatch.setattr("apps.harbor.requests.get", Mock(return_value=Mock(status_code=200, json=lambda: data)))
    if data:
        assert HarborAuthenticator(HOST).get_bearer_token("project/app") == "pull-token"
    else:
        with pytest.raises(ContainerImageValidationError, match="did not return"):
            HarborAuthenticator(HOST).get_bearer_token("project/app")


def test_validation_uses_deployment_image_without_changing_source():
    app = SimpleNamespace(image="ghcr.io/team/app:v1", environment=None, k8s_values={})
    context = get_container_image_context(app)
    assert context.image == f"{HOST}/ghcr.io/team/app:v1"
    assert context.repo == "ghcr.io/team/app"
    assert isinstance(context.auth, HarborAuthenticator)
    assert app.image == "ghcr.io/team/app:v1"


def test_harbor_single_platform_architecture(monkeypatch):
    auth = HarborAuthenticator(HOST)
    monkeypatch.setattr(auth, "get_bearer_token", lambda repo: "pull-token")
    request = Mock(
        side_effect=[
            Mock(status_code=200, json=lambda: {"config": {"digest": "sha256:config"}}),
            Mock(status_code=200, json=lambda: {"os": "linux", "architecture": "amd64"}),
        ]
    )
    monkeypatch.setattr("apps.validators.container_images.requests.get", request)
    assert get_image_architectures(auth=auth, repo="project/app", reference="v1", registry=HOST) == [
        ImageArchitectureTuple(os="linux", arch="amd64")
    ]
    assert request.call_args_list[0].args[0] == f"https://{HOST}/v2/project/app/manifests/v1"
    assert request.call_args_list[1].args[0] == f"https://{HOST}/v2/project/app/blobs/sha256:config"


def test_harbor_manifest_timeout_is_retryable(monkeypatch):
    auth = HarborAuthenticator(HOST)
    monkeypatch.setattr(auth, "get_bearer_token", lambda repo: "pull-token")
    monkeypatch.setattr("apps.validators.container_images.requests.get", Mock(side_effect=requests.Timeout))
    with pytest.raises(ContainerImageValidationError) as error:
        get_image_architectures(auth=auth, repo="project/app", reference="v1", registry=HOST)
    assert error.value.retryable is True
