import json
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.constants import HandleUpdateStatusResponseCode
from apps.helpers import handle_update_status_request
from apps.models import (
    AppCategories,
    Apps,
    BaseAppInstance,
    JupyterInstance,
    K8sUserAppStatus,
    Subdomain,
)
from apps.tasks import (
    _workload_readiness,
    get_release_readiness,
    reconcile_app_statuses,
)
from projects.models import Project

User = get_user_model()

test_user = {"username": "foo@test.com", "email": "foo@test.com", "password": "bar"}


def _deployment(name, ready, desired):
    return {
        "metadata": {"name": name},
        "spec": {"replicas": desired},
        "status": {"readyReplicas": ready},
    }


class WorkloadReadinessTestCase(TestCase):
    """No Serve chart has a DaemonSet, so that branch is unreachable through
    get_release_readiness. The other kinds are covered there."""

    def test_daemonset_uses_scheduled_counts(self):
        item = {"metadata": {"name": "agent"}, "spec": {}, "status": {"desiredNumberScheduled": 3, "numberReady": 3}}
        ref, ready, desired = _workload_readiness(item, "DaemonSet")
        assert ref == "daemonset/agent"
        assert (ready, desired) == (3, 3)


class GetReleaseReadinessTestCase(TestCase):
    """Aggregating readiness across every workload of a release."""

    def _run_with(self, resources):
        payload = json.dumps({"name": "r123", "info": {"status": "deployed", "resources": resources}})
        with patch("apps.tasks.subprocess.run") as mock_run:
            mock_run.return_value.stdout = payload
            return get_release_readiness("r123")

    def test_all_workloads_ready(self):
        readiness, error = self._run_with(
            {
                "v1/Deployment": [_deployment("frontend", 1, 1), _deployment("backend", 1, 1)],
                "v1/StatefulSet": [_deployment("minio", 1, 1)],
            }
        )

        assert error is None
        assert readiness["all_ready"] is True

    def test_one_ready_pod_is_not_enough(self):
        """The reported depictio bug: minio up, frontend and backend still starting."""
        readiness, error = self._run_with(
            {
                "v1/Deployment": [_deployment("frontend", 0, 1), _deployment("backend", 0, 1)],
                "v1/StatefulSet": [_deployment("minio", 1, 1)],
            }
        )

        assert error is None
        assert readiness["all_ready"] is False
        assert readiness["workloads"]["deployment/frontend"] == {"ready": 0, "desired": 1}
        assert readiness["workloads"]["statefulset/minio"] == {"ready": 1, "desired": 1}

    def test_real_depictio_release_shape(self):
        """Mirrors an actual `helm status --show-resources` payload for a depictio release."""
        readiness, error = self._run_with(
            {
                "v1/ConfigMap": [{"metadata": {"name": "r1-backend-config"}}],
                "v1/Secret": [{"metadata": {"name": "r1-depictio-secrets"}}],
                "v1/PersistentVolumeClaim": [{"metadata": {"name": "r1-minio-pvc"}}],
                "v1/Service": [{"metadata": {"name": "r1-minio"}}],
                "v1/Ingress": [{"metadata": {"name": "r1-ingress"}}],
                "v1/Deployment": [
                    _deployment("r1-minio", 1, 1),
                    _deployment("r1-depictio-backend", 1, 1),
                    _deployment("r1-depictio-viewer", 1, 1),
                    _deployment("r1-celery-worker", 1, 1),
                ],
                "v1/StatefulSet": [_deployment("r1-mongo", 1, 1), _deployment("r1-redis", 1, 1)],
                "v1/Pod(related)": [{"items": [{"metadata": {"name": "r1-minio-x"}}]}],
            }
        )

        assert error is None
        assert readiness["all_ready"] is True
        # Six pod-owning workloads; the ConfigMaps, Secrets, PVCs, Services,
        # Ingresses and related pods are not readiness signals.
        assert len(readiness["workloads"]) == 6
        assert "statefulset/r1-mongo" in readiness["workloads"]

    def test_release_with_no_workloads_is_not_ready_but_not_an_error(self):
        """A pod-less chart reads fine; it just never becomes ready."""
        readiness, error = self._run_with({"v1/Service": [{"metadata": {"name": "svc"}}]})

        assert error is None
        assert readiness["all_ready"] is False
        assert readiness["workloads"] == {}

    def test_helm_failure_is_reported(self):
        from subprocess import CalledProcessError

        exc = CalledProcessError(1, "helm", stderr="Error: release: not found")
        with patch("apps.tasks.subprocess.run", side_effect=exc):
            readiness, error = get_release_readiness("r123")

        assert readiness is None
        assert "not found" in error


class StatusIngestionGuardTestCase(TestCase):
    """A single pod's Running event must not set the whole app to Running."""

    RELEASE = "test-release-name"

    def setUp(self):
        self.user = User.objects.create_user(test_user["username"], test_user["email"], test_user["password"])
        self.category = AppCategories.objects.create(name="Network", priority=100, slug="network")
        self.app = Apps.objects.create(
            name="Jupyter Lab", slug="jupyter-lab", user_can_edit=False, category=self.category
        )
        self.project = Project.objects.create_project(name="test-aggregation", owner=self.user, description="")
        subdomain = Subdomain.objects.create(subdomain=self.RELEASE)
        self.status = K8sUserAppStatus.objects.create(status="ContainerCreating")
        self.instance = JupyterInstance.objects.create(
            access="private",
            owner=self.user,
            name="test_app_instance",
            app=self.app,
            project=self.project,
            subdomain=subdomain,
            k8s_user_app_status=self.status,
            k8s_values={"release": self.RELEASE, "namespace": "default"},
        )

    def _newer_ts(self):
        return self.status.time + timedelta(seconds=60)

    def test_running_event_is_deferred(self):
        actual = handle_update_status_request(self.RELEASE, "Running", self._newer_ts())

        assert actual == HandleUpdateStatusResponseCode.DEFERRED_TO_AGGREGATION
        self.status.refresh_from_db()
        assert self.status.status == "ContainerCreating"

    def test_non_running_events_still_apply(self):
        actual = handle_update_status_request(self.RELEASE, "CrashLoopBackOff", self._newer_ts())

        assert actual == HandleUpdateStatusResponseCode.UPDATED_STATUS
        self.status.refresh_from_db()
        assert self.status.status == "CrashLoopBackOff"

    @override_settings(POD_STATUS_AGGREGATION_ENABLED=False)
    def test_guard_can_be_disabled(self):
        actual = handle_update_status_request(self.RELEASE, "Running", self._newer_ts())

        assert actual == HandleUpdateStatusResponseCode.UPDATED_STATUS
        self.status.refresh_from_db()
        assert self.status.status == "Running"


class ReconcileAppStatusesTestCase(TestCase):
    """The reconciler is the only writer of Running."""

    RELEASE = "reconcile-release"

    def setUp(self):
        self.user = User.objects.create_user(test_user["username"], test_user["email"], test_user["password"])
        self.category = AppCategories.objects.create(name="Network", priority=100, slug="network")
        self.app = Apps.objects.create(
            name="Jupyter Lab", slug="jupyter-lab", user_can_edit=False, category=self.category
        )
        self.project = Project.objects.create_project(name="test-reconcile", owner=self.user, description="")
        subdomain = Subdomain.objects.create(subdomain=self.RELEASE)
        self.status = K8sUserAppStatus.objects.create(status="ContainerCreating")
        self.instance = JupyterInstance.objects.create(
            access="private",
            owner=self.user,
            name="test_reconcile_instance",
            app=self.app,
            project=self.project,
            subdomain=subdomain,
            k8s_user_app_status=self.status,
            latest_user_action="Creating",
            k8s_values={"release": self.RELEASE, "namespace": "default"},
        )

    def test_marks_running_when_all_workloads_ready(self):
        readiness = {"all_ready": True, "workloads": {"deployment/a": {"ready": 1, "desired": 1}}}
        with patch("apps.tasks.get_release_readiness", return_value=(readiness, None)):
            reconcile_app_statuses()

        self.status.refresh_from_db()
        assert self.status.status == "Running"
        assert self.status.info == {"workloads": {"deployment/a": {"ready": 1, "desired": 1}}}

    def test_does_not_mark_running_when_a_workload_is_not_ready(self):
        readiness = {
            "all_ready": False,
            "workloads": {
                "deployment/frontend": {"ready": 0, "desired": 1},
                "statefulset/minio": {"ready": 1, "desired": 1},
            },
        }
        with patch("apps.tasks.get_release_readiness", return_value=(readiness, None)):
            reconcile_app_statuses()

        self.status.refresh_from_db()
        assert self.status.status == "ContainerCreating"

    def test_only_genuine_read_failures_warn(self):
        """A release still installing is expected; a broken helm strands apps, so it is loud."""
        for error, should_warn in (
            ("Error: release: not found", False),
            ("forbidden: User cannot list resource", True),
        ):
            with (
                patch("apps.tasks.get_release_readiness", return_value=(None, error)),
                patch("apps.tasks.logger") as mock_logger,
            ):
                reconcile_app_statuses()

            self.status.refresh_from_db()
            assert self.status.status == "ContainerCreating"
            assert mock_logger.warning.called is should_warn, error

    def test_pod_less_app_types_are_skipped(self):
        """volumeK8s and netpolicy charts own no pods, so there is nothing to check."""
        self.app.slug = "volumeK8s"
        self.app.save(update_fields=["slug"])

        with patch("apps.tasks.get_release_readiness") as mock_readiness:
            reconcile_app_statuses()

        mock_readiness.assert_not_called()

    def test_stale_apps_are_skipped(self):
        """A deploy that has not settled within the window is never going to."""
        BaseAppInstance.objects.filter(pk=self.instance.pk).update(updated_on=timezone.now() - timedelta(hours=2))

        with patch("apps.tasks.get_release_readiness") as mock_readiness:
            reconcile_app_statuses()

        mock_readiness.assert_not_called()

    def test_db_connection_is_released_before_each_helm_call(self):
        """helm status is slow and the pool is small, so do not hold a connection."""
        call_order = []

        def fake_readiness(*args, **kwargs):
            call_order.append("helm")
            return {"all_ready": False, "workloads": {}}, None

        with (
            patch("apps.tasks.connection") as mock_connection,
            patch("apps.tasks.get_release_readiness", side_effect=fake_readiness),
        ):
            mock_connection.in_atomic_block = False
            mock_connection.close.side_effect = lambda: call_order.append("close")
            reconcile_app_statuses()

        assert call_order == ["close", "helm"]

    @override_settings(POD_STATUS_AGGREGATION_ENABLED=False)
    def test_disabled_flag_skips_the_sweep(self):
        with patch("apps.tasks.get_release_readiness") as mock_readiness:
            reconcile_app_statuses()

        mock_readiness.assert_not_called()
