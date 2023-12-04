import pytest
from django.test import override_settings


@pytest.fixture(scope="session", autouse=True)
def set_django_settings():
    with override_settings(INACTIVE_USERS=False):
        yield
