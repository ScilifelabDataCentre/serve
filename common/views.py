import json

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import PasswordChangeView
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponseForbidden, JsonResponse
from django.http.response import HttpResponseRedirect
from django.shortcuts import HttpResponse, redirect, render
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_protect
from django.views.generic import CreateView, TemplateView

from common.management.manage_test_data import TestDataManager
from studio.utils import get_logger

from .forms import (
    ChangePasswordForm,
    ProfileEditForm,
    ProfileForm,
    SignUpForm,
    TokenVerificationForm,
    UserEditForm,
    UserForm,
)
from .models import EmailVerificationTable, UserProfile
from .tasks import send_email_task

logger = get_logger(__name__)


# Create your views here.
class HomeView(TemplateView):
    template_name = "common/landing.html"


class RegistrationCompleteView(TemplateView):
    template_name = "registration/registration_complete.html"


# Sign Up View
class SignUpView(CreateView):
    """
    View for user registration

    This view uses two forms: UserForm and ProfileForm together, and due to that it's a bit complicated.
    See SS-507 for more information.

    From technical perspective, it relies on django calling ``form_valid`` to validate form first.
    If the form is valid, it will save the form and redirect to ``success`` page.

    If the form is invalid, it will call ``custom_form_invalid`` to render the form again with errors.

    But if there are any errors with UserForm it will call ``form_invalid`` first.
    """

    template_name = "registration/signup.html"
    form_class = UserForm

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if "profile_form" not in context:
            context["profile_form"] = ProfileForm(self.request.POST or None)
        return context

    # Transaction decorator is needed for form_.save() to work properly
    @transaction.atomic
    def form_valid(self, form):
        context = self.get_context_data()
        profile_form = context["profile_form"]
        form_ = SignUpForm(user=form, profile=profile_form)
        if form_.is_valid():
            # If the email is unique, save the form
            if form_.user.is_unique_email():
                form_.save()
            # Otherwise, we will see in the logs that the email is not unique, but users will not see this.
            # See SS-920 for more information.
            redirect_name = "login"
            if settings.INACTIVE_USERS:
                messages.success(
                    self.request,
                    (
                        "Please check your email for a verification link."
                        " If you don’t see it, perhaps you already have an account on our service, "
                        "try the forgot password route linked below."
                        " Otherwise contact us at serve@scilifelab.se."
                    ),
                )
            else:
                messages.success(self.request, "Account created successfully!")
            return HttpResponseRedirect(reverse_lazy(redirect_name))
        else:
            return self.custom_form_invalid(form, profile_form)

    def custom_form_invalid(self, user_form, profile_form):
        # Both user_form and profile_form are form instances with their current state.
        context = self.get_context_data()
        context["form"] = user_form  # The user form with its current state and errors.
        context["profile_form"] = profile_form  # The profile form with its current state and errors.
        return self.render_to_response(context)

    def form_invalid(self, form):
        # Just in case this gets called, redirect it to the custom handler.
        # 'form' here will be a UserForm instance.
        profile_form = self.get_context_data().get("profile_form")
        return self.custom_form_invalid(form, profile_form)


class VerifyView(TemplateView):
    form_class = TokenVerificationForm
    template_name = "registration/verify.html"

    def get(self, request, *args, **kwargs):
        token = request.GET.get("token")
        form = self.form_class(initial={"token": token})
        return render(request, self.template_name, {"form": form})

    def post(self, request, *args, **kwargs):
        form = self.form_class(request.POST)
        if form.is_valid():
            try:
                email_verification_table = EmailVerificationTable.objects.get(token=form.cleaned_data["token"])
                user = email_verification_table.user

                # If user is approved, it means that the user is affiliated with the university
                # and we can activate the account right away.
                if user.userprofile.is_approved:
                    user.is_active = True
                    user.save()
                    messages.success(request, "Email verified successfully!")
                else:
                    # If user is not approved, we send an email to the admin to approve the account.
                    send_email_task(
                        "User has verified their email address",
                        f"Please go to the admin page to activate account for {user.email}",
                        ["serve@scilifelab.se"],
                    )
                    messages.success(
                        request, "Your email address has been verified. Please wait for admin to approve your account."
                    )

                email_verification_table.delete()
                return redirect("login")
            except EmailVerificationTable.DoesNotExist:
                messages.error(request, "Invalid token!")
                return redirect("portal:home")
        return render(request, self.template_name, {"form": form})


@method_decorator(login_required, name="dispatch")
class EditProfileView(TemplateView):
    template_name = "user/profile_edit_form.html"

    profile_edit_form_class = ProfileEditForm
    user_edit_form_class = UserEditForm

    def get_user_profile_info(self, request):
        # Get the user profile from database
        try:
            # Note that not all users have a user profile object
            # such as the admin superuser
            user_profile = UserProfile.objects.get(user_id=request.user.id)
        except ObjectDoesNotExist as e:
            logger.error(str(e), exc_info=True)
            user_profile = UserProfile()
        except Exception as e:
            logger.error(str(e), exc_info=True)
            user_profile = UserProfile()

        return user_profile

    def get(self, request, *args, **kwargs):
        # admin user
        if request.user.email in ["admin@serve.scilifelab.se", "event_user@serve.scilifelab.se"]:
            return render(request, "user/admin_profile_edit_disabled.html")

        # common user with or without Staff/Superuser status
        else:
            user_profile_data = self.get_user_profile_info(request)

            profile_edit_form = self.profile_edit_form_class(
                initial={
                    "affiliation": user_profile_data.affiliation,
                    "department": user_profile_data.department,
                }
            )

            user_edit_form = self.user_edit_form_class(
                initial={
                    "email": user_profile_data.user.email,
                    "first_name": user_profile_data.user.first_name,
                    "last_name": user_profile_data.user.last_name,
                }
            )

            return render(request, self.template_name, {"form": user_edit_form, "profile_form": profile_edit_form})

    def post(self, request, *args, **kwargs):
        user_profile_data = self.get_user_profile_info(request)

        user_form_details = self.user_edit_form_class(
            request.POST,
            instance=request.user,
            initial={
                "email": user_profile_data.user.email,
            },
        )

        profile_form_details = self.profile_edit_form_class(
            request.POST,
            instance=user_profile_data,
            initial={
                "affiliation": user_profile_data.affiliation,
            },
        )

        if user_form_details.is_valid() and profile_form_details.is_valid():
            try:
                with transaction.atomic():
                    user_form_details.save()
                    profile_form_details.save()

                    logger.info("Updated First Name: " + str(self.get_user_profile_info(request).user.first_name))
                    logger.info("Updated Last Name: " + str(self.get_user_profile_info(request).user.last_name))
                    logger.info("Updated Department: " + str(self.get_user_profile_info(request).department))

            except Exception as e:
                return HttpResponse("Error updating records: " + str(e))

            return render(request, "user/profile.html", {"user_profile": self.get_user_profile_info(request)})

        else:
            if not user_form_details.is_valid():
                logger.error("Edit user error: " + str(user_form_details.errors))

            if not profile_form_details.is_valid():
                logger.error("Edit profile error: " + str(profile_form_details.errors))

            return render(
                request, self.template_name, {"form": user_form_details, "profile_form": profile_form_details}
            )


@method_decorator(login_required, name="dispatch")
class ChangePasswordView(PasswordChangeView):
    form_class = ChangePasswordForm
    template_name = "registration/password_change_form.html"


class PopulateTestUserView(View):
    @method_decorator(csrf_protect)
    def post(self, request):
        """Secure endpoint for test superuser creation with validation and error handling"""
        # production guard and secret validation
        if not settings.DEBUG:
            logger.warning("Production access attempt to test endpoint")
            return HttpResponseForbidden("Test functionality disabled in production")

        try:
            body = json.loads(request.body)
            required_keys = {"user_data"}
            if not required_keys.issubset(body):
                missing = required_keys - body.keys()
                raise ValueError(f"Missing required data: {missing}")

            manager = TestDataManager(user_data=body["user_data"])

            _ = manager.create_user()

            return JsonResponse({"success": True, "user": body["user_data"]["username"]})

        except json.JSONDecodeError:
            logger.error("Invalid JSON payload")
            return JsonResponse({"error": "Invalid JSON format"}, status=400)

        except Exception as e:
            logger.error(f"Test user creation failed: {e}")
            return JsonResponse({"error": str(e)}, status=500)


class PopulateTestSuperUserView(View):
    @method_decorator(csrf_protect)
    def post(self, request):
        """Secure endpoint for test superuser creation with validation and error handling"""
        # production guard
        if not settings.DEBUG:
            logger.warning("Production access attempt to test endpoint")
            return HttpResponseForbidden("Test functionality disabled in production")

        try:
            body = json.loads(request.body)
            required_keys = {"user_data"}
            if not required_keys.issubset(body):
                missing = required_keys - body.keys()
                raise ValueError(f"Missing required data: {missing}")

            manager = TestDataManager(user_data=body["user_data"])

            _ = manager.create_superuser()

            return JsonResponse({"success": True, "superuser": body["user_data"]["username"]})

        except json.JSONDecodeError:
            logger.error("Invalid JSON payload")
            return JsonResponse({"error": "Invalid JSON format"}, status=400)

        except Exception as e:
            logger.error(f"Test superuser creation failed: {e}")
            return JsonResponse({"error": str(e)}, status=500)


class CleanupTestUserView(View):
    @method_decorator(csrf_protect)
    def post(self, request):
        """Secure endpoint for test user deletion with validation and error handling"""
        # production guard
        if not settings.DEBUG:
            logger.warning("Production access attempt to test endpoint")
            return HttpResponseForbidden("Test functionality disabled in production")

        try:
            body = json.loads(request.body)
            required_keys = {"user_data"}
            if not required_keys.issubset(body):
                missing = required_keys - body.keys()
                raise ValueError(f"Missing required data: {missing}")

            manager = TestDataManager(user_data=body["user_data"])

            count = manager.delete_user()

            return JsonResponse({"success": True, "user": body["user_data"]["username"], "users deleted": count})

        except json.JSONDecodeError:
            logger.error("Invalid JSON payload")
            return JsonResponse({"error": "Invalid JSON format"}, status=400)

        except Exception as e:
            logger.error(f"Test user deletion failed: {e}")
            return JsonResponse({"error": str(e)}, status=500)


class PopulateTestProjectView(View):
    @method_decorator(csrf_protect)
    def post(self, request):
        """Secure endpoint for test project deletion with validation and error handling"""
        # production guard
        if not settings.DEBUG:
            logger.warning("Production access attempt to test endpoint")
            return HttpResponseForbidden("Test functionality disabled in production")

        try:
            body = json.loads(request.body)
            required_keys = {"user_data", "project_data"}
            if not required_keys.issubset(body):
                missing = required_keys - body.keys()
                raise ValueError(f"Missing required data: {missing}")

            manager = TestDataManager(
                user_data=body["user_data"],
                project_data=body["project_data"],
            )

            project = manager.create_project()

            return JsonResponse({"success": True, "user": body["user_data"]["username"], "project": project.name})

        except json.JSONDecodeError:
            logger.error("Invalid JSON payload")
            return JsonResponse({"error": "Invalid JSON format"}, status=400)

        except Exception as e:
            logger.error(f"Test project creation failed: {e}")
            return JsonResponse({"error": str(e)}, status=500)


class CleanupTestProjectView(View):
    @method_decorator(csrf_protect)
    def post(self, request):
        """Secure endpoint for test project deletion with validation and error handling"""
        # production guard
        if not settings.DEBUG:
            logger.warning("Production access attempt to test endpoint")
            return HttpResponseForbidden("Test functionality disabled in production")

        try:
            body = json.loads(request.body)
            required_keys = {"user_data", "project_data"}
            if not required_keys.issubset(body):
                missing = required_keys - body.keys()
                raise ValueError(f"Missing required data: {missing}")

            manager = TestDataManager(
                user_data=body["user_data"],
                project_data=body["project_data"],
            )

            count = manager.delete_project()

            return JsonResponse({"success": True, "user": body["user_data"]["username"], "projects deleted": count})

        except json.JSONDecodeError:
            logger.error("Invalid JSON payload")
            return JsonResponse({"error": "Invalid JSON format"}, status=400)

        except Exception as e:
            logger.error(f"Test project deletion failed: {e}")
            return JsonResponse({"error": str(e)}, status=500)


class CleanupAllTestProjectsView(View):
    @method_decorator(csrf_protect)
    def post(self, request):
        """Secure endpoint for all test projects deletion with validation and error handling"""
        # production guard
        if not settings.DEBUG:
            logger.warning("Production access attempt to test endpoint")
            return HttpResponseForbidden("Test functionality disabled in production")

        try:
            body = json.loads(request.body)
            required_keys = {"user_data"}
            if not required_keys.issubset(body):
                missing = required_keys - body.keys()
                raise ValueError(f"Missing required data: {missing}")

            manager = TestDataManager(user_data=body["user_data"])

            count = manager.delete_all_projects()

            return JsonResponse({"success": True, "user": body["user_data"]["username"], "projects deleted": count})

        except json.JSONDecodeError:
            logger.error("Invalid JSON payload")
            return JsonResponse({"error": "Invalid JSON format"}, status=400)

        except Exception as e:
            logger.error(f"Test all projects deletion failed: {e}")
            return JsonResponse({"error": str(e)}, status=500)


class PopulateTestAppView(View):
    @method_decorator(csrf_protect)
    def post(self, request):
        """Secure endpoint for test app creation with validation and error handling"""
        # production guard
        if not settings.DEBUG:
            logger.warning("Production access attempt to test endpoint")
            return HttpResponseForbidden("Test functionality disabled in production")

        try:
            body = json.loads(request.body)
            required_keys = {"user_data", "project_data", "app_data"}
            if not required_keys.issubset(body):
                missing = required_keys - body.keys()
                raise ValueError(f"Missing required data: {missing}")

            manager = TestDataManager(
                user_data=body["user_data"], project_data=body["project_data"], app_data=body["app_data"]
            )

            status = manager.create_app()

            return JsonResponse(
                {
                    "success": status,
                    "app": body["app_data"]["name"],
                    "user": body["user_data"]["username"],
                    "project": body["project_data"]["project_name"],
                }
            )

        except json.JSONDecodeError:
            logger.error("Invalid JSON payload")
            return JsonResponse({"error": "Invalid JSON format"}, status=400)

        except Exception as e:
            logger.error(f"Test app creation failed: {e}")
            return JsonResponse({"error": str(e)}, status=500)
