from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from django.contrib import admin
from django.test import RequestFactory, override_settings

from apps.admin import BaseAppAdmin
from apps.harbor import (
    HarborAuthenticator,
    ImageResolution,
    get_instance_deployment_image,
    remember_deployment_image,
    reset_image_resolution,
    resolve_deployment_image,
)
from apps.helpers import save_instance_and_related_data
from apps.models import Apps, BaseAppInstance, DashInstance, Subdomain
from apps.tasks import deploy_resource
from apps.tests.test_harbor_forms import ImageForm
from apps.validators.container_images import (
    ContainerImageValidationError,
    OCIRegistryPublicChecker,
    PublicImageAccessOutcome,
    PublicImageAccessResult,
    get_container_image_context,
)
from projects.models import Project

HOST = "harbor.example.com"
SOURCE = "ghcr.io/team/app:v1"
PROXY = f"{HOST}/ghcr.io/team/app:v1"
PUBLIC = PublicImageAccessResult(PublicImageAccessOutcome.PUBLIC)
UNAVAILABLE = PublicImageAccessResult(PublicImageAccessOutcome.REGISTRY_UNAVAILABLE)
MANIFEST = {
    "schemaVersion": 2,
    "mediaType": "application/vnd.oci.image.manifest.v1+json",
    "config": {"digest": "sha256:" + "a" * 64},
    "layers": [],
}


@pytest.fixture(autouse=True)
def harbor_configuration():
    with override_settings(
        HARBOR_REGISTRY_HOST=HOST,
        HARBOR_PROXY_CACHE_ENABLED=True,
        HARBOR_DOCKERHUB_PROJECT="docker.io",
        HARBOR_GHCR_PROJECT="ghcr.io",
    ):
        yield


def make_instance(source=SOURCE):
    return SimpleNamespace(
        image=source,
        environment=None,
        info={"existing": "keep"},
        k8s_values={},
        get_k8s_values=lambda: {"appconfig": {"image": source}},
    )


@pytest.mark.parametrize("first_result", [PUBLIC, UNAVAILABLE])
def test_validation_and_deployment_share_one_selection(first_result):
    instance = make_instance()
    checker = Mock()
    checker.check_public_accessibility.side_effect = [first_result, UNAVAILABLE if first_result == PUBLIC else PUBLIC]
    with patch("apps.harbor.OCIRegistryPublicChecker", return_value=checker):
        context = get_container_image_context(instance)
        BaseAppInstance.set_k8s_values(instance)
        BaseAppInstance.set_k8s_values(instance)
    assert instance.k8s_values["appconfig"]["image"] == context.image
    assert context.image == (PROXY if first_result == PUBLIC else SOURCE)
    checker.check_public_accessibility.assert_called_once()
    assert instance.image == SOURCE
    assert instance.info["existing"] == "keep"


def test_new_deployment_can_select_harbor_after_previous_fallback():
    instance = make_instance()
    remember_deployment_image(instance, SOURCE, SOURCE)
    reset_image_resolution(instance)
    checker = Mock()
    checker.check_public_accessibility.return_value = PUBLIC
    with patch("apps.harbor.OCIRegistryPublicChecker", return_value=checker):
        assert get_instance_deployment_image(instance, SOURCE) == PROXY
    assert instance.info["existing"] == "keep"


def test_changing_source_does_not_reuse_previous_selection():
    instance = make_instance()
    remember_deployment_image(instance, SOURCE, SOURCE)
    checker = Mock()
    checker.check_public_accessibility.return_value = PUBLIC
    with patch("apps.harbor.OCIRegistryPublicChecker", return_value=checker):
        assert get_instance_deployment_image(instance, "ghcr.io/team/other:v2") == f"{HOST}/ghcr.io/team/other:v2"


def test_draft_does_not_resolve_proxy():
    instance = make_instance()
    instance.latest_user_action = "Draft"
    with patch("apps.harbor.OCIRegistryPublicChecker") as checker:
        assert get_instance_deployment_image(instance, SOURCE) == SOURCE
    checker.assert_not_called()


def test_successful_form_does_not_repeat_proxy_access_check():
    checker = Mock()
    checker.check_public_accessibility.return_value = PUBLIC
    with (
        patch("apps.harbor.OCIRegistryPublicChecker", return_value=checker),
        patch("apps.helpers.OCIRegistryPublicChecker") as duplicate,
        patch("apps.helpers.waffle.switch_is_active", return_value=False),
    ):
        form = ImageForm({"image": SOURCE})
        assert form.is_valid(), form.errors
    checker.check_public_accessibility.assert_called_once()
    duplicate.assert_not_called()
    assert form.image_resolution.image == PROXY


@pytest.mark.parametrize(
    "source",
    [
        "ghcr.io/team/nested/app:v1",
        "ghcr.io/team/app@sha256:" + "a" * 64,
        "docker.io/library/alpine@sha256:" + "a" * 64,
    ],
)
def test_fallback_supports_nested_paths_and_digests(source):
    proxy_checker = Mock()
    proxy_checker.check_public_accessibility.return_value = UNAVAILABLE
    upstream_checker = Mock()
    upstream_checker.check_public_accessibility.return_value = PUBLIC
    with (
        patch("apps.harbor.OCIRegistryPublicChecker", return_value=proxy_checker),
        patch("apps.helpers.OCIRegistryPublicChecker", return_value=upstream_checker),
        patch("apps.helpers.waffle.switch_is_active", return_value=False),
    ):
        form = ImageForm({"image": source})
        assert form.is_valid(), form.errors
    assert form.image_resolution.image == source
    upstream_checker.check_public_accessibility.assert_called_once()


@pytest.mark.parametrize("body", [None, [], "unexpected", {}, {"token": 123}, {"token": []}, {"token": "   "}])
def test_malformed_harbor_tokens_raise_controlled_error(body):
    with patch("apps.harbor.requests.get", return_value=Mock(status_code=200, json=lambda: body)):
        with pytest.raises(ContainerImageValidationError):
            HarborAuthenticator(HOST).get_bearer_token("project/app")


@pytest.mark.parametrize("body", [None, [], "unexpected", {"token": 123}, {"token": []}])
def test_malformed_oci_tokens_are_handled(body):
    checker = OCIRegistryPublicChecker(HOST)
    with patch.object(checker.session, "get", return_value=Mock(status_code=200, json=lambda: body)):
        assert checker._fetch_token(f"https://{HOST}/service/token", "registry", "scope") == (None, 200)


@pytest.mark.parametrize(
    "body",
    [
        None,
        [],
        {},
        {"schemaVersion": 2},
        {**MANIFEST, "mediaType": "text/html"},
        {**MANIFEST, "mediaType": "application/vnd.oci.image.index.v1+json"},
    ],
)
def test_non_manifest_json_does_not_select_harbor(body):
    response = Mock(status_code=200, headers={}, json=lambda: body)
    with patch("requests.Session.get", return_value=response):
        assert resolve_deployment_image(SOURCE) == SOURCE


def test_html_200_does_not_select_harbor():
    response = Mock(status_code=200, headers={"Content-Type": "text/html"})
    response.json.side_effect = ValueError
    with patch("requests.Session.get", return_value=response), patch("requests.Session.head") as head:
        assert resolve_deployment_image(SOURCE) == SOURCE
    head.assert_not_called()


@pytest.mark.parametrize(
    "manifest",
    [MANIFEST, {"schemaVersion": 2, "mediaType": "application/vnd.oci.image.index.v1+json", "manifests": []}],
)
def test_real_manifest_response_selects_harbor(manifest):
    with patch("requests.Session.get", return_value=Mock(status_code=200, json=lambda: manifest)):
        assert resolve_deployment_image(SOURCE) == PROXY


def test_authenticated_manifest_response_selects_harbor():
    challenge = Mock(
        status_code=401,
        headers={"WWW-Authenticate": f'Bearer realm="https://{HOST}/service/token",service="harbor-registry"'},
    )
    responses = [
        challenge,
        Mock(status_code=200, json=lambda: {"token": "pull-token"}),
        Mock(status_code=200, json=lambda: MANIFEST),
    ]
    with patch("requests.Session.get", side_effect=responses) as request:
        assert resolve_deployment_image(SOURCE) == PROXY
    assert request.call_count == 3


@pytest.fixture
def database_instance(db, django_user_model):
    owner = django_user_model.objects.create_user("harbor-resolution", "harbor@example.com", "password")
    project = Project.objects.create_project(name="harbor-resolution", owner=owner, description="")
    app = Apps.objects.create(name="Dash", slug="dashapp")
    subdomain = Subdomain.objects.create(subdomain="harbor-resolution", project=project)
    return DashInstance.objects.create(
        app=app, project=project, owner=owner, subdomain=subdomain, name="Harbor test", image=SOURCE, chart="chart"
    )


def test_selection_survives_database_reload(database_instance):
    checker = Mock()
    checker.check_public_accessibility.return_value = UNAVAILABLE
    with patch("apps.harbor.OCIRegistryPublicChecker", return_value=checker):
        assert get_container_image_context(database_instance).image == SOURCE
        reloaded = DashInstance.objects.get(pk=database_instance.pk)
        checker.check_public_accessibility.return_value = PUBLIC
        reloaded.set_k8s_values()
    assert reloaded.k8s_values["appconfig"]["image"] == SOURCE
    checker.check_public_accessibility.assert_called_once()


def test_form_selection_is_saved_without_another_probe(database_instance):
    form = SimpleNamespace(image_resolution=ImageResolution(SOURCE), cleaned_data={"image": SOURCE}, save_m2m=Mock())
    with patch("apps.harbor.OCIRegistryPublicChecker") as checker:
        save_instance_and_related_data(database_instance, form)
    checker.assert_not_called()
    reloaded = DashInstance.objects.get(pk=database_instance.pk)
    assert reloaded.info["image_resolution"]["image"] == SOURCE
    assert reloaded.k8s_values["appconfig"]["image"] == SOURCE


def test_helm_result_preserves_image_selection(database_instance):
    remember_deployment_image(database_instance, SOURCE, SOURCE)
    database_instance.save(update_fields=["info"])
    with (
        override_settings(DEBUG=False),
        patch("apps.tasks.helm_install", return_value=("installed", None)),
        patch("apps.harbor.OCIRegistryPublicChecker") as checker,
    ):
        deploy_resource.run(database_instance.serialize())
    checker.assert_not_called()
    database_instance.refresh_from_db()
    assert database_instance.info["image_resolution"]["image"] == SOURCE
    assert database_instance.info["helm"]["success"] is True


def test_admin_redeployment_makes_a_fresh_selection(database_instance):
    remember_deployment_image(database_instance, SOURCE, SOURCE)
    database_instance.save(update_fields=["info"])
    model_admin = BaseAppAdmin(DashInstance, admin.site)
    checker = Mock()
    checker.check_public_accessibility.return_value = PUBLIC
    with (
        patch("apps.harbor.OCIRegistryPublicChecker", return_value=checker),
        patch("apps.admin.deploy_resource.delay"),
        patch.object(model_admin, "message_user"),
    ):
        model_admin.deploy_resources(
            RequestFactory().post("/admin/redeploy"), DashInstance.objects.filter(pk=database_instance.pk)
        )
    database_instance.refresh_from_db()
    assert database_instance.info["image_resolution"]["image"] == PROXY
    assert database_instance.k8s_values["appconfig"]["image"] == PROXY
    checker.check_public_accessibility.assert_called_once()
