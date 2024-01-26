from datetime import datetime, timedelta

import pytz
from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist
from django.test import TestCase, TransactionTestCase

from projects.models import Project

from ..helpers import HandleUpdateStatusResponseCode, handle_update_status_request
from ..models import AppCategories, AppInstance, Apps, AppStatus

utc = pytz.UTC

User = get_user_model()

test_user = {"username": "foo@test.com", "email": "foo@test.com", "password": "bar"}


class UpdateAppStatusNonExistingAppTestCase(TestCase):
    """Test case for request of non-existing app instance."""

    def test_handle_nonexisting_app_should_raise_exception(self):
        release = "non-existing-app-release"

        with self.assertRaises(ObjectDoesNotExist):
            handle_update_status_request(release, "NewStatus", datetime.now)


class UpdateAppStatusTestCase(TestCase):
    """Test case for requests operating on an existing app instance."""

    ACTUAL_RELEASE_NAME = "test-release-name"
    INITIAL_STATUS = "Created"
    INITIAL_EVENT_TS = utc.localize(datetime.now())

    def setUp(self) -> None:
        self.user = User.objects.create_user(test_user["username"], test_user["email"], test_user["password"])
        self.category = AppCategories.objects.create(name="Network", priority=100, slug="network")
        self.app = Apps.objects.create(
            name="Jupyter Lab",
            slug="jupyter-lab",
            user_can_edit=False,
            category=self.category,
        )

        self.project = Project.objects.create_project(name="test-perm-get_status", owner=self.user, description="")

        self.app_instance = AppInstance.objects.create(
            access="public",
            owner=self.user,
            name="test_app_instance_public",
            app=self.app,
            project=self.project,
            parameters={
                "environment": {"pk": ""},
                "release": self.ACTUAL_RELEASE_NAME,
            },
            state=self.INITIAL_STATUS,
        )

    def setUpCreateAppStatus(self):
        self.status_object = AppStatus(appinstance=self.app_instance)
        self.status_object.status_type = self.INITIAL_STATUS
        self.status_object.save()
        # Must re-save with the desired timeUpdate the app instance object
        self.status_object.time = self.INITIAL_EVENT_TS
        self.status_object.save(update_fields=["time"])

    def test_handle_old_event_time_should_ignore_update(self):
        self.setUpCreateAppStatus()
        older_ts = self.INITIAL_EVENT_TS - timedelta(seconds=1)
        actual = handle_update_status_request(self.ACTUAL_RELEASE_NAME, "NewStatus", older_ts)

        assert actual == HandleUpdateStatusResponseCode.NO_ACTION

        # Fetch the app instance and status objects and verify values
        actual_app_instance = AppInstance.objects.filter(
            parameters__contains={"release": self.ACTUAL_RELEASE_NAME}
        ).last()

        assert actual_app_instance.state == self.INITIAL_STATUS
        actual_appstatus = actual_app_instance.status.latest()
        assert actual_appstatus.status_type == self.INITIAL_STATUS
        assert actual_appstatus.time == self.INITIAL_EVENT_TS

    def test_handle_same_status_newer_time_should_update_time(self):
        self.setUpCreateAppStatus()
        newer_ts = self.INITIAL_EVENT_TS + timedelta(seconds=1)
        actual = handle_update_status_request(self.ACTUAL_RELEASE_NAME, self.INITIAL_STATUS, newer_ts)

        assert actual == HandleUpdateStatusResponseCode.UPDATED_TIME_OF_STATUS

        # Fetch the app instance and status objects and verify values
        actual_app_instance = AppInstance.objects.filter(
            parameters__contains={"release": self.ACTUAL_RELEASE_NAME}
        ).last()

        assert actual_app_instance.state == self.INITIAL_STATUS
        actual_appstatus = actual_app_instance.status.latest()
        assert actual_appstatus.status_type == self.INITIAL_STATUS
        assert actual_appstatus.time == newer_ts

    def test_handle_different_status_newer_time_should_update_status(self):
        self.setUpCreateAppStatus()
        newer_ts = self.INITIAL_EVENT_TS + timedelta(seconds=1)
        new_status = self.INITIAL_STATUS + "-test01"
        actual = handle_update_status_request(self.ACTUAL_RELEASE_NAME, new_status, newer_ts)

        assert actual == HandleUpdateStatusResponseCode.UPDATED_STATUS

        # Fetch the app instance and status objects and verify values
        actual_app_instance = AppInstance.objects.filter(
            parameters__contains={"release": self.ACTUAL_RELEASE_NAME}
        ).last()

        assert actual_app_instance.state == new_status
        actual_appstatus = actual_app_instance.status.latest()
        assert actual_appstatus.status_type == new_status
        assert actual_appstatus.time == newer_ts

    def test_handle_missing_app_status_should_create_and_update_status(self):
        newer_ts = self.INITIAL_EVENT_TS + timedelta(seconds=1)
        new_status = self.INITIAL_STATUS + "-test02"
        actual = handle_update_status_request(self.ACTUAL_RELEASE_NAME, new_status, newer_ts)

        assert actual == HandleUpdateStatusResponseCode.CREATED_FIRST_STATUS

        # Fetch the app instance and status objects and verify values
        actual_app_instance = AppInstance.objects.filter(
            parameters__contains={"release": self.ACTUAL_RELEASE_NAME}
        ).last()

        assert actual_app_instance.state == new_status
        actual_appstatus = actual_app_instance.status.latest()
        assert actual_appstatus.status_type == new_status
        assert actual_appstatus.time == newer_ts
