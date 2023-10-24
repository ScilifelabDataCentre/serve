import json
import re
from dataclasses import dataclass
from typing import Optional, Sequence

from django import forms
from django.conf import settings
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.validators import EmailValidator
from django.db import transaction
from django.utils.safestring import mark_safe

from common.models import UserProfile

with open(settings.STATICFILES_DIRS[0] + "/common/departments.json", "r") as f:
    DEPARTMENTS = json.load(f).get("departments", [])

with open(settings.STATICFILES_DIRS[0] + "/common/universities.json", "r") as f:
    UNIVERSITIES = json.load(f).get("universities", dict())
    UNIVERSITIES = [(k, v) for k, v in UNIVERSITIES.items()]


# Regex for validating email domain
# Same regexp could be found in templates/registration/signup.html
EMAIL_ALLOW_REGEX = re.compile(
    (
        r"^(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)*?"  # Subdomain part
        + f"({('|').join([l[0] for l in UNIVERSITIES if l[0] != 'other'])}"
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
        label=False,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "First name*"}),
    )
    last_name = forms.CharField(
        min_length=1,
        max_length=30,
        label=False,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Last name*"}),
    )
    email = forms.EmailField(
        max_length=254,
        label=mark_safe(
            "Use your <a "
            "href='https://www.uka.se/sa-fungerar-hogskolan/universitet-och-hogskolor/lista-over-"
            "universitet-hogskolor-och-enskilda-utbildningsanordnare'>"
            "swedish university</a> email address or submit your request for evaluation."
        ),
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Email*"}),
        label_suffix="",
    )
    password1 = forms.CharField(
        min_length=8,
        label=False,
        widget=forms.PasswordInput(attrs={"class": "form-control", "placeholder": "Password*"}),
    )
    password2 = forms.CharField(
        min_length=8,
        label=False,
        widget=forms.PasswordInput(attrs={"class": "form-control", "placeholder": "Confirm password*"}),
    )

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

    def clean_email(self) -> str:
        """
        Validate that the supplied email address is unique.

        This runs after the basic `UserCreationForm` validation.
        """
        email: str = self.cleaned_data["email"].lower()
        if User.objects.filter(email=email).exists():
            self.add_error("email", ValidationError("Email already exists"))
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
        widget=forms.Select(attrs={"class": "form-control", "placeholder": "University"}),
        label="University affiliation",
        choices=UNIVERSITIES,
        label_suffix="",
    )
    department = forms.CharField(
        widget=ListTextWidget(
            data_list=DEPARTMENTS, name="department-list", attrs={"class": "form-control", "placeholder": "Department"}
        ),
        label="Select closest department name or enter your own",
        label_suffix="",
        required=False,
    )
    why_account_needed = forms.CharField(
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "placeholder": "Because you are not using Swedish University email, please describe why do you need "
                "an account.\nYour request will be submited for evaluation.*",
                "style": "height: 70px",
            }
        ),
        required=False,
    )
    note = forms.CharField(
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "placeholder": (
                    "If you would like us to get in touch with you, to answer your questions or provide "
                    "help with Serve, please describe what do you need here"
                ),
                "style": "height: 70px",
            }
        ),
        required=False,
    )

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
                self.profile.add_error("affiliation", ValidationError("Email affiliation is different from selected"))
            if not is_affiliated:
                self.profile.add_error("affiliation", ValidationError("You are required to select your affiliation"))
            if is_department_empty:
                self.profile.add_error("department", ValidationError("You are required to select your department"))
        else:
            if is_affiliated:
                self.user.add_error(
                    "email",
                    ValidationError(
                        "Email is not from Swedish University. \n"
                        "Please select 'Other' in affiliation or use your University email"
                    ),
                )
                self.profile.add_error("affiliation", ValidationError(""))

            if is_request_account_empty:
                self.profile.add_error(
                    "why_account_needed", ValidationError("Please describe why do you need an account")
                )

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
        profile = self.profile.save(commit=False)
        profile.user = user
        profile.is_approved = self.is_approved
        profile.save()
        return profile
