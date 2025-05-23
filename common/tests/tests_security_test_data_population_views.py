import json

import pytest
from django.conf import settings
from django.http import HttpResponseForbidden
from django.middleware.csrf import get_token
from django.test import RequestFactory

from common.views import (
    CleanupAllTestProjectsView,
    CleanupTestProjectView,
    CleanupTestUserView,
    PopulateTestAppView,
    PopulateTestProjectView,
    PopulateTestSuperUserView,
    PopulateTestUserView,
)

user_data = {
    "affiliation": "uu",
    "department": "user-department-name",
    "email": "no-reply-user@scilifelab.uu.se",
    "first_name": "user-first-name",
    "last_name": "user-last-name",
    "password": "tesT12345@",
    "username": "unit_test_user",
}

superuser_data = {
    "email": "no-reply-superuser@scilifelab.uu.se",
    "password": "tesT12345@",
    "username": "unit_test_super_user",
}

project_data = {"project_name": "e2e-collections-test-proj", "project_description": "e2e-collections-test-proj-desc"}

app_data = {
    "app_slug": "dashapp",
    "name": "collection-app-name",
    "description": "collection-app-description",
    "access": "public",
    "port": 8000,
    "image": "ghcr.io/scilifelabdatacentre/example-dash:latest",
    "source_code_url": "https://someurlthatdoesnotexist.com",
}
# Test configuration
SECURITY_CONFIGS = [
    (
        PopulateTestUserView,
        "/devtools/populate-test-user/",
        {"user_data": user_data, "project_data": project_data, "app_data": app_data},
    ),
    (
        PopulateTestSuperUserView,
        "/devtools/populate-test-superuser/",
        {"user_data": superuser_data, "project_data": project_data, "app_data": app_data},
    ),
    (
        PopulateTestProjectView,
        "/devtools/populate-test-project/",
        {"user_data": user_data, "project_data": project_data, "app_data": app_data},
    ),
    (
        PopulateTestAppView,
        "/devtools/populate-test-app/",
        {"user_data": user_data, "project_data": project_data, "app_data": app_data},
    ),
    (
        CleanupTestProjectView,
        "/devtools/cleanup-test-project/",
        {"user_data": user_data, "project_data": project_data, "app_data": app_data},
    ),
    (
        CleanupAllTestProjectsView,
        "/devtools/cleanup-all-test-projects/",
        {"user_data": user_data, "project_data": project_data, "app_data": app_data},
    ),
    (
        CleanupTestUserView,
        "/devtools/cleanup-test-user/",
        {"user_data": user_data, "project_data": project_data, "app_data": app_data},
    ),
]
USER_CONFIGS = [
    (PopulateTestUserView, "/devtools/populate-test-user/", {"user_data": user_data}),
    (PopulateTestSuperUserView, "/devtools/populate-test-superuser/", {"user_data": superuser_data}),
    (CleanupTestUserView, "/devtools/cleanup-test-user/", {"user_data": user_data}),
    (CleanupTestUserView, "/devtools/cleanup-test-user/", {"user_data": superuser_data}),
]


@pytest.fixture
def factory():
    return RequestFactory()


@pytest.fixture
def csrf_token(factory):
    """Generate a valid CSRF token"""
    request = factory.get("/dummy-url/")
    return get_token(request)


# Security check tests
@pytest.mark.parametrize("view_class,endpoint,payload", SECURITY_CONFIGS)
def test_development_environment_check(view_class, endpoint, payload, factory, csrf_token):
    settings.DEBUG = False
    request = factory.post(
        endpoint,
        json.dumps(payload),
        content_type="application/json",
        headers={"X-CSRFToken": csrf_token},
    )
    request.COOKIES["csrftoken"] = csrf_token
    response = view_class.as_view()(request)
    assert isinstance(response, HttpResponseForbidden)
    assert "Test functionality disabled in production" in str(response.content)


# Invalid JSON test
@pytest.mark.parametrize("view_class,endpoint,_", SECURITY_CONFIGS)
def test_invalid_json_check(view_class, endpoint, _, factory, csrf_token):
    settings.DEBUG = True
    request = factory.post(
        endpoint,
        "invalid{json",
        content_type="application/json",
        headers={"X-CSRFToken": csrf_token},
    )
    request.COOKIES["csrftoken"] = csrf_token
    response = view_class.as_view()(request)
    assert response.status_code == 400
    assert json.loads(response.content)["error"] == "Invalid JSON format"


@pytest.mark.parametrize("view_class,endpoint,payload", SECURITY_CONFIGS)
def test_csrf_protection_check(view_class, endpoint, payload, factory, csrf_token):
    settings.DEBUG = True

    # Test missing CSRF token
    request = factory.post(endpoint, json.dumps(payload), content_type="application/json", headers={})
    response = view_class.as_view()(request)
    assert response.status_code == 403
    assert "CSRF" in str(response.content)

    # Test invalid CSRF token
    request = factory.post(
        endpoint,
        json.dumps(payload),
        content_type="application/json",
        headers={"X-CSRFToken": "invalid-token"},
    )
    request.COOKIES["csrftoken"] = csrf_token  # Cookie/header mismatch
    response = view_class.as_view()(request)
    assert response.status_code == 403
    assert "CSRF" in str(response.content)


@pytest.mark.django_db
@pytest.mark.parametrize("view_class,endpoint,payload", USER_CONFIGS)
def test_valid_user(view_class, endpoint, payload, factory, csrf_token):
    settings.DEBUG = True

    request = factory.post(
        endpoint,
        json.dumps(payload),
        content_type="application/json",
        headers={"X-CSRFToken": csrf_token},
    )
    request.COOKIES["csrftoken"] = csrf_token
    response = view_class.as_view()(request)
    assert response.status_code == 200
