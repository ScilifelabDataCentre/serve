from django.test import TestCase

from apps.tasks import (
    DEPLOY_RESOURCE_MAX_RETRIES,
    POD_LESS_APP_SLUGS,
    should_retry_deploy,
)


class ShouldRetryDeployTestCase(TestCase):
    def test_a_normal_app_retries_until_the_limit(self):
        self.assertTrue(should_retry_deploy("customapp", 0, DEPLOY_RESOURCE_MAX_RETRIES))
        self.assertFalse(should_retry_deploy("customapp", DEPLOY_RESOURCE_MAX_RETRIES, DEPLOY_RESOURCE_MAX_RETRIES))

    def test_pod_less_app_types_never_retry(self):
        for slug in POD_LESS_APP_SLUGS:
            self.assertFalse(should_retry_deploy(slug, 0, DEPLOY_RESOURCE_MAX_RETRIES), f"{slug} retried")
