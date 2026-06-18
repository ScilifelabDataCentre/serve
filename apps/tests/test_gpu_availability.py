from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.forms import CustomAppForm
from apps.gpu import (
    GPU_UNAVAILABLE_MESSAGE,
    GpuUnavailableError,
    ensure_gpu_capacity,
    flavor_gpu_count,
    gpu_available_for_flavor,
    gpus_in_use,
)
from apps.helpers import create_instance_from_form
from apps.models import (
    AppCategories,
    Apps,
    CustomAppInstance,
    JupyterInstance,
    K8sUserAppStatus,
    Subdomain,
    VolumeInstance,
)
from apps.tasks import delete_old_objects
from projects.models import Flavor, PersistentVolumeMountPath, Project

User = get_user_model()


class GpuAvailabilityTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("foo1", "foo@test.com", "bar")
        self.project = Project.objects.create_project(name="test-gpu", owner=self.user, description="")
        self.category = AppCategories.objects.create(name="Develop", priority=100, slug="develop")
        self.app = Apps.objects.create(name="Jupyter Lab", slug="jupyter-lab", category=self.category, gpu_enabled=True)
        self.gpu_flavor = Flavor.objects.create(name="gpu-flavor", project=self.project, gpu_req="1", gpu_lim="1")
        self.cpu_flavor = Flavor.objects.create(name="cpu-flavor", project=self.project)

    def create_jupyter_instance(self, flavor, subdomain_name, **kwargs):
        return JupyterInstance.objects.create(
            access="private",
            owner=self.user,
            name=f"app-{subdomain_name}",
            app=self.app,
            project=self.project,
            flavor=flavor,
            subdomain=Subdomain.objects.create(subdomain=subdomain_name),
            k8s_user_app_status=K8sUserAppStatus.objects.create(),
            **kwargs,
        )

    def test_flavor_gpu_count_parses_gpu_req(self):
        self.assertEqual(flavor_gpu_count(self.gpu_flavor), 1)
        self.assertEqual(flavor_gpu_count(self.cpu_flavor), 0)
        self.assertEqual(flavor_gpu_count(None), 0)
        self.assertEqual(flavor_gpu_count(Flavor(gpu_req="not-a-number")), 0)
        self.assertEqual(flavor_gpu_count(Flavor(gpu_req=None)), 0)

    def test_gpus_in_use_counts_active_gpu_apps(self):
        self.assertEqual(gpus_in_use(), 0)

        instance = self.create_jupyter_instance(self.gpu_flavor, "gpu-app")
        self.assertEqual(gpus_in_use(), 1)

        # The instance holding the GPU can be excluded, e.g. when it is being updated
        self.assertEqual(gpus_in_use(exclude_instance=instance), 0)

        # Apps without a GPU flavor do not count
        self.create_jupyter_instance(self.cpu_flavor, "cpu-app")
        self.assertEqual(gpus_in_use(), 1)

        # Deleted apps do not count
        instance.latest_user_action = "Deleting"
        instance.save(update_fields=["latest_user_action"])
        self.assertEqual(gpus_in_use(), 0)

    def test_gpus_in_use_ignores_apps_without_gpu_enabled_template(self):
        self.app.gpu_enabled = False
        self.app.save(update_fields=["gpu_enabled"])
        self.create_jupyter_instance(self.gpu_flavor, "gpu-app")
        self.assertEqual(gpus_in_use(), 0)

    @override_settings(GPU_TOTAL_CAPACITY=1)
    def test_gpu_available_for_flavor(self):
        self.assertTrue(gpu_available_for_flavor(self.gpu_flavor))
        self.assertTrue(gpu_available_for_flavor(self.cpu_flavor))

        instance = self.create_jupyter_instance(self.gpu_flavor, "gpu-app")
        self.assertFalse(gpu_available_for_flavor(self.gpu_flavor))
        self.assertTrue(gpu_available_for_flavor(self.cpu_flavor))
        self.assertTrue(gpu_available_for_flavor(self.gpu_flavor, exclude_instance=instance))

    @override_settings(GPU_TOTAL_CAPACITY=1)
    def test_ensure_gpu_capacity_passes_when_gpu_is_free(self):
        instance = JupyterInstance(app=self.app, flavor=self.gpu_flavor, project=self.project, owner=self.user)
        ensure_gpu_capacity(instance)

    @override_settings(GPU_TOTAL_CAPACITY=1)
    def test_ensure_gpu_capacity_raises_when_no_gpu_is_free(self):
        self.create_jupyter_instance(self.gpu_flavor, "gpu-app")
        instance = JupyterInstance(app=self.app, flavor=self.gpu_flavor, project=self.project, owner=self.user)
        with self.assertRaises(GpuUnavailableError):
            ensure_gpu_capacity(instance)

    @override_settings(GPU_TOTAL_CAPACITY=1)
    def test_ensure_gpu_capacity_noop_for_non_gpu_flavor(self):
        self.create_jupyter_instance(self.gpu_flavor, "gpu-app")
        instance = JupyterInstance(app=self.app, flavor=self.cpu_flavor, project=self.project, owner=self.user)
        ensure_gpu_capacity(instance)

    @override_settings(GPU_TOTAL_CAPACITY=1)
    def test_ensure_gpu_capacity_noop_when_app_template_not_gpu_enabled(self):
        self.app.gpu_enabled = False
        self.app.save(update_fields=["gpu_enabled"])
        instance = JupyterInstance(app=self.app, flavor=self.gpu_flavor, project=self.project, owner=self.user)
        ensure_gpu_capacity(instance)

    @override_settings(GPU_TOTAL_CAPACITY=1)
    def test_ensure_gpu_capacity_allows_existing_gpu_app_to_resave(self):
        instance = self.create_jupyter_instance(self.gpu_flavor, "gpu-app")
        ensure_gpu_capacity(instance)


class GpuFlavorFormTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("foo1", "foo@test.com", "bar")
        self.project = Project.objects.create_project(name="test-gpu-form", owner=self.user, description="")
        self.app = Apps.objects.create(name="Custom App", slug="customapp", gpu_enabled=True)
        self.volume = VolumeInstance.objects.create(
            name="project-vol",
            app=self.app,
            owner=self.user,
            project=self.project,
            size=1,
            subdomain=Subdomain.objects.create(subdomain="vol-subdomain", project=self.project),
            k8s_user_app_status=K8sUserAppStatus.objects.create(),
        )
        self.mount_path = PersistentVolumeMountPath.objects.create(
            volume=self.volume,
            mount_path="/home/data",
            is_default=True,
        )
        self.cpu_flavor = Flavor.objects.create(name="cpu-flavor", project=self.project)
        self.gpu_flavor = Flavor.objects.create(name="gpu-flavor", project=self.project, gpu_req="1", gpu_lim="1")

    def get_form_data(self, flavor):
        return {
            "name": "Valid Name",
            "description": "A valid description",
            "subdomain": "valid-subdomain",
            "mount_path": self.mount_path,
            "flavor": flavor,
            "access": "public",
            "source_code_url": "http://example.com",
            "note_on_linkonly_privacy": None,
            "port": 8000,
            "image": "mock.io/scilifelabdatacentre/image:tag",
            "default_url_subpath": "valid-default_url_subpath/",
            "invenio_tags": "Antibodies|Chemistry|Cats",
        }

    def create_gpu_holding_instance(self, subdomain_name="gpu-holder"):
        return CustomAppInstance.objects.create(
            owner=self.user,
            name="gpu-holder",
            app=self.app,
            project=self.project,
            flavor=self.gpu_flavor,
            subdomain=Subdomain.objects.create(subdomain=subdomain_name, project=self.project),
            k8s_user_app_status=K8sUserAppStatus.objects.create(),
        )

    @override_settings(GPU_TOTAL_CAPACITY=1)
    def test_gpu_flavor_allowed_when_gpu_is_free(self):
        form = CustomAppForm(self.get_form_data(self.gpu_flavor), project_pk=self.project.pk)
        self.assertTrue(form.is_valid(), form.errors)

    @override_settings(GPU_TOTAL_CAPACITY=1)
    def test_gpu_flavor_rejected_when_all_gpus_are_taken(self):
        self.create_gpu_holding_instance()

        form = CustomAppForm(self.get_form_data(self.gpu_flavor), project_pk=self.project.pk)
        self.assertFalse(form.is_valid())
        self.assertIn(GPU_UNAVAILABLE_MESSAGE, form.errors["flavor"])

    @override_settings(GPU_TOTAL_CAPACITY=1)
    def test_cpu_flavor_allowed_when_all_gpus_are_taken(self):
        self.create_gpu_holding_instance()

        form = CustomAppForm(self.get_form_data(self.cpu_flavor), project_pk=self.project.pk)
        self.assertTrue(form.is_valid(), form.errors)

    @override_settings(GPU_TOTAL_CAPACITY=1)
    def test_app_holding_gpu_can_keep_its_gpu_flavor(self):
        instance = self.create_gpu_holding_instance()

        form = CustomAppForm(self.get_form_data(self.gpu_flavor), project_pk=self.project.pk, instance=instance)
        self.assertTrue(form.is_valid(), form.errors)

    @override_settings(GPU_TOTAL_CAPACITY=1)
    def test_unavailable_gpu_flavor_is_disabled_in_widget(self):
        self.create_gpu_holding_instance()

        form = CustomAppForm(project_pk=self.project.pk)
        self.assertEqual(form.fields["flavor"].widget.unavailable_flavors, {str(self.gpu_flavor.pk)})
        # The preselected flavor falls back to one that does not require a GPU
        self.assertEqual(form.fields["flavor"].initial, self.cpu_flavor)

    @override_settings(GPU_TOTAL_CAPACITY=1)
    def test_gpu_flavor_not_disabled_in_widget_when_gpu_is_free(self):
        form = CustomAppForm(project_pk=self.project.pk)
        self.assertEqual(form.fields["flavor"].widget.unavailable_flavors, set())

    @override_settings(GPU_TOTAL_CAPACITY=1)
    def test_gpu_flavor_allowed_for_app_without_gpu_enabled_template(self):
        self.app.gpu_enabled = False
        self.app.save(update_fields=["gpu_enabled"])
        self.create_gpu_holding_instance()

        form = CustomAppForm(self.get_form_data(self.gpu_flavor), project_pk=self.project.pk)
        self.assertTrue(form.is_valid(), form.errors)

    @override_settings(GPU_TOTAL_CAPACITY=1)
    @patch("apps.helpers._deploy_with_background_tasks_and_doi")
    def test_create_instance_from_form_gate_blocks_second_gpu_app(self, _mock_deploy):
        first_form = CustomAppForm(self.get_form_data(self.gpu_flavor), project_pk=self.project.pk)
        second_data = self.get_form_data(self.gpu_flavor)
        second_data["subdomain"] = "second-subdomain"
        second_form = CustomAppForm(second_data, project_pk=self.project.pk)
        self.assertTrue(first_form.is_valid(), first_form.errors)
        self.assertTrue(second_form.is_valid(), second_form.errors)

        create_instance_from_form(first_form, self.project, "customapp")
        self.assertEqual(gpus_in_use(), 1)

        with self.assertRaises(GpuUnavailableError):
            create_instance_from_form(second_form, self.project, "customapp")
        self.assertEqual(CustomAppInstance.objects.count(), 1)
        self.assertEqual(gpus_in_use(), 1)


class DeleteOldGpuAppsTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("foo1", "foo@test.com", "bar")
        self.project = Project.objects.create_project(name="test-gpu-delete", owner=self.user, description="")
        self.category = AppCategories.objects.create(name="Develop", priority=100, slug="develop")
        self.app = Apps.objects.create(name="Jupyter Lab", slug="jupyter-lab", category=self.category, gpu_enabled=True)
        self.gpu_flavor = Flavor.objects.create(name="gpu-flavor", project=self.project, gpu_req="1", gpu_lim="1")
        self.cpu_flavor = Flavor.objects.create(name="cpu-flavor", project=self.project)

    def create_jupyter_instance(self, flavor, subdomain_name, age):
        instance = JupyterInstance.objects.create(
            access="private",
            owner=self.user,
            name=f"app-{subdomain_name}",
            app=self.app,
            project=self.project,
            flavor=flavor,
            subdomain=Subdomain.objects.create(subdomain=subdomain_name),
            k8s_user_app_status=K8sUserAppStatus.objects.create(),
        )
        # created_on has auto_now_add, so it must be backdated through a queryset update
        JupyterInstance.objects.filter(pk=instance.pk).update(created_on=timezone.now() - age)
        return instance

    @patch("apps.tasks.delete_resource.delay")
    def test_develop_app_with_gpu_is_deleted_after_one_day(self, mock_delay):
        instance = self.create_jupyter_instance(self.gpu_flavor, "gpu-old", timezone.timedelta(days=2))

        delete_old_objects()

        deleted_pks = [call.args[0]["pk"] for call in mock_delay.call_args_list]
        self.assertEqual(deleted_pks, [instance.pk])

    @patch("apps.tasks.delete_resource.delay")
    def test_develop_app_with_gpu_is_kept_within_one_day(self, mock_delay):
        self.create_jupyter_instance(self.gpu_flavor, "gpu-new", timezone.timedelta(hours=12))

        delete_old_objects()

        mock_delay.assert_not_called()

    @patch("apps.tasks.delete_resource.delay")
    def test_develop_app_without_gpu_is_kept_for_seven_days(self, mock_delay):
        self.create_jupyter_instance(self.cpu_flavor, "cpu-recent", timezone.timedelta(days=2))

        delete_old_objects()

        mock_delay.assert_not_called()

    @patch("apps.tasks.delete_resource.delay")
    def test_develop_app_without_gpu_is_deleted_after_seven_days(self, mock_delay):
        instance = self.create_jupyter_instance(self.cpu_flavor, "cpu-old", timezone.timedelta(days=8))

        delete_old_objects()

        deleted_pks = [call.args[0]["pk"] for call in mock_delay.call_args_list]
        self.assertEqual(deleted_pks, [instance.pk])
