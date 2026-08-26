"""Tests for SourceCodeUrlValidator using CustomAppInstance."""

from unittest.mock import MagicMock

import pytest
import requests
from django.contrib.auth import get_user_model

from apps.background_tasks.tasks.validation import SourceCodeUrlValidator
from apps.models import (
    Apps,
    BaseAppInstance,
    CustomAppInstance,
    K8sUserAppStatus,
    Subdomain,
)
from projects.models import Project

User = get_user_model()


def _make_custom_app(**kwargs):
    user = User.objects.create_user("scurl_user", "scurl@test.com", "pw")
    project = Project.objects.create_project(name="scurl-project", owner=user, description="")
    app = Apps.objects.create(name="SC URL App", slug="customapp")
    subdomain = Subdomain.objects.create(subdomain=f"scurl-{project.id}-{app.id}", project=project)
    k8s = K8sUserAppStatus.objects.create()
    defaults = dict(
        owner=user,
        project=project,
        app=app,
        chart="custom-app",
        name="Source code URL test",
        subdomain=subdomain,
        k8s_user_app_status=k8s,
        access="public",
        port=8000,
        image="ghcr.io/example/scurl-test:tag",
    )
    defaults.update(kwargs)
    return CustomAppInstance.objects.create(**defaults)


@pytest.mark.django_db
def test_source_code_url_validator_skips_when_empty():
    instance = _make_custom_app(source_code_url="")

    result = SourceCodeUrlValidator().execute(instance)

    assert result["valid"] is True
    assert result["skipped"] is True
    assert result["reason"] == "no source code URL"


@pytest.mark.django_db
def test_source_code_url_validator_skips_when_whitespace_only():
    instance = _make_custom_app(source_code_url="   \t  ")

    result = SourceCodeUrlValidator().execute(instance)

    assert result["valid"] is True
    assert result["skipped"] is True
    assert result["reason"] == "no source code URL"


@pytest.mark.django_db
def test_source_code_url_validator_success_on_head_200(monkeypatch):
    instance = _make_custom_app(source_code_url="https://example.org/repo")

    mock_resp = MagicMock()
    mock_resp.status_code = 200

    monkeypatch.setattr(
        "apps.background_tasks.tasks.validation.requests.head",
        lambda *a, **kw: mock_resp,
    )

    result = SourceCodeUrlValidator().execute(instance)

    assert result["valid"] is True
    assert result["url"] == "https://example.org/repo"
    assert result["status_code"] == 200


@pytest.mark.django_db
def test_source_code_url_validator_resolves_url_when_fk_is_base_app_row(monkeypatch):
    """
    BackgroundTask.app_instance is a BaseAppInstance FK; the parent row must be
    resolved to the concrete model so source_code_url (on SocialMixin) is visible.
    """
    custom = _make_custom_app(source_code_url="https://example.org/from-child-table")
    base_row = BaseAppInstance.objects.get(pk=custom.pk)
    assert base_row.__class__ is BaseAppInstance

    mock_resp = MagicMock()
    mock_resp.status_code = 200

    monkeypatch.setattr(
        "apps.background_tasks.tasks.validation.requests.head",
        lambda *a, **kw: mock_resp,
    )

    result = SourceCodeUrlValidator().execute(base_row)

    assert result["valid"] is True
    assert result["url"] == "https://example.org/from-child-table"
    assert result["status_code"] == 200


@pytest.mark.django_db
def test_source_code_url_validator_falls_back_to_get_on_head_405(monkeypatch):
    instance = _make_custom_app(source_code_url="https://example.org/repo")

    head_resp = MagicMock()
    head_resp.status_code = 405

    get_resp = MagicMock()
    get_resp.status_code = 200
    get_resp.close = MagicMock()

    monkeypatch.setattr(
        "apps.background_tasks.tasks.validation.requests.head",
        lambda *a, **kw: head_resp,
    )
    monkeypatch.setattr(
        "apps.background_tasks.tasks.validation.requests.get",
        lambda *a, **kw: get_resp,
    )

    result = SourceCodeUrlValidator().execute(instance)

    assert result["valid"] is True
    assert result["status_code"] == 200
    get_resp.close.assert_called_once()


@pytest.mark.django_db
def test_source_code_url_validator_non_2xx_fails_task(monkeypatch):
    instance = _make_custom_app(source_code_url="https://example.org/missing")

    mock_resp = MagicMock()
    mock_resp.status_code = 404

    monkeypatch.setattr(
        "apps.background_tasks.tasks.validation.requests.head",
        lambda *a, **kw: mock_resp,
    )

    with pytest.raises(ValueError, match="returned unreachable"):
        SourceCodeUrlValidator().execute(instance)


@pytest.mark.django_db
def test_source_code_url_validator_head_network_error_fails_task(monkeypatch):
    instance = _make_custom_app(source_code_url="https://example.org/repo")

    def boom(*a, **kw):
        raise requests.ConnectionError("refused")

    monkeypatch.setattr("apps.background_tasks.tasks.validation.requests.head", boom)

    with pytest.raises(ValueError, match="unreachable"):
        SourceCodeUrlValidator().execute(instance)
