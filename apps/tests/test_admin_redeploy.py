from unittest.mock import patch

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from apps.admin import BaseAppAdmin
from apps.models import Apps, DashInstance, K8sUserAppStatus, Subdomain
from apps.tasks import deploy_resource, restart_helm_workloads
from projects.models import Flavor, Project

User = get_user_model()


class RedeployAppsAdminActionTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("admin-redeploy", "admin-redeploy@example.com", "password")
        self.project = Project.objects.create_project(name="admin-redeploy", owner=self.user, description="")
        self.app = Apps.objects.create(name="Dash", slug="dashapp", chart="dash-chart:1.0.0")
        self.subdomain = Subdomain.objects.create(subdomain="admin-redeploy", project=self.project)
        self.status = K8sUserAppStatus.objects.create(status="Running")
        self.instance = DashInstance.objects.create(
            access="public",
            app=self.app,
            chart=self.app.chart,
            image="example.org/dash:latest",
            info={"helm": {"success": True}},
            k8s_user_app_status=self.status,
            latest_user_action="Creating",
            name="Admin redeploy",
            owner=self.user,
            port=8050,
            project=self.project,
            subdomain=self.subdomain,
        )
        self.model_admin = BaseAppAdmin(DashInstance, admin.site)
        self.request = RequestFactory().post("/admin/apps/dashinstance/")

    @patch("apps.admin.deploy_resource.delay")
    def test_redeploy_forces_rollout_and_resets_deployment_status(self, mock_deploy):
        with patch.object(self.model_admin, "message_user"):
            self.model_admin.deploy_resources(self.request, DashInstance.objects.filter(pk=self.instance.pk))

        self.instance.refresh_from_db()
        self.status.refresh_from_db()

        self.assertEqual(self.instance.latest_user_action, "Changing")
        self.assertIsNone(self.status.status)
        self.assertNotIn("helm", self.instance.info)
        mock_deploy.assert_called_once()
        self.assertTrue(mock_deploy.call_args.kwargs["force_redeploy"])

    @patch("apps.admin.deploy_resource.delay")
    def test_redeploy_link_only_app(self, mock_deploy):
        self.instance.access = "link"
        self.instance.note_on_linkonly_privacy = "Shared with reviewers"
        self.instance.save(update_fields=["access", "note_on_linkonly_privacy"])

        with patch.object(self.model_admin, "message_user"):
            self.model_admin.deploy_resources(self.request, DashInstance.objects.filter(pk=self.instance.pk))

        self.instance.refresh_from_db()
        self.assertEqual(self.instance.access, "link")
        self.assertEqual(self.instance.k8s_values["permission"], "link")
        self.assertEqual(self.instance.latest_user_action, "Changing")
        mock_deploy.assert_called_once()
        self.assertTrue(mock_deploy.call_args.kwargs["force_redeploy"])

    @override_settings(DEBUG=False)
    @patch("apps.tasks.restart_helm_workloads", return_value=("restarted", None))
    @patch("apps.tasks.helm_install", return_value=("upgraded", None))
    def test_force_redeploy_restarts_workloads_after_helm_upgrade(self, _mock_helm, mock_restart):
        self.instance.set_k8s_values()
        self.instance.save(update_fields=["k8s_values"])

        deploy_resource.run(self.instance.serialize(), force_redeploy=True)

        mock_restart.assert_called_once_with(self.subdomain.subdomain, self.instance.k8s_values["namespace"])
        self.instance.refresh_from_db()
        self.assertTrue(self.instance.info["helm"]["success"])
        self.assertEqual(self.instance.info["helm"]["restart"]["stdout"], "restarted")

    @override_settings(DEBUG=False)
    @patch("apps.tasks.restart_helm_workloads")
    @patch("apps.tasks.helm_install", return_value=("upgraded", None))
    def test_regular_deploy_does_not_force_workload_restart(self, _mock_helm, mock_restart):
        self.instance.set_k8s_values()
        self.instance.save(update_fields=["k8s_values"])

        deploy_resource.run(self.instance.serialize())

        mock_restart.assert_not_called()
        self.instance.refresh_from_db()
        self.assertNotIn("restart", self.instance.info["helm"])


class CreateLinkOnlyAppInAdminTestCase(TestCase):
    def setUp(self):
        self.superuser = User.objects.create_superuser("link-admin", "link-admin@example.com", "password")
        self.project = Project.objects.create_project(name="link-admin", owner=self.superuser, description="")
        self.app = Apps.objects.create(name="Dash", slug="dashapp", chart="dash-chart:1.0.0")
        self.subdomain = Subdomain.objects.create(subdomain="link-admin-app", project=self.project)
        self.client.force_login(self.superuser)

    def test_admin_can_create_link_only_app(self):
        response = self.client.post(
            reverse("admin:apps_dashinstance_add"),
            {
                "access": "link",
                "app": self.app.pk,
                "chart": self.app.chart,
                "description": "Link-only app created by an administrator",
                "image": "example.org/dash:latest",
                "latest_user_action": "Creating",
                "name": "Admin-created link app",
                "note_on_linkonly_privacy": "Shared with reviewers",
                "owner": self.superuser.pk,
                "port": 8050,
                "project": self.project.pk,
                "subdomain": self.subdomain.pk,
                "subjects_keywords": "[]",
                "tags": "",
                "upload_size": 100,
                "_save": "Save",
            },
        )

        self.assertEqual(response.status_code, 302, response.context and response.context["adminform"].form.errors)
        instance = DashInstance.objects.get(name="Admin-created link app")
        self.assertEqual(instance.access, "link")
        self.assertEqual(instance.note_on_linkonly_privacy, "Shared with reviewers")


class CreateLinkOnlyAppInProductUITestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("link-user", "link-user@example.com", "password")
        self.project = Project.objects.create_project(name="link-ui", owner=self.user, description="")
        self.flavor = Flavor.objects.create(name="Small", project=self.project)
        self.app = Apps.objects.create(name="Dash", slug="dashapp", chart="dash-chart:1.0.0")
        self.client.force_login(self.user)

    @patch("apps.tasks.run_background_tasks.delay")
    def test_user_can_create_link_only_app(self, mock_background_tasks):
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                reverse("apps:create", kwargs={"project": self.project.slug, "app_slug": self.app.slug}),
                {
                    "access": "link",
                    "description": "Link-only app created through the product UI",
                    "flavor": self.flavor.pk,
                    "image": "example.org/dash:latest",
                    "invenio_tags": "",
                    "name": "UI-created link app",
                    "note_on_linkonly_privacy": "Shared with reviewers",
                    "port": 8050,
                    "source_code_url": "",
                    "subdomain": "link-ui-app",
                },
            )

        self.assertEqual(response.status_code, 302)
        instance = DashInstance.objects.get(name="UI-created link app")
        self.assertEqual(instance.access, "link")
        self.assertEqual(instance.note_on_linkonly_privacy, "Shared with reviewers")
        self.assertIsNotNone(instance.reminder_date_linkonly_privacy)
        mock_background_tasks.assert_called_once()


class RestartHelmWorkloadsTestCase(SimpleTestCase):
    @patch("apps.tasks.subprocess.run")
    @patch("apps.tasks.get_manifest_yaml")
    def test_restarts_every_rollout_capable_workload(self, mock_manifest, mock_run):
        mock_manifest.return_value = (
            """
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: web
---
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: worker
---
apiVersion: v1
kind: Service
metadata:
  name: web
""",
            None,
        )
        mock_run.return_value.stdout = "restarted"

        output, error = restart_helm_workloads("release", "namespace")

        self.assertEqual(output, "restarted")
        self.assertIsNone(error)
        mock_run.assert_called_once_with(
            [
                "kubectl",
                "rollout",
                "restart",
                "deployment/web",
                "statefulset/worker",
                "--namespace",
                "namespace",
            ],
            check=True,
            text=True,
            capture_output=True,
        )

    @patch("apps.tasks.subprocess.run")
    @patch("apps.tasks.get_manifest_yaml", return_value=("kind: PersistentVolumeClaim", None))
    def test_release_without_workloads_does_not_call_kubectl(self, _mock_manifest, mock_run):
        output, error = restart_helm_workloads("release", "namespace")

        self.assertEqual(output, "No restartable workloads found for Helm release release.")
        self.assertIsNone(error)
        mock_run.assert_not_called()
