import base64
import json
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from projects.models import Project

from ..models import (
    Apps,
    CustomAppInstance,
    DepictioInstance,
    K8sUserAppStatus,
    Subdomain,
)

User = get_user_model()


@override_settings(DOMAIN="serve.example.test", INVENIO_MOCK_MODE=True)
class AppDetailsViewTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("owner", "owner@test.com", "password")
        self.project = Project.objects.create_project(name="depictio-project", owner=self.user, description="")
        self.client.login(username="owner@test.com", password="password")

    @staticmethod
    def _progress_state():
        return {
            "tasks": [],
            "summary": {"total": 0, "success": 0, "skipped": 0, "failed": 0},
            "deployment": {
                "status": "success",
                "label": "Ready",
                "message": "Deployment complete",
                "app_status": "Running",
            },
        }

    def test_depictio_details_show_minio_credentials_and_urls(self):
        app = Apps.objects.create(name="Depictio", slug="depictio", chart="depictio-chart")
        subdomain = Subdomain.objects.create(subdomain="depictio-release")
        k8s_status = K8sUserAppStatus.objects.create(status="Running")
        instance = DepictioInstance.objects.create(
            access="project",
            owner=self.user,
            name="Depictio app",
            app=app,
            chart=app.chart,
            project=self.project,
            subdomain=subdomain,
            k8s_user_app_status=k8s_status,
            url="https://depictio-release.serve.example.test",
        )

        secret_payload = {
            "data": {
                "MINIO_ROOT_USER": base64.b64encode(b"minio-user").decode(),
                "MINIO_ROOT_PASSWORD": base64.b64encode(b"minio-password").decode(),
            }
        }

        with (
            patch("apps.views.build_progress_state", return_value=self._progress_state()),
            patch("apps.views.subprocess.run", return_value=Mock(stdout=json.dumps(secret_payload))) as mock_run,
        ):
            response = self.client.get(
                reverse(
                    "apps:details",
                    kwargs={"project": self.project.slug, "app_slug": app.slug, "app_id": instance.pk},
                )
            )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Depictio details")
        self.assertContains(response, "API details")
        self.assertContains(response, "MinIO details")
        self.assertContains(response, "minio-user")
        self.assertContains(response, "minio-password")
        self.assertContains(response, "depictio-release-api.serve.example.test")
        self.assertContains(response, "depictio-release-minio.serve.example.test")
        mock_run.assert_called_once_with(
            [
                "kubectl",
                "get",
                "secret",
                "--namespace",
                "default",
                "depictio-release-depictio-secrets",
                "-o",
                "json",
            ],
            check=True,
            text=True,
            capture_output=True,
        )

    def test_non_depictio_details_do_not_fetch_cluster_secrets(self):
        app = Apps.objects.create(name="Custom App", slug="customapp", chart="custom-chart")
        subdomain = Subdomain.objects.create(subdomain="custom-release")
        k8s_status = K8sUserAppStatus.objects.create(status="Running")
        instance = CustomAppInstance.objects.create(
            owner=self.user,
            name="Custom app",
            app=app,
            chart=app.chart,
            project=self.project,
            subdomain=subdomain,
            k8s_user_app_status=k8s_status,
            url="https://custom-release.serve.example.test",
        )

        with (
            patch("apps.views.build_progress_state", return_value=self._progress_state()),
            patch("apps.views.subprocess.run") as mock_run,
        ):
            response = self.client.get(
                reverse(
                    "apps:details",
                    kwargs={"project": self.project.slug, "app_slug": app.slug, "app_id": instance.pk},
                )
            )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Depictio details")
        mock_run.assert_not_called()
