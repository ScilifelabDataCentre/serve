from django.conf import settings
from django.contrib import messages
from django.core.mail import send_mail
from django.db import transaction
from django.http.response import HttpResponseRedirect
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.views.generic import CreateView, TemplateView

from .forms import ProfileForm, SignUpForm, TokenVerificationForm, UserForm
from .models import EmailVerificationTable


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
            form_.save()
            redirect_name = "login"
            if settings.INACTIVE_USERS:
                messages.success(self.request, "Please check your email to verify your account!")
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
                    send_mail(
                        f"User {user.email} has verified their email address",
                        "Please go to the admin page to activate their account.",
                        settings.EMAIL_HOST_USER,
                        # TODO: Change this to the email of the admin
                        # ["serve@scilifelab.se"],
                        [settings.EMAIL_HOST_USER],
                        fail_silently=False,
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
