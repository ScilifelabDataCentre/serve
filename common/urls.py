from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.urls import include, path

from . import views

app_name = "common"

urlpatterns = [
    path("success/", views.RegistrationCompleteView.as_view(), name="success"),
    path("signup/", views.SignUpView.as_view(), name="signup"),
    path("verify/", views.VerifyView.as_view(), name="verify"),
<<<<<<< HEAD
    path("edit-profile/", login_required(views.EditProfileView.as_view()), name="edit-profile"),
=======
    path("edit-profile/", views.EditProfileView.as_view(), name="edit-profile"),
    path("admin_profile_edit_disabled/", views.EditProfileView.as_view(), name="admin_profile_edit_disabled"),
>>>>>>> 0ed33936100075cb1b452129be1296397bbff6dd
]
