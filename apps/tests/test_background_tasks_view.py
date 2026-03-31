import uuid

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.background_tasks.registry import TASK_REGISTRY
from projects.models import Project, ProjectTemplate

from ..models import (
    AppCategories,
    Apps,
    BackgroundTask,
    CustomAppInstance,
    K8sUserAppStatus,
    Subdomain,
)

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
        self.assertEqual(
            response.context["status_api_url"],
            reverse(
                "apps:background_tasks_status",
                kwargs={
                    "project": self.project.slug,
                    "app_slug": self.app.slug,
                    "app_id": self.app_instance.pk,
                },
            )
            + "?mode=details",
        )

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
            "Check Image Compatibility",
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
        self.assertEqual(
            [task["task_name"] for task in payload["tasks"]], ["validate_docker_image", "doi_provisioning"]
        )
        self.assertEqual(payload["summary"]["total"], 2)

    def test_background_task_status_api_filters_to_requested_run_id(self):
        requested_run_id = uuid.uuid4()
        other_run_id = uuid.uuid4()
        BackgroundTask.objects.filter(app_instance=self.app_instance).update(run_id=other_run_id)
        BackgroundTask.objects.create(
            app_instance=self.app_instance,
            task_name="validate_docker_image",
            task_type="validation",
            status="success",
            is_critical=True,
            execution_order=1,
            run_id=requested_run_id,
        )
        BackgroundTask.objects.create(
            app_instance=self.app_instance,
            task_name="doi_provisioning",
            task_type="external_api",
            status="success",
            is_critical=False,
            execution_order=2,
            run_id=requested_run_id,
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
            + f"?run_id={requested_run_id}",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(
            [task["task_name"] for task in payload["tasks"]],
            ["validate_docker_image", "doi_provisioning"],
        )
        self.assertTrue(all(task["run_id"] == str(requested_run_id) for task in payload["tasks"]))

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

    def test_background_task_status_api_ignores_stale_failed_checks_before_new_run_records_exist(self):
        BackgroundTask.objects.filter(app_instance=self.app_instance).update(status="failed")
        self.app_instance.k8s_user_app_status.status = "Running"
        self.app_instance.k8s_user_app_status.save(update_fields=["status"])
        self.app_instance.latest_user_action = "Changing"
        self.app_instance.save()

        response = self.client.get(
            reverse(
                "apps:background_tasks_status",
                kwargs={
                    "project": self.project.slug,
                    "app_slug": self.app.slug,
                    "app_id": self.app_instance.pk,
                },
            ),
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["tasks"], [])
        self.assertEqual(payload["deployment"]["status"], "pending")
        self.assertEqual(payload["deployment"]["label"], "Pending")
        self.assertEqual(payload["deployment"]["message"], "Waiting for deployment checks to start.")

    def test_background_task_status_api_keeps_waiting_when_helm_succeeds_before_current_tasks_appear(self):
        BackgroundTask.objects.filter(app_instance=self.app_instance).update(status="failed")
        self.app_instance.k8s_user_app_status.status = "Running"
        self.app_instance.k8s_user_app_status.save(update_fields=["status"])
        self.app_instance.latest_user_action = "Changing"
        self.app_instance.info = {"helm": {"success": True, "info": {"stdout": "ok", "stderr": ""}}}
        self.app_instance.save()

        response = self.client.get(
            reverse(
                "apps:background_tasks_status",
                kwargs={
                    "project": self.project.slug,
                    "app_slug": self.app.slug,
                    "app_id": self.app_instance.pk,
                },
            ),
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["tasks"], [])
        self.assertEqual(payload["deployment"]["status"], "pending")
        self.assertEqual(payload["deployment"]["label"], "Pending")
        self.assertEqual(payload["deployment"]["message"], "Waiting for deployment checks to start.")

    def test_background_task_status_api_does_not_wait_for_checks_when_app_has_no_registered_tasks(self):
        original_tasks = TASK_REGISTRY.get_all_tasks()
        try:
            TASK_REGISTRY._tasks.clear()
            BackgroundTask.objects.filter(app_instance=self.app_instance).delete()
            self.app_instance.k8s_user_app_status.status = "Running"
            self.app_instance.k8s_user_app_status.save(update_fields=["status"])
            self.app_instance.latest_user_action = "Changing"
            self.app_instance.save(update_fields=["latest_user_action"])
            requested_run_id = uuid.uuid4()

            response = self.client.get(
                reverse(
                    "apps:background_tasks_status",
                    kwargs={
                        "project": self.project.slug,
                        "app_slug": self.app.slug,
                        "app_id": self.app_instance.pk,
                    },
                )
                + f"?run_id={requested_run_id}",
            )
        finally:
            TASK_REGISTRY._tasks = original_tasks

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["tasks"], [])
        self.assertEqual(payload["deployment"]["status"], "success")
        self.assertEqual(payload["deployment"]["label"], "Done")

    def test_background_task_status_api_keeps_deploy_running_until_helm_records_success(self):
        BackgroundTask.objects.filter(app_instance=self.app_instance).update(status="success")
        self.app_instance.k8s_user_app_status.status = "Running"
        self.app_instance.k8s_user_app_status.save(update_fields=["status"])
        self.app_instance.latest_user_action = "Changing"
        self.app_instance.save(update_fields=["latest_user_action"])
        BackgroundTask.objects.create(
            app_instance=self.app_instance,
            task_name="validate_docker_image",
            task_type="validation",
            status="success",
            is_critical=True,
            execution_order=1,
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
        self.assertEqual(payload["deployment"]["status"], "success")
        self.assertEqual(payload["deployment"]["label"], "Done")

    def test_background_task_status_api_keeps_deploy_running_during_transient_notfound_state(self):
        BackgroundTask.objects.filter(app_instance=self.app_instance).update(status="success")
        self.app_instance.k8s_user_app_status.status = "NotFound"
        self.app_instance.k8s_user_app_status.save(update_fields=["status"])
        self.app_instance.latest_user_action = "Changing"
        self.app_instance.save(update_fields=["latest_user_action"])
        BackgroundTask.objects.create(
            app_instance=self.app_instance,
            task_name="validate_docker_image",
            task_type="validation",
            status="success",
            is_critical=True,
            execution_order=1,
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
        self.assertEqual(payload["deployment"]["status"], "pending")
        self.assertEqual(payload["deployment"]["label"], "Pending")

    def test_background_task_status_api_surfaces_helm_failure_after_checks_complete(self):
        BackgroundTask.objects.filter(app_instance=self.app_instance).update(status="success")
        self.app_instance.k8s_user_app_status.status = "Running"
        self.app_instance.k8s_user_app_status.save(update_fields=["status"])
        self.app_instance.latest_user_action = "Changing"
        self.app_instance.info = {"helm": {"success": False, "info": {"stderr": "chart upgrade failed"}}}
        self.app_instance.save()
        BackgroundTask.objects.create(
            app_instance=self.app_instance,
            task_name="validate_docker_image",
            task_type="validation",
            status="success",
            is_critical=True,
            execution_order=1,
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
        self.assertEqual(payload["deployment"]["status"], "failed")
        self.assertEqual(payload["deployment"]["label"], "Failed")

    def test_background_task_status_api_ignores_helm_failure_from_other_run(self):
        current_run_id = uuid.uuid4()
        previous_run_id = uuid.uuid4()
        BackgroundTask.objects.filter(app_instance=self.app_instance).update(run_id=previous_run_id, status="success")
        BackgroundTask.objects.create(
            app_instance=self.app_instance,
            task_name="validate_docker_image",
            task_type="validation",
            status="success",
            is_critical=True,
            execution_order=1,
            run_id=current_run_id,
        )
        BackgroundTask.objects.create(
            app_instance=self.app_instance,
            task_name="doi_provisioning",
            task_type="external_api",
            status="success",
            is_critical=False,
            execution_order=2,
            run_id=current_run_id,
        )
        self.app_instance.k8s_user_app_status.status = "Running"
        self.app_instance.k8s_user_app_status.save(update_fields=["status"])
        self.app_instance.latest_user_action = "Changing"
        self.app_instance.info = {
            "helm": {
                "success": False,
                "run_id": str(previous_run_id),
                "info": {"stderr": "chart upgrade failed"},
            }
        }
        self.app_instance.save()

        response = self.client.get(
            reverse(
                "apps:background_tasks_status",
                kwargs={
                    "project": self.project.slug,
                    "app_slug": self.app.slug,
                    "app_id": self.app_instance.pk,
                },
            )
            + f"?run_id={current_run_id}",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["deployment"]["status"], "success")
        self.assertEqual(payload["deployment"]["label"], "Done")

    def test_background_task_status_api_returns_metadata_only_progress_state(self):
        BackgroundTask.objects.create(
            app_instance=self.app_instance,
            task_name="validate_image_public",
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
        BackgroundTask.objects.filter(app_instance=self.app_instance).update(status="success")
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
            + "?mode=metadata_only",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["metadata_only"])
        self.assertEqual(payload["summary"]["total"], 1)
        self.assertEqual(payload["summary"]["skipped"], 1)
        self.assertEqual(payload["deployment"]["status"], "success")
        self.assertEqual(payload["deployment"]["label"], "Up to date")
        self.assertEqual(payload["deployment"]["step_status"], "skipped")
        self.assertEqual([task["task_name"] for task in payload["tasks"]], ["metadata_only_update"])
        self.assertEqual(payload["tasks"][0]["display_name"], "Metadata Change")
        self.assertTrue(payload["tasks"][0]["was_skipped"])
        self.assertEqual(
            payload["tasks"][0]["skip_reason"],
            "because app only gets redeployed on changes to image, subdomain, permissions and volumes",
        )

    def test_metadata_only_progress_keeps_previous_failed_deploy_step_failed(self):
        BackgroundTask.objects.filter(app_instance=self.app_instance).update(status="failed")
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
            + "?mode=metadata_only",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["metadata_only"])
        self.assertEqual(payload["deployment"]["status"], "blocked")
        self.assertEqual(payload["deployment"]["label"], "Blocked")
        self.assertEqual(payload["deployment"]["step_status"], "failed")
        self.assertEqual(
            [task["task_name"] for task in payload["tasks"]],
            ["metadata_only_update"],
        )
        self.assertEqual(
            payload["deployment"]["message"],
            "Your changes were saved, but deployment is blocked by a failed check.",
        )

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

    def test_background_task_status_api_exposes_structured_error_detail(self):
        BackgroundTask.objects.filter(app_instance=self.app_instance).update(
            status="failed",
            error_message="raw backend failure",
            result_data={
                "ui_error": {
                    "code": "image_not_public",
                    "summary": "We could not find this container image.",
                    "image_reference": "ghcr.io/example/app:bad",
                    "note": "Make sure the image is publicly available.",
                }
            },
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
        self.assertEqual(
            payload["tasks"][0]["error_detail"],
            {
                "code": "image_not_public",
                "summary": "We could not find this container image.",
                "image_reference": "ghcr.io/example/app:bad",
                "note": "Make sure the image is publicly available.",
            },
        )

    def test_legacy_unregistered_tasks_are_hidden_from_progress_pages(self):
        BackgroundTask.objects.create(
            app_instance=self.app_instance,
            task_name="mock_frontend_check",
            task_type="validation",
            status="success",
            is_critical=False,
            execution_order=99,
        )

        details_response = self.client.get(
            reverse(
                "apps:details",
                kwargs={
                    "project": self.project.slug,
                    "app_slug": self.app.slug,
                    "app_id": self.app_instance.pk,
                },
            )
        )
        self.assertEqual(details_response.status_code, 200)
        self.assertNotContains(details_response, "Mock Frontend Check")

        checks_response = self.client.get(
            reverse(
                "apps:background_tasks",
                kwargs={
                    "project": self.project.slug,
                    "app_slug": self.app.slug,
                    "app_id": self.app_instance.pk,
                },
            )
        )
        self.assertEqual(checks_response.status_code, 200)
        self.assertNotContains(checks_response, "Mock Frontend Check")

        status_response = self.client.get(
            reverse(
                "apps:background_tasks_status",
                kwargs={
                    "project": self.project.slug,
                    "app_slug": self.app.slug,
                    "app_id": self.app_instance.pk,
                },
            )
        )
        self.assertEqual(status_response.status_code, 200)
        payload = status_response.json()
        self.assertNotIn("mock_frontend_check", [task["task_name"] for task in payload["tasks"]])

    def test_background_task_status_api_details_mode_returns_recent_history(self):
        BackgroundTask.objects.filter(app_instance=self.app_instance).update(status="failed")
        self.app_instance.k8s_user_app_status.status = "Running"
        self.app_instance.k8s_user_app_status.save(update_fields=["status"])
        self.app_instance.latest_user_action = "Changing"
        self.app_instance.save()

        response = self.client.get(
            reverse(
                "apps:background_tasks_status",
                kwargs={
                    "project": self.project.slug,
                    "app_slug": self.app.slug,
                    "app_id": self.app_instance.pk,
                },
            )
            + "?mode=details",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload["metadata_only"])
        self.assertEqual(len(payload["tasks"]), 1)
        self.assertEqual(payload["tasks"][0]["task_name"], "validate_docker_image")
        self.assertEqual(payload["summary"]["total"], 1)

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
