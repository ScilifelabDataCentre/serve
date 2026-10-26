"""Activating a file manager reuses a previously deleted one instead of creating a new row."""

from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.constants import AppActionOrigin
from apps.forms import FilemanagerForm
from apps.helpers import create_instance_from_form
from apps.models import (
    Apps,
    FilemanagerInstance,
    K8sUserAppStatus,
    Subdomain,
    VolumeInstance,
)
from apps.tasks import delete_resource
from projects.models import Flavor, Project

User = get_user_model()

APP_SLUG = "filemanager"


@patch("apps.tasks.run_background_tasks.delay")
class FilemanagerReuseTestCase(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user("foo1", "foo@test.com", "bar")
        self.project = Project.objects.create_project(name="test-fm-reuse", owner=self.user, description="")
        self.other_project = Project.objects.create_project(name="test-fm-other", owner=self.user, description="")
        self.app = Apps.objects.create(name="File Manager", slug=APP_SLUG)
        self.volume_app = Apps.objects.create(name="Persistent Volume", slug="volumeK8s")
        self.flavor = Flavor.objects.create(name="flavor", project=self.project)
        self.volume_1 = self._create_volume("project-vol-1", "vol-sub-1")
        self.volume_2 = self._create_volume("project-vol-2", "vol-sub-2")

    def _create_volume(self, name, subdomain):
        return VolumeInstance.objects.create(
            name=name,
            app=self.volume_app,
            owner=self.user,
            project=self.project,
            size=1,
            subdomain=Subdomain.objects.create(subdomain=subdomain, project=self.project),
            k8s_user_app_status=K8sUserAppStatus.objects.create(),
        )

    def _create_filemanager(
        self,
        project=None,
        subdomain="fm-old",
        latest_user_action="SystemDeleting",
        deleted_ago=timedelta(days=2),
        persistent=False,
        delete_finished=True,
    ):
        project = project or self.project
        created_on = timezone.now() - timedelta(days=3)
        instance = FilemanagerInstance.objects.create(
            app=self.app,
            name="Old File Manager",
            access="private",
            owner=self.user,
            project=project,
            flavor=self.flavor,
            persistent=persistent,
            latest_user_action=latest_user_action,
            deleted_on=timezone.now() - deleted_ago if deleted_ago is not None else None,
            subdomain=Subdomain.objects.create(subdomain=subdomain, project=project),
            k8s_user_app_status=K8sUserAppStatus.objects.create(status="Running"),
            info={"helm": {"success": True, "deleted_at": timezone.now().isoformat()} if delete_finished else None},
        )
        instance.volume.set([self.volume_1])
        # created_on is auto_now_add, so it can only be backdated with an update.
        FilemanagerInstance.objects.filter(pk=instance.pk).update(created_on=created_on)
        instance.refresh_from_db()
        return instance

    def _activate(self, volumes=None):
        volumes = volumes if volumes is not None else [self.volume_2]
        data = {
            "name": "File Manager",
            "access": "project",
            "flavor": self.flavor.pk,
            "volume": [v.pk for v in volumes],
        }
        form = FilemanagerForm(data, project_pk=self.project.pk)
        self.assertTrue(form.is_valid(), form.errors)

        with self.captureOnCommitCallbacks(execute=True):
            result = create_instance_from_form(form, self.project, APP_SLUG)
        return result

    def test_reuses_deleted_filemanager(self, mock_deploy):
        old = self._create_filemanager()
        old_created_on = old.created_on
        before = timezone.now()

        result = self._activate(volumes=[self.volume_2])

        self.assertEqual(result.instance_id, old.pk)
        self.assertEqual(FilemanagerInstance.objects.count(), 1)

        reused = FilemanagerInstance.objects.get(pk=old.pk)
        self.assertGreaterEqual(reused.created_on, before)
        self.assertGreater(reused.created_on, old_created_on)
        self.assertIsNone(reused.deleted_on)
        self.assertEqual(reused.latest_user_action, "Creating")
        self.assertEqual(reused.access, "project")
        self.assertEqual(reused.name, "File Manager")
        self.assertEqual(list(reused.volume.all()), [self.volume_2])
        # The subdomain of the deleted file manager is kept.
        self.assertEqual(reused.subdomain.subdomain, "fm-old")
        self.assertEqual(reused.k8s_values["apps"]["volumeK8s"], {"project-vol-2": {"release": "vol-sub-2"}})
        # Stale deployment state is cleared before redeploying.
        self.assertIsNone(reused.k8s_user_app_status.status)
        self.assertFalse(isinstance(reused.info, dict) and "helm" in reused.info)
        # The automatic deletion window restarts from the reactivation.
        self.assertGreater(reused.scheduled_deletion_at, timezone.now())
        mock_deploy.assert_called_once()

    def test_reuses_most_recently_deleted_filemanager(self, mock_deploy):
        self._create_filemanager(subdomain="fm-older", deleted_ago=timedelta(days=5))
        newest = self._create_filemanager(subdomain="fm-newer", latest_user_action="Deleting")

        result = self._activate()

        self.assertEqual(result.instance_id, newest.pk)
        self.assertEqual(FilemanagerInstance.objects.count(), 2)

    def test_creates_new_filemanager_when_none_exists(self, mock_deploy):
        result = self._activate()

        instance = FilemanagerInstance.objects.get(pk=result.instance_id)
        self.assertEqual(FilemanagerInstance.objects.count(), 1)
        self.assertEqual(instance.latest_user_action, "Creating")
        self.assertIsNone(instance.deleted_on)
        self.assertEqual(list(instance.volume.all()), [self.volume_2])
        mock_deploy.assert_called_once()

    def test_does_not_reuse_filemanager_of_another_project(self, mock_deploy):
        other = self._create_filemanager(project=self.other_project)

        result = self._activate()

        self.assertNotEqual(result.instance_id, other.pk)
        other.refresh_from_db()
        self.assertEqual(other.latest_user_action, "SystemDeleting")
        self.assertIsNotNone(other.deleted_on)

    def test_does_not_reuse_persistent_filemanager(self, mock_deploy):
        persistent = self._create_filemanager(persistent=True)

        result = self._activate()

        self.assertNotEqual(result.instance_id, persistent.pk)
        persistent.refresh_from_db()
        self.assertEqual(persistent.latest_user_action, "SystemDeleting")

    def test_does_not_reuse_active_filemanager(self, mock_deploy):
        active = self._create_filemanager(latest_user_action="Creating", deleted_ago=None)

        result = self._activate()

        self.assertNotEqual(result.instance_id, active.pk)
        active.refresh_from_db()
        self.assertEqual(list(active.volume.all()), [self.volume_1])

    def test_does_not_reuse_filemanager_with_pending_delete(self, mock_deploy):
        """A delete task that has not finished yet could remove the reused instance."""
        pending = self._create_filemanager(latest_user_action="Deleting", delete_finished=False)

        result = self._activate()

        self.assertNotEqual(result.instance_id, pending.pk)
        pending.refresh_from_db()
        self.assertEqual(pending.latest_user_action, "Deleting")

    def test_reuses_filemanager_deleted_moments_ago(self, mock_deploy):
        recent = self._create_filemanager(latest_user_action="Deleting", deleted_ago=timedelta(seconds=5))

        result = self._activate()

        self.assertEqual(result.instance_id, recent.pk)

    @patch("apps.tasks.get_merged_k8s_values", return_value={"subdomain": "fm-old", "namespace": "default"})
    @patch("apps.tasks.helm_delete", return_value=("release uninstalled", None))
    def test_delete_resource_marks_delete_as_finished(self, mock_helm_delete, mock_values, mock_deploy):
        instance = self._create_filemanager(latest_user_action="Deleting", delete_finished=False)

        delete_resource({"model": instance._meta.label_lower, "pk": instance.pk}, AppActionOrigin.USER.value)

        instance.refresh_from_db()
        self.assertIn("deleted_at", instance.info["helm"])
        self.assertEqual(FilemanagerInstance.objects.get_reusable_instance(self.project), instance)

    def test_reused_filemanager_without_subdomain_gets_a_new_one(self, mock_deploy):
        old = self._create_filemanager()
        FilemanagerInstance.objects.filter(pk=old.pk).update(subdomain=None)

        result = self._activate()

        self.assertEqual(result.instance_id, old.pk)
        reused = FilemanagerInstance.objects.get(pk=old.pk)
        self.assertIsNotNone(reused.subdomain)
        self.assertNotEqual(reused.subdomain.subdomain, "fm-old")

    def test_updating_existing_filemanager_is_unaffected(self, mock_deploy):
        """Reuse only applies when activating, not when an existing file manager is updated."""
        deleted = self._create_filemanager(subdomain="fm-deleted")
        active = self._create_filemanager(subdomain="fm-active", latest_user_action="Creating", deleted_ago=None)

        data = {
            "name": "Renamed",
            "access": "project",
            "flavor": self.flavor.pk,
            "volume": [self.volume_2.pk],
            "subdomain": "fm-active",
        }
        form = FilemanagerForm(data, project_pk=self.project.pk, instance=active)
        self.assertTrue(form.is_valid(), form.errors)
        with self.captureOnCommitCallbacks(execute=True):
            result = create_instance_from_form(form, self.project, APP_SLUG, app_id=active.pk)

        self.assertEqual(result.instance_id, active.pk)
        deleted.refresh_from_db()
        self.assertEqual(deleted.latest_user_action, "SystemDeleting")
