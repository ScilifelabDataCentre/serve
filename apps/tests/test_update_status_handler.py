import concurrent.futures
import time
from datetime import datetime, timedelta

import pytest
import pytz
from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist
from django.test import TestCase, TransactionTestCase

from projects.models import Project

from ..constants import HandleUpdateStatusResponseCode
from ..helpers import handle_update_status_request
from ..models import AppCategories, Apps, JupyterInstance, K8sUserAppStatus, Subdomain

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
    INITIAL_STATUS = "Unknown"
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

        subdomain = Subdomain.objects.create(subdomain=self.ACTUAL_RELEASE_NAME)
        self.app_instance = JupyterInstance.objects.create(
            access="private",
            owner=self.user,
            name="test_app_instance_private",
            app=self.app,
            project=self.project,
            subdomain=subdomain,
            k8s_values={
                "environment": {"pk": ""},
                "release": self.ACTUAL_RELEASE_NAME,
            },
        )
        print(f"######## {self.INITIAL_EVENT_TS}")

    def setUpCreateK8sUserAppStatus(self):
        k8s_user_app_status = K8sUserAppStatus.objects.create(status=self.INITIAL_STATUS)
        k8s_user_app_status.time = self.INITIAL_EVENT_TS
        k8s_user_app_status.save()
        self.app_instance.k8s_user_app_status = k8s_user_app_status
        self.app_instance.save(update_fields=["k8s_user_app_status"])
        print(f"######## {k8s_user_app_status.time}")

    def test_handle_old_event_time_should_ignore_update(self):
        self.setUpCreateK8sUserAppStatus()
        older_ts = self.app_instance.k8s_user_app_status.time - timedelta(seconds=1)
        new_status = "PodInitializing"
        actual = handle_update_status_request(self.ACTUAL_RELEASE_NAME, new_status, older_ts)

        assert actual == HandleUpdateStatusResponseCode.NO_ACTION

        # Fetch the app instance and status objects and verify values
        actual_app_instance = JupyterInstance.objects.filter(
            k8s_values__contains={"release": self.ACTUAL_RELEASE_NAME}
        ).last()

        assert actual_app_instance.k8s_user_app_status.status == self.INITIAL_STATUS
        actual_k8suser_appstatus = actual_app_instance.k8s_user_app_status
        assert actual_k8suser_appstatus.status == self.INITIAL_STATUS
        assert actual_k8suser_appstatus.time == self.INITIAL_EVENT_TS

    def test_handle_same_status_newer_time_should_update_time(self):
        self.setUpCreateK8sUserAppStatus()
        newer_ts = self.app_instance.k8s_user_app_status.time + timedelta(seconds=1)
        actual = handle_update_status_request(self.ACTUAL_RELEASE_NAME, self.INITIAL_STATUS, newer_ts)

        assert actual == HandleUpdateStatusResponseCode.UPDATED_TIME_OF_STATUS

        # Fetch the app instance and status objects and verify values
        actual_app_instance = JupyterInstance.objects.filter(
            k8s_values__contains={"release": self.ACTUAL_RELEASE_NAME}
        ).last()

        assert actual_app_instance.k8s_user_app_status.status == self.INITIAL_STATUS
        actual_k8suser_appstatus = actual_app_instance.k8s_user_app_status
        assert actual_k8suser_appstatus.status == self.INITIAL_STATUS
        assert actual_k8suser_appstatus.time == newer_ts

    def test_handle_different_status_newer_time_should_update_status(self):
        self.setUpCreateK8sUserAppStatus()
        newer_ts = self.app_instance.k8s_user_app_status.time + timedelta(seconds=1)
        # new_status = self.INITIAL_STATUS + "-test01"
        new_status = "PodInitializing"
        actual = handle_update_status_request(self.ACTUAL_RELEASE_NAME, new_status, newer_ts)

        assert actual == HandleUpdateStatusResponseCode.UPDATED_STATUS

        # Fetch the app instance and status objects and verify values
        actual_app_instance = JupyterInstance.objects.filter(
            k8s_values__contains={"release": self.ACTUAL_RELEASE_NAME}
        ).last()

        assert actual_app_instance.k8s_user_app_status.status == new_status
        actual_k8suser_appstatus = actual_app_instance.k8s_user_app_status
        assert actual_k8suser_appstatus.status == new_status
        assert actual_k8suser_appstatus.time == newer_ts

    def test_handle_missing_k8s_user_app_status_should_create_and_update_status(self):
        newer_ts = self.INITIAL_EVENT_TS + timedelta(seconds=1)
        # new_status = self.INITIAL_STATUS + "-test02"
        new_status = "PodInitializing"
        actual = handle_update_status_request(self.ACTUAL_RELEASE_NAME, new_status, newer_ts)

        assert actual == HandleUpdateStatusResponseCode.CREATED_FIRST_STATUS

        # Fetch the app instance and status objects and verify values
        actual_app_instance = JupyterInstance.objects.filter(
            k8s_values__contains={"release": self.ACTUAL_RELEASE_NAME}
        ).last()

        assert actual_app_instance.k8s_user_app_status.status == new_status
        actual_k8suser_appstatus = actual_app_instance.k8s_user_app_status
        assert actual_k8suser_appstatus.status == new_status
        assert actual_k8suser_appstatus.time == newer_ts

    @pytest.mark.skip("Skipped because the k8s_user_app_status field is now restricted to a domain of values.")
    def test_handle_long_status_text_should_trim_status(self):
        """
        This test verifies that the status code can be trimmed to a max length of chars and used.
        TODO: Revisit:
        NOTE: This is undergoing refactoring and this test may no longer be valid.
        """
        newer_ts = self.INITIAL_EVENT_TS + timedelta(seconds=1)
        new_status = "LongStatusText-ThisPartLongerThan20Chars"
        expected_status_text = new_status[:20]
        assert len(expected_status_text) == 20
        actual = handle_update_status_request(self.ACTUAL_RELEASE_NAME, new_status, newer_ts)

        assert actual == HandleUpdateStatusResponseCode.CREATED_FIRST_STATUS

        # Fetch the app instance and status objects and verify values
        actual_app_instance = JupyterInstance.objects.filter(
            k8s_values__contains={"release": self.ACTUAL_RELEASE_NAME}
        ).last()

        assert actual_app_instance.k8s_user_app_status.status == expected_status_text
        actual_k8suser_appstatus = actual_app_instance.k8s_user_app_status
        assert actual_k8suser_appstatus.status == expected_status_text
        assert actual_k8suser_appstatus.time == newer_ts


'''
#TODO: THIS TEST NEEDS TO BE UPDATED TO ADHERE TO NEW LOGIC
@pytest.mark.skip(
    reason="This test requires a modification to the handle_update_status_request function to add a delay parameter."
)
class UpdateAppStatusConcurrentRequestsTestCase(TransactionTestCase):
    """Test case for concurrent requests operating on an existing app instance."""

    ACTUAL_RELEASE_NAME = "test-release-name"
    INITIAL_STATUS = "StatusA"
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
        self.setUpCreateAppStatus()

    def setUpCreateAppStatus(self):
        self.status_object = AppStatus(appinstance=self.app_instance)
        self.status_object.status_type = self.INITIAL_STATUS
        self.status_object.save()
        # Must re-save with the desired timeUpdate the app instance object
        self.status_object.time = self.INITIAL_EVENT_TS
        self.status_object.save(update_fields=["time"])

    def test_concurrent_requests(self):
        """
        To test concurrent tests, we use 2 requests:
        (a) a request to update the status to StatusA (same as first) and time to +3 secs
        (b) a request to update the status to StatusB (different) and time to +1

        1. begin request (a), pause after the select operation (fetching of the app instance object)
        2. begin another request (b) that completes by updating the status to StatusB and the time
        3. complete request (a) by updating the time
        """

        # Verify test data created from test setup
        actual_app_instance = AppInstance.objects.filter(
            parameters__contains={"release": self.ACTUAL_RELEASE_NAME}
        ).last()

        assert actual_app_instance.state == self.INITIAL_STATUS
        actual_appstatus = actual_app_instance.status.latest()
        assert actual_appstatus.status_type == self.INITIAL_STATUS
        assert actual_appstatus.time == self.INITIAL_EVENT_TS

        # Test the function using 2 threads
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            task_futures = []

            task_futures.append(executor.submit(self.submit_request_new_time))

            # Give the first request time to start
            time.sleep(0.01)

            task_futures.append(executor.submit(self.submit_request_new_status))

            for future in concurrent.futures.as_completed(task_futures):
                result = future.result()
                print(result)
                if result[0] == "submit_request_new_time":
                    assert result[1] == HandleUpdateStatusResponseCode.UPDATED_TIME_OF_STATUS
                elif result[0] == "submit_request_new_status":
                    assert result[1] == HandleUpdateStatusResponseCode.NO_ACTION

        # Verify that the end result is as expected
        actual_app_instance = AppInstance.objects.filter(
            parameters__contains={"release": self.ACTUAL_RELEASE_NAME}
        ).last()

        # Expected final state values are: status = StatusA, time = time + 3
        assert actual_app_instance.state == self.INITIAL_STATUS
        actual_appstatus = actual_app_instance.status.latest()
        assert actual_appstatus.status_type == self.INITIAL_STATUS
        assert actual_appstatus.time == self.INITIAL_EVENT_TS + timedelta(seconds=3)

    def submit_request_new_time(self):
        """A request to update the time for status StatusA."""
        print("Begin submit_request_new_time")
        newer_ts = self.INITIAL_EVENT_TS + timedelta(seconds=3)
        # Note that this next line requires a modification to the handle_update_status_request function by adding a new
        # parameter update_delay_seconds int = 0
        actual = handle_update_status_request(self.ACTUAL_RELEASE_NAME, self.INITIAL_STATUS, newer_ts, None, 1)
        return "submit_request_new_time", actual

    def submit_request_new_status(self):
        print("Begin submit_request_new_status")
        newer_ts = self.INITIAL_EVENT_TS + timedelta(seconds=1)
        new_status = "StatusB"
        actual = handle_update_status_request(self.ACTUAL_RELEASE_NAME, new_status, newer_ts)
        return "submit_request_new_status", actual
'''
