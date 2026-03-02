from types import SimpleNamespace

import pytest

from apps.background_tasks.tasks.validation import ImagePublicValidator
from apps.validators.container_images import RegistryHost, parse_image_reference


@pytest.mark.parametrize(
    ("image", "expected_registry", "expected_repo", "expected_reference"),
    [
        ("python", "registry-1.docker.io", "library/python", "latest"),
        ("python:3.12", "registry-1.docker.io", "library/python", "3.12"),
        ("myuser/myapp:1.0.0", "registry-1.docker.io", "myuser/myapp", "1.0.0"),
        ("docker.io/python", "registry-1.docker.io", "library/python", "latest"),
        ("docker.io/library/ubuntu:24.04", "registry-1.docker.io", "library/ubuntu", "24.04"),
        ("registry-1.docker.io/library/python", "registry-1.docker.io", "library/python", "latest"),
        ("index.docker.io/library/nginx", "registry-1.docker.io", "library/nginx", "latest"),
        (
            "ghcr.io/scilifelabdatacentre/serve/serve-studio:develop-20260224",
            "ghcr.io",
            "scilifelabdatacentre/serve/serve-studio",
            "develop-20260224",
        ),
        ("localhost/myapp", "localhost", "myapp", "latest"),
        (
            "localhost:5000/team/app:1.2.3",
            "localhost:5000",
            "team/app",
            "1.2.3",
        ),
        (
            "docker.io/library/ubuntu@sha256:abc123",
            "registry-1.docker.io",
            "library/ubuntu",
            "sha256:abc123",
        ),
        (
            "ghcr.io/example/team-app@sha256:def456",
            "ghcr.io",
            "example/team-app",
            "sha256:def456",
        ),
        (
            "https://ghcr.io/example/team-app:stable",
            "ghcr.io",
            "example/team-app",
            "stable",
        ),
        (
            "http://registry.example.com/ns/app@sha256:deadbeef",
            "registry.example.com",
            "ns/app",
            "sha256:deadbeef",
        ),
        (
            "  ghcr.io/org/repo:tag-with-dashes  ",
            "ghcr.io",
            "org/repo",
            "tag-with-dashes",
        ),
        (
            "quay.io/org/repo",
            "quay.io",
            "org/repo",
            "latest",
        ),
        (
            "registry.example.com/myorg/myapp",
            "registry.example.com",
            "myorg/myapp",
            "latest",
        ),
    ],
)
def test_parse_image_reference_cases(image, expected_registry, expected_repo, expected_reference):
    registry, repo, reference = parse_image_reference(image)

    assert registry == expected_registry
    assert repo == expected_repo
    assert reference == expected_reference


def test_parse_image_reference_known_hosts_return_enum():
    registry, _, _ = parse_image_reference("ghcr.io/org/repo:tag")
    assert isinstance(registry, RegistryHost)
    assert registry is RegistryHost.GHCR

    docker_registry, _, _ = parse_image_reference("python:3.12")
    assert isinstance(docker_registry, RegistryHost)
    assert docker_registry is RegistryHost.DOCKER_HUB


def test_validate_image_public_success(monkeypatch):
    app_instance = SimpleNamespace(image="ghcr.io/example/team-app:stable", environment=None, k8s_values={})

    monkeypatch.setattr(
        "apps.validators.container_images.OCIRegistryPublicChecker.is_public",
        lambda self, repository, reference: True,
    )

    result = ImagePublicValidator().execute(app_instance)

    assert result["valid"] is True
    assert result["public"] is True
    assert result["registry"] == "ghcr.io"
    assert result["repo"] == "example/team-app"
    assert result["reference"] == "stable"


def test_validate_image_public_failure(monkeypatch):
    app_instance = SimpleNamespace(image="ghcr.io/example/team-app:stable", environment=None, k8s_values={})

    monkeypatch.setattr(
        "apps.validators.container_images.OCIRegistryPublicChecker.is_public",
        lambda self, repository, reference: False,
    )

    with pytest.raises(ValueError, match="not publicly pullable"):
        ImagePublicValidator().execute(app_instance)
