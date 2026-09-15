from unittest.mock import Mock, patch
from urllib.parse import urlencode

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.test import Client, TestCase, override_settings
from guardian.shortcuts import assign_perm

from common.models import UserProfile
from projects.models import Project

from ..helpers import CreateInstanceResult
from ..models import Apps, JupyterInstance, K8sUserAppStatus, Subdomain

User = get_user_model()

test_user = {"username": "foo1", "email": "foo@test.com", "password": "bar"}


class CreateAppViewTestCase(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(test_user["username"], test_user["email"], test_user["password"])
        self.app = Apps.objects.create(
            name="Jupyter Lab",
            slug="jupyter-lab",
        )

    def get_data(self, user=None):
        project = Project.objects.create_project(
            name="test-perm", owner=user if user is not None else self.user, description=""
        )

        return project

    @override_settings(
        APPS_PER_PROJECT_LIMIT={
            "jupyter-lab": 1,
        }
    )
    def test_has_permission(self):
        c = Client()

        project = self.get_data()

        response = c.post("/accounts/login/", {"username": test_user["email"], "password": test_user["password"]})
        response.status_code

        self.assertEqual(response.status_code, 302)

        response = c.get(f"/projects/{project.slug}/apps/create/jupyter-lab")

        self.assertEqual(response.status_code, 200)

    @override_settings(APPS_PER_PROJECT_LIMIT={"jupyter-lab": 0})
    def test_has_reached_app_limit(self):
        c = Client()

        project = self.get_data()

        response = c.post("/accounts/login/", {"username": test_user["email"], "password": test_user["password"]})
        response.status_code

        self.assertEqual(response.status_code, 302)

        response = c.get(f"/projects/{project.slug}/apps/create/jupyter-lab")

        self.assertEqual(response.status_code, 403)

        response = c.post(f"/projects/{project.slug}/apps/create/jupyter-lab")

        self.assertEqual(response.status_code, 403)

    @override_settings(APPS_PER_PROJECT_LIMIT={"jupyter-lab": 1})
    def test_missing_access_to_project(self):
        c = Client()

        user = User.objects.create_user("foo12", "foo2@test.com", "bar2")

        project = self.get_data(user)

        response = c.post("/accounts/login/", {"username": test_user["email"], "password": test_user["password"]})
        response.status_code

        self.assertEqual(response.status_code, 302)

        response = c.get(f"/projects/{project.slug}/apps/create/jupyter-lab")

        self.assertEqual(response.status_code, 403)

        response = c.post(f"/projects/{project.slug}/apps/create/jupyter-lab")

        self.assertEqual(response.status_code, 403)

    @override_settings(
        APPS_PER_PROJECT_LIMIT={
            "jupyter-lab": None,
        }
    )
    def test_has_permission_when_none(self):
        c = Client()

        project = self.get_data()

        response = c.post("/accounts/login/", {"username": test_user["email"], "password": test_user["password"]})
        response.status_code

        self.assertEqual(response.status_code, 302)

        response = c.get(f"/projects/{project.slug}/apps/create/jupyter-lab")

        self.assertEqual(response.status_code, 200)

    @override_settings(APPS_PER_PROJECT_LIMIT={})
    def test_has_permission_when_not_specified(self):
        c = Client()

        project = self.get_data()

        response = c.post("/accounts/login/", {"username": test_user["email"], "password": test_user["password"]})
        response.status_code

        self.assertEqual(response.status_code, 302)

        response = c.get(f"/projects/{project.slug}/apps/create/jupyter-lab")

        self.assertEqual(response.status_code, 200)

    @override_settings(
        APPS_PER_PROJECT_LIMIT={
            "jupyter-lab": 1,
        }
    )
    def test_has_permission_project_level(self):
        c = Client()

        project = self.get_data()

        response = c.post("/accounts/login/", {"username": test_user["email"], "password": test_user["password"]})
        response.status_code

        self.assertEqual(response.status_code, 302)

        response = c.get(f"/projects/{project.slug}/apps/create/jupyter-lab")

        self.assertEqual(response.status_code, 200)

        project = self.get_data()

        response = c.get(f"/projects/{project.slug}/apps/create/jupyter-lab")

        self.assertEqual(response.status_code, 200)

        subdomain = Subdomain.objects.create(subdomain="test_internal")
        k8s_user_app_status = K8sUserAppStatus.objects.create()
        _ = JupyterInstance.objects.create(
            access="private",
            owner=self.user,
            name="test_app_instance_private",
            app=self.app,
            project=project,
            subdomain=subdomain,
            k8s_user_app_status=k8s_user_app_status,
        )

        response = c.get(f"/projects/{project.slug}/apps/create/jupyter-lab")

        self.assertEqual(response.status_code, 403)

    @override_settings(APPS_PER_PROJECT_LIMIT={"jupyter-lab": 0})
    def test_permission_overrides_reached_app_limit(self):
        c = Client()

        project = self.get_data()

        response = c.post("/accounts/login/", {"username": test_user["email"], "password": test_user["password"]})
        response.status_code

        self.assertEqual(response.status_code, 302)

        response = c.get(f"/projects/{project.slug}/apps/create/jupyter-lab")

        self.assertEqual(response.status_code, 403)

        content_type = ContentType.objects.get_for_model(JupyterInstance)
        project_permissions = Permission.objects.filter(content_type=content_type)

        add_permission = next(
            (perm for perm in project_permissions if perm.codename == "add_jupyterinstance"),
            None,
        )

        self.user.user_permissions.add(add_permission)

        self.user = User.objects.get(username=test_user["email"])

        response = c.get(f"/projects/{project.slug}/apps/create/jupyter-lab")

        self.assertEqual(response.status_code, 200)

    def make_privileged(self, user):
        profile, _ = UserProfile.objects.get_or_create(user=user)
        profile.is_privileged = True
        profile.save()

    def existing_instance(self, project, owner, subdomain="test_internal"):
        return JupyterInstance.objects.create(
            access="private",
            owner=owner,
            name="test_app_instance_private",
            app=self.app,
            project=project,
            subdomain=Subdomain.objects.create(subdomain=subdomain),
            k8s_user_app_status=K8sUserAppStatus.objects.create(),
        )

    @override_settings(APPS_PER_PROJECT_LIMIT={"jupyter-lab": 1})
    def test_privileged_user_can_create_past_the_app_limit(self):
        c = Client()
        project = self.get_data()
        self.existing_instance(project, self.user)

        c.post("/accounts/login/", {"username": test_user["email"], "password": test_user["password"]})

        self.assertEqual(c.get(f"/projects/{project.slug}/apps/create/jupyter-lab").status_code, 403)

        self.make_privileged(self.user)

        self.assertEqual(c.get(f"/projects/{project.slug}/apps/create/jupyter-lab").status_code, 200)

    @override_settings(APPS_PER_PROJECT_LIMIT={"jupyter-lab": 0})
    def test_privileged_user_cannot_create_a_disabled_app_type(self):
        c = Client()
        project = self.get_data()
        self.make_privileged(self.user)

        c.post("/accounts/login/", {"username": test_user["email"], "password": test_user["password"]})

        self.assertEqual(c.get(f"/projects/{project.slug}/apps/create/jupyter-lab").status_code, 403)

    @override_settings(APPS_PER_PROJECT_LIMIT={"jupyter-lab": 1})
    def test_app_limit_is_per_project(self):
        c = Client()

        project = self.get_data()

        response = c.post("/accounts/login/", {"username": test_user["email"], "password": test_user["password"]})
        response.status_code

        self.assertEqual(response.status_code, 302)

        response = c.get(f"/projects/{project.slug}/apps/create/jupyter-lab")

        self.assertEqual(response.status_code, 200)

        user2 = User.objects.create_user("foo123", "foo123@test.com", "bar123")

        project.authorized.add(user2)
        project.save()

        response = c.get(f"/projects/{project.slug}/apps/create/jupyter-lab")

        self.assertEqual(response.status_code, 200)

        subdomain = Subdomain.objects.create(subdomain="test_internal")
        k8s_user_app_status = K8sUserAppStatus.objects.create()
        _ = JupyterInstance.objects.create(
            access="private",
            owner=self.user,
            name="test_app_instance_private",
            app=self.app,
            project=project,
            subdomain=subdomain,
            k8s_user_app_status=k8s_user_app_status,
        )

        response = c.get(f"/projects/{project.slug}/apps/create/jupyter-lab")

        self.assertEqual(response.status_code, 403)

        response = c.get(f"/projects/{project.slug}/apps/create/jupyter-lab")

        self.assertEqual(response.status_code, 403)

    @override_settings(APPS_PER_PROJECT_LIMIT={"jupyter-lab": 1})
    def test_app_limit_altered_for_project(self):
        c = Client()

        project = self.get_data()

        response = c.post("/accounts/login/", {"username": test_user["email"], "password": test_user["password"]})
        response.status_code

        self.assertEqual(response.status_code, 302)

        project.apps_per_project["jupyter-lab"] = 0

        project.save()

        response = c.get(f"/projects/{project.slug}/apps/create/jupyter-lab")

        self.assertEqual(response.status_code, 403)

    @override_settings(APPS_PER_PROJECT_LIMIT={"jupyter-lab": 1})
    def test_app_limit_altered_for_project_v2(self):
        c = Client()

        project = self.get_data()

        response = c.post("/accounts/login/", {"username": test_user["email"], "password": test_user["password"]})
        response.status_code

        self.assertEqual(response.status_code, 302)

        response = c.get(f"/projects/{project.slug}/apps/create/jupyter-lab")

        self.assertEqual(response.status_code, 200)

        subdomain = Subdomain.objects.create(subdomain="test_internal")
        k8s_user_app_status = K8sUserAppStatus.objects.create()
        _ = JupyterInstance.objects.create(
            access="private",
            owner=self.user,
            name="test_app_instance_private",
            app=self.app,
            project=project,
            subdomain=subdomain,
            k8s_user_app_status=k8s_user_app_status,
        )

        response = c.get(f"/projects/{project.slug}/apps/create/jupyter-lab")

        self.assertEqual(response.status_code, 403)

        project.apps_per_project["jupyter-lab"] = 2

        project.save()

        response = c.get(f"/projects/{project.slug}/apps/create/jupyter-lab")

        self.assertEqual(response.status_code, 200)

    @override_settings(APPS_PER_PROJECT_LIMIT={"jupyter-lab": 1})
    def test_submit_redirects_to_deployment_progress_page(self):
        c = Client()
        project = self.get_data()
        c.force_login(self.user)

        fake_form = Mock()
        fake_form.is_valid.return_value = True
        fake_form.instance.app.should_display_deployment_details = True

        with (
            patch("apps.views.CreateApp.get_form", return_value=fake_form),
            patch(
                "apps.views.create_instance_from_form",
                return_value=CreateInstanceResult(
                    instance_id=321,
                    progress_started_at="2026-04-17T10:11:12+00:00",
                    workflow_started=True,
                ),
            ),
        ):
            response = c.post(
                f"/projects/{project.slug}/apps/create/jupyter-lab",
            )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url,
            "/projects/"
            f"{project.slug}/apps/progress/jupyter-lab/321?"
            f"{urlencode({'started_at': '2026-04-17T10:11:12+00:00'})}",
        )

        fake_form = Mock()
        fake_form.is_valid.return_value = True
        fake_form.instance.app.should_display_deployment_details = False

        with (
            patch("apps.views.CreateApp.get_form", return_value=fake_form),
            patch(
                "apps.views.create_instance_from_form",
                return_value=CreateInstanceResult(
                    instance_id=321,
                    progress_started_at="2026-04-17T10:11:12+00:00",
                    workflow_started=True,
                ),
            ),
        ):
            response = c.post(f"/projects/{project.slug}/apps/create/jupyter-lab")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, f"/projects/{project.slug}/")
