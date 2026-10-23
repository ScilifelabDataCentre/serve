from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from django import forms
from django.core.exceptions import ValidationError
from django.test import override_settings

from apps.forms.mixins import ContainerImageMixin
from apps.helpers import validate_harbor_image
from apps.models import BaseAppInstance
from apps.validators.container_images import (
    ImageArchitectureTuple,
    PublicImageAccessOutcome,
    PublicImageAccessResult,
    validate_harbor_image_reference,
)

HOST = "harbor.serve-dev.scilifelab.se"


class ImageForm(ContainerImageMixin, forms.Form):
    image = forms.CharField(max_length=255)


@pytest.fixture(autouse=True)
def harbor_configuration(monkeypatch):
    checker = Mock()
    checker.check_public_accessibility.return_value = PublicImageAccessResult(PublicImageAccessOutcome.PUBLIC)
    monkeypatch.setattr("apps.harbor.OCIRegistryPublicChecker", Mock(return_value=checker))
    with override_settings(
        HARBOR_REGISTRY_HOST=HOST,
        HARBOR_PROXY_CACHE_ENABLED=False,
        HARBOR_DOCKERHUB_PROJECT="docker.io",
        HARBOR_GHCR_PROJECT="ghcr.io",
    ):
        yield checker


@pytest.mark.parametrize("project", ["docker.io/library", "ghcr.io/team", "preserved/team"])
def test_harbor_images_do_not_use_upstream_validators(monkeypatch, project):
    harbor = Mock()
    docker = Mock()
    github = Mock()
    monkeypatch.setattr("apps.forms.mixins.validate_harbor_image", harbor)
    monkeypatch.setattr("apps.forms.mixins.validate_docker_image", docker)
    monkeypatch.setattr("apps.forms.mixins.validate_ghcr_image", github)
    image = f"{HOST}/{project}/app:v1"
    form = ImageForm({"image": image})
    assert form.is_valid(), form.errors
    assert form.cleaned_data["image"] == image
    harbor.assert_called_once_with(image)
    docker.assert_not_called()
    github.assert_not_called()


def test_proxy_mapping_validates_harbor_but_keeps_source(monkeypatch, harbor_configuration):
    harbor = Mock()
    monkeypatch.setattr("apps.forms.mixins.validate_harbor_image", harbor)
    with override_settings(HARBOR_PROXY_CACHE_ENABLED=True):
        form = ImageForm({"image": "ghcr.io/team/app:v1"})
        assert form.is_valid(), form.errors
        assert form.cleaned_data["image"] == "ghcr.io/team/app:v1"
        harbor.assert_called_once_with(
            f"{HOST}/ghcr.io/team/app:v1",
            access=harbor_configuration.check_public_accessibility.return_value,
        )


@pytest.mark.parametrize("source", ["docker.io/library/alpine:3", "ghcr.io/team/app:v1"])
@pytest.mark.parametrize("outcome", [PublicImageAccessOutcome.PRIVATE, PublicImageAccessOutcome.REGISTRY_UNAVAILABLE])
def test_proxy_failure_uses_upstream_validation(monkeypatch, harbor_configuration, source, outcome):
    harbor_configuration.check_public_accessibility.return_value = PublicImageAccessResult(outcome)
    harbor = Mock()
    upstream = Mock()
    monkeypatch.setattr("apps.forms.mixins.validate_harbor_image", harbor)
    monkeypatch.setattr("apps.forms.mixins.validate_public_image", upstream)
    with override_settings(HARBOR_PROXY_CACHE_ENABLED=True):
        form = ImageForm({"image": source})
        assert form.is_valid(), form.errors
    upstream.assert_called_once_with(source)
    harbor.assert_not_called()
    assert form.cleaned_data["image"] == source


def test_proxy_fallback_still_rejects_invalid_source(monkeypatch, harbor_configuration):
    harbor_configuration.check_public_accessibility.return_value = PublicImageAccessResult(
        PublicImageAccessOutcome.REGISTRY_UNAVAILABLE
    )
    monkeypatch.setattr(
        "apps.forms.mixins.validate_public_image", Mock(side_effect=ValidationError("Source image is private"))
    )
    with override_settings(HARBOR_PROXY_CACHE_ENABLED=True):
        form = ImageForm({"image": "ghcr.io/team/app:v1"})
        assert not form.is_valid()
    assert "Source image is private" in str(form.errors["image"])


def test_proxy_validation_failure_retries_original_registry(monkeypatch):
    monkeypatch.setattr(
        "apps.forms.mixins.validate_harbor_image", Mock(side_effect=ValidationError("Could not reach Harbor"))
    )
    upstream = Mock()
    monkeypatch.setattr("apps.forms.mixins.validate_public_image", upstream)
    with override_settings(HARBOR_PROXY_CACHE_ENABLED=True):
        form = ImageForm({"image": "ghcr.io/team/app:v1"})
        assert form.is_valid(), form.errors
    upstream.assert_called_once_with("ghcr.io/team/app:v1")


def test_harbor_validation_error_is_shown_in_form(monkeypatch):
    monkeypatch.setattr(
        "apps.forms.mixins.validate_harbor_image", Mock(side_effect=ValidationError("Image unavailable"))
    )
    form = ImageForm({"image": f"{HOST}/ghcr.io/team/app:v1"})
    assert not form.is_valid()
    assert "Error validating Harbor image" in str(form.errors["image"])


@pytest.mark.parametrize(
    ("image", "validator"), [("ghcr.io/team/app:v1", "validate_ghcr_image"), ("alpine:3", "validate_docker_image")]
)
def test_upstream_validation_is_unchanged_when_proxy_is_disabled(monkeypatch, image, validator):
    validate = Mock()
    monkeypatch.setattr(f"apps.forms.mixins.{validator}", validate)
    form = ImageForm({"image": image})
    assert form.is_valid(), form.errors
    validate.assert_called_once_with(form.cleaned_data["image"])


def test_draft_does_not_contact_registry(monkeypatch):
    validate = Mock()
    monkeypatch.setattr("apps.forms.mixins.validate_harbor_image", validate)
    form = ImageForm({"image": f"{HOST}/ghcr.io/team/app:v1"})
    form._is_draft_access = True
    assert form.is_valid()
    validate.assert_not_called()


def test_harbor_does_not_override_image_field_help():
    form = ImageForm()
    form.instance = None
    original_help = (
        "Docker image with your application. For example, ghcr.io/username/image-name:image-tag "
        "or docker.io/username/image-name:image-tag."
    )
    form.image = forms.CharField(help_text=original_help)
    form._setup_container_image_field()
    assert form.fields["image"].help_text == original_help


@pytest.mark.parametrize("enabled", [True, False])
def test_generated_values_keep_source_image(enabled):
    app = SimpleNamespace(
        image="ghcr.io/team/app:v1",
        get_k8s_values=lambda: {"appconfig": {"image": "ghcr.io/team/app:v1", "port": 8080}},
    )
    with override_settings(HARBOR_PROXY_CACHE_ENABLED=enabled):
        BaseAppInstance.set_k8s_values(app)
    expected = f"{HOST}/ghcr.io/team/app:v1" if enabled else "ghcr.io/team/app:v1"
    assert app.k8s_values["appconfig"] == {"image": expected, "port": 8080}
    assert app.image == "ghcr.io/team/app:v1"


def test_values_without_an_image_are_unchanged():
    app = SimpleNamespace(get_k8s_values=lambda: {"namespace": "serve-dev"})
    BaseAppInstance.set_k8s_values(app)
    assert app.k8s_values == {"namespace": "serve-dev"}


@pytest.mark.parametrize("source", ["docker.io/library/alpine:3", "ghcr.io/team/app:v1"])
def test_deployment_values_use_upstream_when_proxy_fails(source, harbor_configuration):
    harbor_configuration.check_public_accessibility.return_value = PublicImageAccessResult(
        PublicImageAccessOutcome.REGISTRY_UNAVAILABLE
    )
    app = SimpleNamespace(image=source, get_k8s_values=lambda: {"appconfig": {"image": source}})
    with override_settings(HARBOR_PROXY_CACHE_ENABLED=True):
        BaseAppInstance.set_k8s_values(app)
    assert app.k8s_values["appconfig"]["image"] == source
    assert app.image == source


@pytest.mark.parametrize(
    "repository",
    [
        "project/app",
        "docker.io/library/alpine",
        "ghcr.io/team/nested/app",
        "project/app_name",
        "project/app__name",
        "project/app--name",
        "project/app.name",
    ],
)
def test_harbor_reference_format_accepts_repository_names(repository):
    assert validate_harbor_image_reference(f"{HOST}/{repository}:v1") == (HOST, repository, "v1")


@pytest.mark.parametrize("tag", ["v1", "latest", "1.2.3", "_test", "Release-1", "a" * 128])
def test_harbor_reference_format_accepts_tags(tag):
    assert validate_harbor_image_reference(f"{HOST}/project/app:{tag}") == (HOST, "project/app", tag)


def test_harbor_reference_format_accepts_digest():
    digest = "sha256:" + "a" * 64
    assert validate_harbor_image_reference(f"{HOST}/project/app@{digest}") == (HOST, "project/app", digest)


@pytest.mark.parametrize(
    "path",
    [
        "project",
        "project/../app:v1",
        "project//app:v1",
        "project/App:v1",
        "project/app:",
        "project/app:-bad",
        "project/app:tag with spaces",
        "project/app:é",
        "project/app:" + "a" * 129,
        "project/app@sha256:invalid",
    ],
)
def test_harbor_reference_format_rejects_invalid_input(path):
    with pytest.raises(ValidationError, match="Harbor image address"):
        validate_harbor_image_reference(f"{HOST}/{path}")


def test_harbor_reference_format_rejects_url_scheme():
    with pytest.raises(ValidationError, match="Harbor image address"):
        validate_harbor_image_reference(f"https://{HOST}/project/app:v1")


@pytest.mark.parametrize(
    "image", [f"{HOST}/project", f"{HOST}/project/../app:v1", f"{HOST}/project/app@sha256:invalid"]
)
def test_invalid_harbor_image_is_rejected_without_network(monkeypatch, image):
    check = Mock()
    monkeypatch.setattr("apps.helpers.OCIRegistryPublicChecker.check_public_accessibility", check)
    with pytest.raises(ValidationError, match="Harbor image address"):
        validate_harbor_image(image)
    check.assert_not_called()


@pytest.mark.parametrize(
    ("outcome", "message"),
    [
        (PublicImageAccessOutcome.PRIVATE, "could not be pulled anonymously"),
        (PublicImageAccessOutcome.REGISTRY_UNAVAILABLE, "Could not reach Harbor"),
    ],
)
def test_harbor_private_and_unavailable_images_fail_validation(monkeypatch, outcome, message):
    monkeypatch.setattr(
        "apps.helpers.OCIRegistryPublicChecker.check_public_accessibility",
        lambda self, repository, reference: PublicImageAccessResult(outcome),
    )
    with pytest.raises(ValidationError, match=message):
        validate_harbor_image(f"{HOST}/project/app:v1")


def test_harbor_multiarch_image_accepts_linux_amd64(monkeypatch):
    monkeypatch.setattr(
        "apps.helpers.OCIRegistryPublicChecker.check_public_accessibility",
        lambda self, repository, reference: PublicImageAccessResult(PublicImageAccessOutcome.PUBLIC),
    )
    monkeypatch.setattr("apps.helpers.waffle.switch_is_active", lambda name: True)
    monkeypatch.setattr(
        "apps.helpers.get_image_architectures",
        lambda **kwargs: [ImageArchitectureTuple("linux", "amd64"), ImageArchitectureTuple("linux", "arm64")],
    )
    image = f"{HOST}/project/app:v1"
    assert validate_harbor_image(image) == image


def test_harbor_arm_only_image_is_rejected(monkeypatch):
    monkeypatch.setattr(
        "apps.helpers.OCIRegistryPublicChecker.check_public_accessibility",
        lambda self, repository, reference: PublicImageAccessResult(PublicImageAccessOutcome.PUBLIC),
    )
    monkeypatch.setattr("apps.helpers.waffle.switch_is_active", lambda name: True)
    monkeypatch.setattr(
        "apps.helpers.get_image_architectures", lambda **kwargs: [ImageArchitectureTuple("linux", "arm64")]
    )
    with pytest.raises(ValidationError, match="linux/amd64"):
        validate_harbor_image(f"{HOST}/project/app:v1")
