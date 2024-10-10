import json
import re
import uuid
from dataclasses import dataclass
from typing import Optional, Sequence

from django import forms
from django.conf import settings
from django.contrib.auth import password_validation
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.validators import EmailValidator
from django.db import transaction
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _

from common.models import EmailVerificationTable, UserProfile
from studio.utils import get_logger

logger = get_logger(__name__)


with open(settings.STATICFILES_DIRS[0] + "/common/departments.json", "r") as f:
    DEPARTMENTS = json.load(f).get("departments", [])

with open(settings.STATICFILES_DIRS[0] + "/common/universities.json", "r") as f:
    UNIVERSITIES = json.load(f).get("universities", dict())
    UNIVERSITIES = [(k, v) for k, v in UNIVERSITIES.items()]


# Regex for validating email domain
# Same regexp could be found in templates/registration/signup.html
EMAIL_ALLOW_REGEX = re.compile(
    (
        r"^(?:(?!\b(?:student|stud)\b\.)[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)*?"  # Subdomain part
        + f"({('|').join([u[0] for u in UNIVERSITIES if u[0] != 'other'])}"
        + r")\.se"  # End of the domain
    ),
    re.IGNORECASE,
)


class ListTextWidget(forms.TextInput):
    """
    This widget is used to create a text input with a list of options on input.
    """

    def __init__(self, data_list, name, *args, **kwargs):
        super(ListTextWidget, self).__init__(*args, **kwargs)
        self._name = name
        self._list = data_list
        self.attrs.update({"list": "list__%s" % self._name})

    def render(self, name, value, attrs=None, renderer=None):
        """
        Render the widget as an HTML string.
        """
        text_html = super(ListTextWidget, self).render(name, value, attrs=attrs)
        data_list = '<datalist id="list__%s">' % self._name
        for item in self._list:
            data_list += '<option value="%s">' % item
        data_list += "</datalist>"

        return text_html + data_list


class BootstrapErrorFormMixin:
    """
    This is a base class for all forms that use bootstrap.

    It adds bootstrap error classes to fields

    Because of ``is_valid`` method, it should be used with Django forms only.
    """

    def add_error_classes(self):
        for field_name, errors in self.errors.items():
            if errors:
                self.fields[field_name].widget.attrs.update(
                    {"class": "form-control is-invalid", "aria-describedby": f"validation_{field_name}"}
                )
            else:
                self.fields[field_name].widget.attrs.update({"class": "form-control"})

    def is_valid(self):
        valid = super().is_valid()
        if not valid:
            self.add_error_classes()
        return valid


class UserForm(BootstrapErrorFormMixin, UserCreationForm):
    first_name = forms.CharField(
        min_length=1,
        max_length=30,
        label="First name",
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    last_name = forms.CharField(
        min_length=1,
        max_length=30,
        label="Last name",
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    email = forms.EmailField(
        max_length=254,
        label="Email",
        widget=forms.TextInput(attrs={"class": "form-control"}),
        help_text=mark_safe(
            "Use your <a "
            "href='https://www.uka.se/sa-fungerar-hogskolan/universitet-och-hogskolor/lista-over-"
            "universitet-hogskolor-och-enskilda-utbildningsanordnare'>"
            "Swedish university</a> email address. If you are not affiliated with a Swedish university, "
            "your account request will be reviewed manually."
        ),
        # disabled = True,
    )
    password1 = forms.CharField(
        min_length=8,
        label="Password",
        widget=forms.PasswordInput(attrs={"class": "form-control"}),
        help_text=password_validation.password_validators_help_text_html(),
    )
    password2 = forms.CharField(
        min_length=8,
        label="Confirm password",
        widget=forms.PasswordInput(attrs={"class": "form-control"}),
    )

    required_css_class = "required"

    class Meta:
        model = User
        fields = [
            "username",
            "first_name",
            "last_name",
            "email",
            "password1",
            "password2",
        ]
        exclude = [
            "username",
        ]

    def is_unique_email(self) -> bool:
        email: str = self.cleaned_data["email"].lower()
        return not User.objects.filter(email=email).exists()

    def clean_email(self) -> str:
        """
        Validate that the supplied email address is unique.

        This runs after the basic `UserCreationForm` validation.
        """
        email: str = self.cleaned_data["email"].lower()
        # See SS-920 to understand why we are doing this
        if not self.is_unique_email():
            logger.error("Attempting to create an account with email %s that is already in use", email)
        return email

    def add_error_classes(self) -> None:
        """
        Add bootstrap error classes to fields and move errors from password2 to password1
        so that errors are displayed in one place on the left side of the form
        """
        super().add_error_classes()
        if "password1" in self.errors or "password2" in self.errors:
            self.fields["password1"].widget.attrs.update({"class": "form-control is-invalid"})
            self.fields["password2"].widget.attrs.update({"class": "form-control is-invalid"})
            errors_p1 = self.errors.get("password1", [])
            self.errors["password1"] = errors_p1 + self.errors.get("password2", [])
            if "password2" in self.errors:
                del self.errors["password2"]

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.data})"


class ProfileForm(BootstrapErrorFormMixin, forms.ModelForm):
    affiliation = forms.ChoiceField(
        widget=forms.Select(attrs={"class": "form-control"}),
        label="University",
        choices=UNIVERSITIES,
        help_text="Your university affiliation, must match the email address.",
    )
    department = forms.CharField(
        widget=ListTextWidget(data_list=DEPARTMENTS, name="department-list", attrs={"class": "form-control"}),
        label="Department",
        required=False,
        help_text="Select closest department name or enter your own.",
    )
    why_account_needed = forms.CharField(
        widget=forms.Textarea(attrs={"class": "form-control", "style": "height: 70px"}),
        required=False,
        label="How do you plan to use Serve?",
        help_text="Because you are not using a Swedish university researcher email, "
        "please describe why you need an account."
        " Your request will be manually evaluated by the Serve team.",
    )
    note = forms.CharField(
        widget=forms.Textarea(attrs={"class": "form-control", "style": "height: 70px"}),
        required=False,
        label="Do you require support?",
        help_text="If you would like us to get in touch with you, to answer your questions or provide help with "
        "Serve, please describe how we can help you here.",
    )

    required_css_class = "required"

    class Meta:
        model = UserProfile
        fields = [
            "affiliation",
            "department",
            "note",
            "why_account_needed",
        ]

    def __repr__(self):
        return f"{self.__class__.__name__}({self.data})"


@dataclass
class SignUpForm:
    """
    This class is used to validate user and profile forms together.
    """

    user: UserForm
    profile: ProfileForm
    is_approved: bool = False

    def clean(self) -> None:
        user_data = self.user.cleaned_data
        profile_data = self.profile.cleaned_data

        email = user_data.get("email", "")
        affiliation = profile_data.get("affiliation")
        why_account_needed = profile_data.get("why_account_needed")
        user_data["email"] = email.lower()
        affiliation_from_email = email.split("@")[1].split(".")[-2].lower()

        is_university_email = EMAIL_ALLOW_REGEX.match(email.split("@")[1]) is not None
        is_affiliated = affiliation is not None and affiliation != "other"
        is_request_account_empty = not bool(why_account_needed)
        is_department_empty = not bool(profile_data.get("department"))

        self.is_approved = is_university_email

        if is_university_email:
            # Check that selected affiliation is equal to affiliation from email
            if is_affiliated and affiliation != affiliation_from_email:
                self.profile.add_error(
                    "affiliation", ValidationError("Email affiliation is different from selected university")
                )
            if not is_affiliated:
                self.profile.add_error(
                    "affiliation", ValidationError("You are required to select a university affiliation")
                )
            if is_department_empty:
                self.profile.add_error("department", ValidationError("You are required to select your department"))
        else:
            if is_affiliated:
                self.user.add_error(
                    "email",
                    ValidationError(
                        "Email was not recognized as a researcher email from a Swedish university. \n"
                        "Please select 'Other' in affiliation or use your Swedish university researcher email."
                    ),
                )
                self.profile.add_error("affiliation", ValidationError(""))

            if is_request_account_empty:
                self.profile.add_error("why_account_needed", ValidationError("Please describe why you need an account"))

    def _is_valid(self) -> bool:
        # these two calls are done that way, so that we can get errors for both forms and display them together
        is_user_valid: bool = self.user.is_valid()
        is_profile_valid: bool = self.profile.is_valid()
        return is_user_valid and is_profile_valid

    def is_valid(self, force_clean=False) -> bool:
        # is_valid calls from user and profile forms are needed to get cleaned_data attributes
        # cleaned_data is needed for clean method to work properly
        # This results in this spagetty code, but it works.
        is_valid = self._is_valid()
        if is_valid or force_clean:
            self.clean()
            is_valid = self._is_valid()
        return is_valid

    # Because this function is meant to be used in SignUpView, it doesn't have @transaction.atomic
    # But if you are going to use it somewhere else, you should add it
    def save(self):
        user = self.user.save()
        email_verification = EmailVerificationTable(user=user, token=uuid.uuid4())
        profile = self.profile.save(commit=False)
        profile.user = user
        profile.is_approved = self.is_approved
        profile.save()
        email_verification.save()
        return profile


class TokenVerificationForm(forms.Form):
    token = forms.CharField(
        max_length=100,
        label="Token",
        widget=forms.TextInput(attrs={"class": "form-control"}),
        help_text="Token from email",
    )

    def clean_token(self):
        token = self.cleaned_data["token"]
        if not EmailVerificationTable.objects.filter(token=token).exists():
            raise ValidationError("Invalid token")
        return token

    class Meta:
        model = EmailVerificationTable
        fields = [
            "token",
        ]


# creating a new form because UserForm is a UserCreationForm, which means 'exclude' in Meta or change in
# initialization won't work
class UserEditForm(BootstrapErrorFormMixin, forms.ModelForm):
    first_name = forms.CharField(
        min_length=1,
        max_length=30,
        label="First name",
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    last_name = forms.CharField(
        min_length=1,
        max_length=30,
        label="Last name",
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    email = forms.EmailField(
        max_length=254,
        label="Email address",
        widget=forms.TextInput(attrs={"class": "form-control"}),
        help_text=mark_safe("Email address can not be changed. Please email serve@scilifelab.se with any questions."),
        disabled=True,
    )

    required_css_class = "required"

    class Meta:
        model = User
        fields = [
            "username",
            "first_name",
            "last_name",
            "email",
            "password1",
            "password2",
        ]
        exclude = [
            "username",
            "password1",
            "password2",
        ]

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.data})"


class ProfileEditForm(ProfileForm):
    class Meta(ProfileForm.Meta):
        exclude = [
            "note",
            "why_account_needed",
        ]

    def __init__(self, *args, **kwargs):
        super(ProfileEditForm, self).__init__(*args, **kwargs)
        self.fields["affiliation"].disabled = True
        self.fields[
            "affiliation"
        ].help_text = "Affiliation can not be changed. Please email serve@scilifelab.se with any questions."
