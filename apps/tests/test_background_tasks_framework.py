import types
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from apps.background_tasks.base import BaseBackgroundTask
from apps.background_tasks.registry import TASK_REGISTRY, BackgroundTaskRegistry
from apps.models import Apps, BackgroundTask, BaseAppInstance
from apps.tasks import (
    check_tasks_and_deploy,
    deploy_resource,
    execute_single_background_task,
    retry_background_task,
    run_background_tasks,
)
from projects.models import Project

User = get_user_model()


@pytest.mark.django_db
def test_known_tasks_are_registered_after_django_startup():
    # Registration should happen deterministically via AppsConfig.ready().
    assert TASK_REGISTRY.is_registered("validate_docker_image") is True
    assert TASK_REGISTRY.is_registered("validate_image_public") is True
    assert TASK_REGISTRY.is_registered("validate_source_code_url") is True
    assert TASK_REGISTRY.is_registered("doi_provisioning") is True


@pytest.mark.django_db
def test_known_tasks_apply_to_non_custom_app_types():
    streamlit_tasks = TASK_REGISTRY.get_tasks_for_app("streamlit")
    dash_tasks = TASK_REGISTRY.get_tasks_for_app("dashapp")

    assert "validate_docker_image" in [task.task_name for task in streamlit_tasks]
    assert "doi_provisioning" in [task.task_name for task in streamlit_tasks]
    assert "validate_docker_image" in [task.task_name for task in dash_tasks]
    assert "doi_provisioning" in [task.task_name for task in dash_tasks]


@pytest.mark.django_db
def test_doi_provisioning_is_not_registered_for_jupyter_lab():
    jupyter_tasks = TASK_REGISTRY.get_tasks_for_app("jupyter-lab")

    assert "validate_docker_image" in [task.task_name for task in jupyter_tasks]
    assert "doi_provisioning" not in [task.task_name for task in jupyter_tasks]


@pytest.mark.django_db
def test_validate_docker_image_is_not_registered_for_non_image_apps():
    tissuumaps_tasks = TASK_REGISTRY.get_tasks_for_app("tissuumaps")

    assert "validate_docker_image" not in [task.task_name for task in tissuumaps_tasks]


@pytest.mark.django_db
def test_doi_provisioning_task_includes_funding_metadata(app_instance):
    funding_payload = [
        {
            "funder_name": "Uppsala University",
            "funder_id": "048a87296",
            "number": "2024-01567",
            "title": "Uppsala Precision Medicine Grant",
            "url": "",
        }
    ]
    task_record = BackgroundTask.objects.create(
        app_instance=app_instance,
        task_name="doi_provisioning",
        task_type="external_api",
        status="pending",
        is_critical=False,
        execution_order=2,
        max_retries=0,
    )

    with patch("apps.background_tasks.tasks.doi_provisioning.resolve_app_image", return_value="some-image"), patch(
        "doi_minting.services.invenio_svc.save_metadata_to_invenio_then_mint_doi"
    ) as mock_mint:
        result = execute_single_background_task(
            task_db_id=task_record.id,
            task_kwargs_by_task_name={"doi_provisioning": {"language": "eng", "funding": funding_payload}},
        )

    assert result["success"] is True
    mock_mint.assert_called_once()
    assert mock_mint.call_args.kwargs["additional_metadata"]["languages"] == "eng"
    assert mock_mint.call_args.kwargs["additional_metadata"]["funding"] == funding_payload


@pytest.fixture()
def immediate_on_commit(monkeypatch):
    """Run transaction.on_commit callbacks immediately in unit tests."""

    def _on_commit(func, using=None):  # signature-compatible
        func()

    monkeypatch.setattr(transaction, "on_commit", _on_commit)


@pytest.fixture()
def clean_task_registry():
    """Isolate the global TASK_REGISTRY between tests."""
    original = TASK_REGISTRY.get_all_tasks()
    TASK_REGISTRY._tasks.clear()
    try:
        yield TASK_REGISTRY
    finally:
        TASK_REGISTRY._tasks.clear()
        TASK_REGISTRY._tasks.update(original)


@pytest.mark.django_db
def test_background_task_registry_filters_and_orders():
    registry = BackgroundTaskRegistry()

    @registry.register(name="t0", execution_order=0, app_types=["a"])
    class T0(BaseBackgroundTask):
        def execute(self, app_instance, **kwargs):
            return {"ok": True}

    @registry.register(name="t1", execution_order=1, app_types=["a"])
    class T1(BaseBackgroundTask):
        def execute(self, app_instance, **kwargs):
            return {"ok": True}

    @registry.register(name="t_other", execution_order=0, app_types=["b"])
    class TOther(BaseBackgroundTask):
        def execute(self, app_instance, **kwargs):
            return {"ok": True}

    assert registry.is_registered("t0") is True
    assert registry.get_task_class("t1") is T1

    tasks_for_a = registry.get_tasks_for_app("a")
    assert [t.task_name for t in tasks_for_a] == ["t0", "t1"]

    grouped = registry.get_tasks_by_order("a")
    assert list(grouped.keys()) == [0, 1]
    assert [t.task_name for t in grouped[0]] == ["t0"]


def test_base_background_task_retry_policy_defaults():
    class Dummy(BaseBackgroundTask):
        max_retries = 2

        def execute(self, app_instance, **kwargs):
            return {}

    t = Dummy()

    assert t.should_retry(RuntimeError("boom"), retry_count=0) is True
    assert t.should_retry(RuntimeError("boom"), retry_count=1) is True
    assert t.should_retry(RuntimeError("boom"), retry_count=2) is False

    assert t.should_retry(ValidationError("bad input"), retry_count=0) is False
    assert t.should_retry(PermissionDenied("nope"), retry_count=0) is False

    assert t.get_retry_delay(0) == 15
    assert t.get_retry_delay(1) == 75
    assert t.get_retry_delay(2) == 300
    assert t.get_retry_delay(3) == 300


@pytest.fixture()
def app_instance(db):
    user = User.objects.create_user("u1", "u1@test.com", "pw")
    project = Project.objects.create_project(name="p1", owner=user, description="")
    app = Apps.objects.create(name="Test App", slug="customapp")
    return BaseAppInstance.objects.create(owner=user, project=project, app=app, chart="test-chart")


@pytest.mark.django_db
def test_execute_single_background_task_success(clean_task_registry, app_instance):
    @TASK_REGISTRY.register(name="unit_success", is_critical=True, execution_order=0, app_types=["customapp"])
    class UnitSuccessTask(BaseBackgroundTask):
        def execute(self, app_instance, **kwargs):
            return {"success": True, "app_id": app_instance.id}

    record = BackgroundTask.objects.create(
        app_instance=app_instance,
        task_name="unit_success",
        task_type="validation",
        status="pending",
        is_critical=True,
        execution_order=0,
        max_retries=0,
    )

    # Call the task directly (no Celery config required).
    result = execute_single_background_task(record.id)
    assert result["success"] is True

    record.refresh_from_db()
    assert record.status == "success"
    assert record.result_data == {"success": True, "app_id": app_instance.id}
    assert record.started_at is not None
    assert record.completed_at is not None
    # celery_task_id is best-effort; in eager/unit runs it may be empty depending on task context.


@pytest.mark.django_db
def test_execute_single_background_task_validation_error_marks_failed_no_retry(clean_task_registry, app_instance):
    @TASK_REGISTRY.register(name="unit_validation_fail", is_critical=True, execution_order=0, app_types=["customapp"])
    class UnitValidationFailTask(BaseBackgroundTask):
        max_retries = 3

        def execute(self, app_instance, **kwargs):
            raise ValidationError("invalid")

    record = BackgroundTask.objects.create(
        app_instance=app_instance,
        task_name="unit_validation_fail",
        task_type="validation",
        status="pending",
        is_critical=True,
        execution_order=0,
        max_retries=3,
    )

    result = execute_single_background_task(record.id)
    assert result["success"] is False

    record.refresh_from_db()
    assert record.status == "failed"
    assert record.retry_count == 0
    assert "invalid" in record.error_message


@pytest.mark.django_db
def test_check_tasks_and_deploy_deploys_when_no_failed_critical(immediate_on_commit, app_instance):
    BackgroundTask.objects.create(
        app_instance=app_instance,
        task_name="t1",
        task_type="validation",
        status="success",
        is_critical=True,
        execution_order=0,
        max_retries=0,
    )

    with patch.object(deploy_resource, "delay") as mock_deploy:
        result = check_tasks_and_deploy(
            previous_results=None,
            app_instance_id=app_instance.id,
            serialized_instance=app_instance.serialize(),
        )

    assert result["success"] is True
    assert result["deployed"] is True
    mock_deploy.assert_called_once()


@pytest.mark.django_db
def test_check_tasks_and_deploy_blocks_when_failed_critical(immediate_on_commit, app_instance):
    BackgroundTask.objects.create(
        app_instance=app_instance,
        task_name="t1",
        task_type="validation",
        status="failed",
        is_critical=True,
        execution_order=0,
        max_retries=0,
        error_message="boom",
    )

    with patch.object(deploy_resource, "delay") as mock_deploy:
        result = check_tasks_and_deploy(
            previous_results=None,
            app_instance_id=app_instance.id,
            serialized_instance=app_instance.serialize(),
        )

    assert result["success"] is False
    assert result["deployed"] is False
    mock_deploy.assert_not_called()

    app_instance.refresh_from_db()
    assert app_instance.latest_user_action == "Failed"


@pytest.mark.django_db
def test_check_tasks_and_deploy_does_not_block_when_switch_enabled(immediate_on_commit, app_instance):
    BackgroundTask.objects.create(
        app_instance=app_instance,
        task_name="t1",
        task_type="validation",
        status="failed",
        is_critical=True,
        execution_order=0,
        max_retries=0,
        error_message="boom",
    )

    with patch(
        "apps.background_tasks.feature_flags.background_tasks_nonblocking_deploy",
        return_value=True,
    ), patch.object(deploy_resource, "delay") as mock_deploy:
        result = check_tasks_and_deploy(
            previous_results=None,
            app_instance_id=app_instance.id,
            serialized_instance=app_instance.serialize(),
        )

    assert result["deployed"] is True
    assert result.get("blocked") is False
    mock_deploy.assert_called_once()

    app_instance.refresh_from_db()
    assert app_instance.latest_user_action != "Failed"


@pytest.mark.django_db
def test_retry_background_task_resets_and_enqueues(app_instance):
    record = BackgroundTask.objects.create(
        app_instance=app_instance,
        task_name="t1",
        task_type="validation",
        status="failed",
        is_critical=True,
        execution_order=0,
        max_retries=3,
        retry_count=2,
        error_message="nope",
        result_data={"x": 1},
        celery_task_id="abc",
    )

    with patch.object(execute_single_background_task, "delay") as mock_exec:
        result = retry_background_task(task_id=record.id)

    assert result["success"] is True
    mock_exec.assert_called_once_with(record.id)

    record.refresh_from_db()
    assert record.status == "pending"
    assert record.error_message == ""
    assert record.retry_count == 0
    assert record.started_at is None
    assert record.completed_at is None
    assert record.result_data is None
    assert record.celery_task_id == ""


@pytest.mark.django_db
def test_retry_background_task_refuses_non_failed(app_instance):
    record = BackgroundTask.objects.create(
        app_instance=app_instance,
        task_name="t1",
        task_type="validation",
        status="retrying",
        is_critical=True,
        execution_order=0,
        max_retries=3,
    )

    with patch.object(execute_single_background_task, "delay") as mock_exec:
        result = retry_background_task(task_id=record.id)

    assert result["success"] is False
    mock_exec.assert_not_called()


@pytest.mark.django_db
def test_run_background_tasks_no_tasks_proceeds_to_deploy(immediate_on_commit, clean_task_registry, app_instance):
    # Ensure no tasks registered for the slug.
    TASK_REGISTRY._tasks.clear()

    with patch.object(deploy_resource, "delay") as mock_deploy:
        result = run_background_tasks(serialized_instance=app_instance.serialize(), app_slug="customapp")

    assert result["success"] is True
    assert "No tasks" in result["message"]
    mock_deploy.assert_called_once()


@pytest.mark.django_db
def test_run_background_tasks_creates_db_rows_and_schedules_workflow(
    immediate_on_commit, clean_task_registry, app_instance, monkeypatch
):
    @TASK_REGISTRY.register(name="unit_one", is_critical=True, execution_order=0, app_types=["customapp"])
    class UnitOne(BaseBackgroundTask):
        def execute(self, app_instance, **kwargs):
            return {"ok": 1}

    @TASK_REGISTRY.register(name="unit_two", is_critical=False, execution_order=1, app_types=["customapp"])
    class UnitTwo(BaseBackgroundTask):
        def execute(self, app_instance, **kwargs):
            return {"ok": 2}

    called = {"apply_async": 0, "steps": ()}

    class FakeWorkflow:
        def apply_async(self):
            called["apply_async"] += 1

    # run_background_tasks does `from celery import chain, group` inside the function.
    import celery  # type: ignore

    def _fake_chain(*steps):
        called["steps"] = steps
        return FakeWorkflow()

    monkeypatch.setattr(celery, "chain", _fake_chain)
    monkeypatch.setattr(celery, "group", lambda steps: types.SimpleNamespace(steps=steps))

    result = run_background_tasks(serialized_instance=app_instance.serialize(), app_slug="customapp")
    assert result["success"] is True

    rows = BackgroundTask.objects.filter(app_instance=app_instance).order_by("execution_order")
    assert rows.count() == 2
    assert [r.task_name for r in rows] == ["unit_one", "unit_two"]
    assert all(r.status == "pending" for r in rows)
    assert called["apply_async"] == 1

    # First two steps are execute_single_background_task signatures and must be immutable
    # so previous chain results are not injected as positional args.
    assert len(called["steps"]) == 3
    assert called["steps"][0].immutable is True
    assert called["steps"][1].immutable is True


@pytest.mark.django_db
def test_run_background_tasks_uses_known_tasks_for_streamlit(immediate_on_commit, monkeypatch):
    user = User.objects.create_user("u_streamlit", "u_streamlit@test.com", "pw")
    project = Project.objects.create_project(name="p_streamlit", owner=user, description="")
    app = Apps.objects.create(name="Streamlit App", slug="streamlit")
    app_instance = BaseAppInstance.objects.create(owner=user, project=project, app=app, chart="test-chart")

    called = {"apply_async": 0}

    class FakeWorkflow:
        def apply_async(self):
            called["apply_async"] += 1

    import celery  # type: ignore

    monkeypatch.setattr(celery, "chain", lambda *steps: FakeWorkflow())
    monkeypatch.setattr(celery, "group", lambda steps: types.SimpleNamespace(steps=steps))

    result = run_background_tasks(serialized_instance=app_instance.serialize(), app_slug="streamlit")

    assert result["success"] is True

    rows = BackgroundTask.objects.filter(app_instance=app_instance).order_by("execution_order", "task_name")
    assert [r.task_name for r in rows] == ["validate_docker_image", "doi_provisioning"]
    assert all(r.status == "pending" for r in rows)
    assert called["apply_async"] == 1


@pytest.mark.django_db
def test_run_background_tasks_uses_only_validation_for_jupyter_lab(immediate_on_commit, monkeypatch):
    user = User.objects.create_user("u_jupyter_run", "u_jupyter_run@test.com", "pw")
    project = Project.objects.create_project(name="p_jupyter_run", owner=user, description="")
    app = Apps.objects.create(name="JupyterLab", slug="jupyter-lab")
    app_instance = BaseAppInstance.objects.create(owner=user, project=project, app=app, chart="test-chart")

    called = {"apply_async": 0}

    class FakeWorkflow:
        def apply_async(self):
            called["apply_async"] += 1

    import celery  # type: ignore

    monkeypatch.setattr(celery, "chain", lambda *steps: FakeWorkflow())
    monkeypatch.setattr(celery, "group", lambda steps: types.SimpleNamespace(steps=steps))

    result = run_background_tasks(serialized_instance=app_instance.serialize(), app_slug="jupyter-lab")

    assert result["success"] is True

    rows = BackgroundTask.objects.filter(app_instance=app_instance).order_by("execution_order", "task_name")
    assert [r.task_name for r in rows] == ["validate_docker_image"]
    assert all(r.status == "pending" for r in rows)
    assert called["apply_async"] == 1
