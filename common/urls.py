from django.conf import settings
from django.contrib.auth import views as auth_views
from django.urls import include, path

from . import views

# from .views import PopulateTestDataView, CleanupTestDataView

app_name = "common"

urlpatterns = [
    path("success/", views.RegistrationCompleteView.as_view(), name="success"),
    path("signup/", views.SignUpView.as_view(), name="signup"),
    path("verify/", views.VerifyView.as_view(), name="verify"),
    path("verify/reset/", views.VerificationTokenResetView.as_view(), name="verifyreset"),
    path("edit-profile/", views.EditProfileView.as_view(), name="edit-profile"),
    path("password-change/", views.ChangePasswordView.as_view(), name="password-change"),
    path("admin_profile_edit_disabled/", views.EditProfileView.as_view(), name="admin_profile_edit_disabled"),
]

if settings.DEBUG:
    urlpatterns += [
        path("devtools/populate-test-user/", views.PopulateTestUserView.as_view(), name="populate-test-user"),
        path(
            "devtools/populate-test-superuser/",
            views.PopulateTestSuperUserView.as_view(),
            name="populate-test-superuser",
        ),
        path("devtools/cleanup-test-user/", views.CleanupTestUserView.as_view(), name="cleanup-test-user"),
        path("devtools/populate-test-project/", views.PopulateTestProjectView.as_view(), name="populate-test-project"),
        path("devtools/cleanup-test-project/", views.CleanupTestProjectView.as_view(), name="cleanup-test-project"),
        path(
            "devtools/cleanup-all-test-projects/",
            views.CleanupAllTestProjectsView.as_view(),
            name="cleanup-all-test-projects",
        ),
        path("devtools/populate-test-app/", views.PopulateTestAppView.as_view(), name="populate-test-app"),
    ]
