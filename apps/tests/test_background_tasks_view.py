from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from projects.models import Project, ProjectTemplate

from ..models import AppCategories, Apps, BackgroundTask, CustomAppInstance, K8sUserAppStatus, Subdomain

User = get_user_model()


class BackgroundTasksViewTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("foo1", "foo@test.com", "bar")
        self.client.force_login(self.user)

        self.category = AppCategories.objects.create(name="Serve", priority=100, slug="serve")
        self.app = Apps.objects.create(
            name="My Custom App",
            slug="customapp",
            user_can_edit=True,
            category=self.category,
        )
        self.project_template = ProjectTemplate.objects.create(name="Default template", slug="default-template")
        self.project_template.available_apps.add(self.app)
        self.project = Project.objects.create_project(
            name="test-background-tasks",
            owner=self.user,
            description="",
            project_template=self.project_template,
        )

        subdomain = Subdomain.objects.create(subdomain="test-background-tasks")
        k8s_user_app_status = K8sUserAppStatus.objects.create()

        self.app_instance = CustomAppInstance.objects.create(
            access="private",
            owner=self.user,
            name="test deployment app",
            app=self.app,
            project=self.project,
            subdomain=subdomain,
            k8s_user_app_status=k8s_user_app_status,
            k8s_values={"environment": {"pk": ""}},
        )

        BackgroundTask.objects.create(
            app_instance=self.app_instance,
            task_name="validate_docker_image",
            task_type="validation",
            status="running",
            is_critical=True,
            execution_order=1,
        )

    def test_deployment_progress_page_uses_user_facing_copy(self):
        response = self.client.get(
            reverse(
                "apps:deployment_progress",
                kwargs={
                    "project": self.project.slug,
                    "app_slug": self.app.slug,
                    "app_id": self.app_instance.pk,
                },
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Preparing test deployment app")
        self.assertContains(response, "We are preparing your app")
        self.assertContains(response, "Back to form")
        self.assertContains(response, "Deployment summary")

    def test_background_tasks_page_shows_detailed_checks_copy(self):
        response = self.client.get(
            reverse(
                "apps:background_tasks",
                kwargs={
                    "project": self.project.slug,
                    "app_slug": self.app.slug,
                    "app_id": self.app_instance.pk,
                },
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Deployment Checks")
        self.assertContains(response, "test deployment app - Deployment Checks")
        self.assertContains(response, "About Deployment Checks:")
        self.assertContains(response, "Check Details")
        self.assertContains(response, "Check Image Compatibility")

    def test_private_app_details_page_shows_deployment_summary(self):
        response = self.client.get(
            reverse(
                "apps:details",
                kwargs={
                    "project": self.project.slug,
                    "app_slug": self.app.slug,
                    "app_id": self.app_instance.pk,
                },
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Deployment Summary")
        self.assertContains(response, "Recent Checks")
        self.assertContains(response, "Back to project")
        self.assertNotContains(response, ">Logs<", html=False)
        self.assertContains(
            response,
            "validate_docker_image",
        )

    def test_private_app_details_page_marks_skipped_checks_distinctly(self):
        BackgroundTask.objects.create(
            app_instance=self.app_instance,
            task_name="doi_provisioning",
            task_type="external_api",
            status="success",
            is_critical=False,
            execution_order=2,
            result_data={"skipped": True, "reason": "DOI minting is only available for public apps."},
        )

        response = self.client.get(
            reverse(
                "apps:details",
                kwargs={
                    "project": self.project.slug,
                    "app_slug": self.app.slug,
                    "app_id": self.app_instance.pk,
                },
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Skipped")

    def test_background_task_status_api_collapses_historical_duplicate_task_names(self):
        BackgroundTask.objects.create(
            app_instance=self.app_instance,
            task_name="validate_docker_image",
            task_type="validation",
            status="success",
            is_critical=True,
            execution_order=1,
        )
        BackgroundTask.objects.create(
            app_instance=self.app_instance,
            task_name="doi_provisioning",
            task_type="external_api",
            status="success",
            is_critical=False,
            execution_order=2,
        )

        response = self.client.get(
            reverse(
                "apps:background_tasks_status",
                kwargs={
                    "project": self.project.slug,
                    "app_slug": self.app.slug,
                    "app_id": self.app_instance.pk,
                },
            )
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload["tasks"]), 2)
        self.assertEqual([task["task_name"] for task in payload["tasks"]], ["validate_docker_image", "doi_provisioning"])
        self.assertEqual(payload["summary"]["total"], 2)

    def test_background_task_status_api_keeps_deploy_pending_while_checks_are_running(self):
        self.app_instance.k8s_user_app_status.status = "Running"
        self.app_instance.k8s_user_app_status.save(update_fields=["status"])
        self.app_instance.latest_user_action = "Changing"
        self.app_instance.save(update_fields=["latest_user_action"])

        response = self.client.get(
            reverse(
                "apps:background_tasks_status",
                kwargs={
                    "project": self.project.slug,
                    "app_slug": self.app.slug,
                    "app_id": self.app_instance.pk,
                },
            )
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["deployment"]["status"], "pending")
        self.assertEqual(payload["deployment"]["label"], "Pending")

    def test_background_task_status_api_keeps_deploy_running_until_helm_records_success(self):
        BackgroundTask.objects.filter(app_instance=self.app_instance).update(status="success")
        self.app_instance.k8s_user_app_status.status = "Running"
        self.app_instance.k8s_user_app_status.save(update_fields=["status"])
        self.app_instance.latest_user_action = "Changing"
        self.app_instance.info = {}
        self.app_instance.save(update_fields=["latest_user_action", "info"])

        response = self.client.get(
            reverse(
                "apps:background_tasks_status",
                kwargs={
                    "project": self.project.slug,
                    "app_slug": self.app.slug,
                    "app_id": self.app_instance.pk,
                },
            )
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["deployment"]["status"], "running")
        self.assertEqual(payload["deployment"]["label"], "Deploying")

    def test_background_task_status_api_keeps_deploy_running_during_transient_notfound_state(self):
        BackgroundTask.objects.filter(app_instance=self.app_instance).update(status="success")
        self.app_instance.k8s_user_app_status.status = "NotFound"
        self.app_instance.k8s_user_app_status.save(update_fields=["status"])
        self.app_instance.latest_user_action = "Changing"
        self.app_instance.save(update_fields=["latest_user_action"])

        response = self.client.get(
            reverse(
                "apps:background_tasks_status",
                kwargs={
                    "project": self.project.slug,
                    "app_slug": self.app.slug,
                    "app_id": self.app_instance.pk,
                },
            )
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["deployment"]["status"], "running")
        self.assertEqual(payload["deployment"]["label"], "Deploying")

    def test_background_task_status_api_surfaces_helm_failure_after_checks_complete(self):
        BackgroundTask.objects.filter(app_instance=self.app_instance).update(status="success")
        self.app_instance.k8s_user_app_status.status = "Running"
        self.app_instance.k8s_user_app_status.save(update_fields=["status"])
        self.app_instance.latest_user_action = "Changing"
        self.app_instance.info = {"helm": {"success": False, "info": {"stderr": "chart upgrade failed"}}}
        self.app_instance.save(update_fields=["latest_user_action", "info"])

        response = self.client.get(
            reverse(
                "apps:background_tasks_status",
                kwargs={
                    "project": self.project.slug,
                    "app_slug": self.app.slug,
                    "app_id": self.app_instance.pk,
                },
            )
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["deployment"]["status"], "failed")
        self.assertEqual(payload["deployment"]["label"], "Failed")

    def test_background_task_status_api_marks_skipped_tasks(self):
        BackgroundTask.objects.create(
            app_instance=self.app_instance,
            task_name="doi_provisioning",
            task_type="external_api",
            status="success",
            is_critical=False,
            execution_order=2,
            result_data={"skipped": True, "reason": "doi_minting_using_invenio switch is off"},
        )

        response = self.client.get(
            reverse(
                "apps:background_tasks_status",
                kwargs={
                    "project": self.project.slug,
                    "app_slug": self.app.slug,
                    "app_id": self.app_instance.pk,
                },
            )
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        doi_task = next(task for task in payload["tasks"] if task["task_name"] == "doi_provisioning")
        self.assertTrue(doi_task["was_skipped"])
        self.assertEqual(doi_task["skip_reason"], "doi_minting_using_invenio switch is off")
        self.assertEqual(payload["summary"]["success"], 0)
        self.assertEqual(payload["summary"]["skipped"], 1)
        doi_graph_node = next(node for node in payload["graph"]["nodes"] if node["id"] == f"task-{doi_task['id']}")
        self.assertEqual(doi_graph_node["status"], "skipped")
        self.assertEqual(doi_graph_node["label"], "Mint DOI")

    def test_new_project_scoped_pages_reject_app_ids_from_other_projects(self):
        other_user = User.objects.create_user("foo2", "foo2@test.com", "bar")
        other_project = Project.objects.create_project(
            name="other-project",
            owner=other_user,
            description="",
            project_template=self.project_template,
        )
        other_subdomain = Subdomain.objects.create(subdomain="other-project-app")
        other_k8s_status = K8sUserAppStatus.objects.create()
        other_instance = CustomAppInstance.objects.create(
            access="private",
            owner=other_user,
            name="other app",
            app=self.app,
            project=other_project,
            subdomain=other_subdomain,
            k8s_user_app_status=other_k8s_status,
            k8s_values={"environment": {"pk": ""}},
        )

        for route_name in ("apps:deployment_progress", "apps:details"):
            response = self.client.get(
                reverse(
                    route_name,
                    kwargs={
                        "project": self.project.slug,
                        "app_slug": self.app.slug,
                        "app_id": other_instance.pk,
                    },
                )
            )
            self.assertEqual(response.status_code, 404)

        response = self.client.get(
            reverse(
                "apps:background_tasks_status",
                kwargs={
                    "project": self.project.slug,
                    "app_slug": self.app.slug,
                    "app_id": other_instance.pk,
                },
            )
        )
        self.assertEqual(response.status_code, 404)
