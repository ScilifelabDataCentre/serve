from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.db import transaction

from apps.app_registry import APP_REGISTRY
from apps.helpers import create_instance_from_form
from apps.models import Apps
from projects.models import Flavor, Project

User = get_user_model()


@pytest.fixture()
def immediate_on_commit(monkeypatch):
    """Run transaction.on_commit callbacks immediately in unit tests."""

    def _on_commit(func, using=None):  # signature-compatible
        func()

    monkeypatch.setattr(transaction, "on_commit", _on_commit)


@pytest.mark.django_db
def test_background_tasks_switch_off_falls_back_to_direct_deploy(immediate_on_commit):
    user = User.objects.create_user("u1", "u1@test.com", "pw")
    project = Project.objects.create_project(name="p1", owner=user, description="")
    flavor = Flavor.objects.create(name="flavor", project=project)

    app_slug = "dashapp"
    _ = Apps.objects.create(name="Dash", slug=app_slug, user_can_delete=False)

    data = {
        "name": "test-app",
        "description": "desc",
        "flavor": str(flavor.pk),
        "access": "public",
        "port": 8000,
        "image": "some-image",
        "source_code_url": "https://example.com",
    }

    _, form_class = APP_REGISTRY.get(app_slug)
    form = form_class(data, project_pk=project.pk)
    assert form.is_valid(), form.errors

    def _switch(name: str) -> bool:
        return name == "background_tasks" and False

    with patch("apps.helpers.waffle.switch_is_active", side_effect=_switch), patch(
        "apps.tasks.deploy_resource.delay"
    ) as mock_deploy, patch("apps.tasks.run_background_tasks.delay") as mock_bg:
        _ = create_instance_from_form(form, project, app_slug, app_id=None)

    mock_bg.assert_not_called()
    mock_deploy.assert_called_once()


@pytest.mark.django_db
def test_background_tasks_switch_on_uses_orchestrator(immediate_on_commit):
    user = User.objects.create_user("u1", "u1@test.com", "pw")
    project = Project.objects.create_project(name="p1", owner=user, description="")
    flavor = Flavor.objects.create(name="flavor", project=project)

    app_slug = "dashapp"
    _ = Apps.objects.create(name="Dash", slug=app_slug, user_can_delete=False)

    data = {
        "name": "test-app",
        "description": "desc",
        "flavor": str(flavor.pk),
        "access": "public",
        "port": 8000,
        "image": "some-image",
        "source_code_url": "https://example.com",
    }

    _, form_class = APP_REGISTRY.get(app_slug)
    form = form_class(data, project_pk=project.pk)
    assert form.is_valid(), form.errors

    def _switch(name: str) -> bool:
        return name == "background_tasks"

    with patch("apps.helpers.waffle.switch_is_active", side_effect=_switch), patch(
        "apps.tasks.deploy_resource.delay"
    ) as mock_deploy, patch("apps.tasks.run_background_tasks.delay") as mock_bg:
        _ = create_instance_from_form(form, project, app_slug, app_id=None)

    mock_deploy.assert_not_called()
    mock_bg.assert_called_once()
