import json
import re
import uuid
from dataclasses import dataclass
from typing import Any, Dict, Optional, Sequence

from django import forms
from django.conf import settings
from django.contrib.auth.forms import PasswordChangeForm, UserCreationForm
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import (
    get_password_validators,
    password_validators_help_texts,
)
from django.core.exceptions import ValidationError
from django.core.validators import EmailValidator
from django.db import transaction
from django.utils import timezone
from django.utils.html import format_html
from django.utils.safestring import mark_safe

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


# Custom helptext for password validators used in signup and change password forms
def password_validators_help_text_html(
    password_validators=get_password_validators(settings.AUTH_PASSWORD_VALIDATORS),
):
    """
    Return an HTML string with all help texts of all configured validators
    in an <ul>.
    """
    help_texts = []
    for validator, settings_validator in zip(password_validators, settings.AUTH_PASSWORD_VALIDATORS):
        help_texts.append(
            {
                "help_text": password_validators_help_texts([validator]),
                "validator": settings_validator["NAME"].split(".")[-1],
                "name": settings_validator["NAME"],
            }
        )
    help_texts.append(
        {"help_text": ["Your passwords should match"], "validator": "PasswordMatch", "name": "PasswordMatch"}
    )
    help_items = [
        format_html(
            """<li class='d-flex requirements text-muted {}'><i class='bi bi-check text-success me-2'>
            </i><i class='bi bi-x text-danger me-2'></i>{}</li>""",
            help_text["validator"],
            help_text["help_text"][0],
        )
        for help_text in help_texts
    ]
    return '<ul class="list-unstyled mb-0" id="password_alert">%s</ul>' % "".join(help_items) if help_items else ""


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
            # Skip non-field errors (__all__) — they don't have a widget
            if field_name == "__all__":
                continue
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
    )
    password1 = forms.CharField(
        min_length=10,
        label="Password",
        widget=forms.PasswordInput(attrs={"class": "form-control", "aria-describedby": "password_requirements"}),
        help_text=mark_safe(password_validators_help_text_html()),
    )
    password2 = forms.CharField(
        min_length=10,
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
    # REMOVED: organization and department fields
    # These are now handled by JS dynamic rows + hidden affiliations-data input in template
    """
    organization = forms.CharField(
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "id": "organization-autocomplete",
                "placeholder": "Start typing organization name...",
                "autocomplete": "off",
            }
        ),
        label="Organization",
        help_text="Start typing to select your organization via ROR (Research Organization Registry).",
    )
    department = forms.CharField(
        widget=ListTextWidget(data_list=DEPARTMENTS, name="department-list", attrs={"class": "form-control"}),
        label="Department",
        required=False,
        help_text="Select closest department name or enter your own.",
    )
    """
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
            # organization and department removed — managed via affiliations-data hidden input
            # "organization",
            # "department",
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
    organization_data: Optional[Dict[str, Any]] = None

    def clean(self) -> None:
        user_data = self.user.cleaned_data
        profile_data = self.profile.cleaned_data

        email = user_data.get("email", "")
        why_account_needed = profile_data.get("why_account_needed")

        is_university_email = EMAIL_ALLOW_REGEX.match(email.split("@")[1]) is not None

        is_request_account_empty = not bool(why_account_needed)

        self.is_approved = is_university_email

        # --- Parse affiliations-data from POST (replaces organization-data) ---
        affiliations_data_str = self.profile.data.get("affiliations-data", "")
        affiliations_list = []

        if affiliations_data_str:
            try:
                affiliations_list = json.loads(affiliations_data_str)
            except json.JSONDecodeError as e:
                logger.debug(f"JSONDecodeError parsing affiliations-data: {e}")
                affiliations_list = []

        # Ensure it's a list
        if not isinstance(affiliations_list, list):
            affiliations_list = []

        # Filter out empty entries (no title)
        affiliations_list = [aff for aff in affiliations_list if isinstance(aff, dict) and aff.get("title", "").strip()]

        # Validation: at least one affiliation required
        if not affiliations_list:
            self.profile.add_error(
                None,  # Non-field error since org field no longer exists on form
                ValidationError("At least one affiliation is required."),
            )

        # ROR validation is SOFT — no error added for missing/invalid ror_id.
        # Affiliations with "no ror" or empty ror_id are accepted as-is.

        if not is_university_email and is_request_account_empty:
            self.profile.add_error(
                "why_account_needed",
                ValidationError("Please describe why you need an account"),
            )

        self.affiliations_data = affiliations_list

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

        # Write new affiliations field
        profile.affiliations = self.affiliations_data if self.affiliations_data else []

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
        try:
            db_token: EmailVerificationTable = EmailVerificationTable.objects.get(token=token)
            if (timezone.now() - db_token.date_created).days > 3:
                raise ValidationError("Token has expired. Please request a new one.")
        except EmailVerificationTable.DoesNotExist:
            raise ValidationError("Invalid token")
        return token

    class Meta:
        model = EmailVerificationTable
        fields = [
            "token",
        ]


class RequestNewVerificationForm(forms.Form):
    email = forms.EmailField(
        label="Email",
        widget=forms.TextInput(attrs={"class": "form-control"}),
        help_text="Enter email you've used to sign up on Serve",
    )


# SS-643 We've created a new form because UserForm above
# is a UserCreationForm,
# which means 'exclude' in Meta or change in
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


class ChangePasswordForm(BootstrapErrorFormMixin, PasswordChangeForm):
    old_password = forms.CharField(
        min_length=10,
        label="Old Password",
        widget=forms.PasswordInput(attrs={"class": "form-control"}),
    )
    new_password1 = forms.CharField(
        min_length=10,
        label="New Password",
        widget=forms.PasswordInput(attrs={"class": "form-control", "aria-describedby": "password_requirements"}),
        help_text=mark_safe(password_validators_help_text_html()),
    )
    new_password2 = forms.CharField(
        min_length=10,
        label="Confirm password",
        widget=forms.PasswordInput(attrs={"class": "form-control"}),
    )
    required_css_class = "required"

    class Meta:
        model = User

    def add_error_classes(self) -> None:
        """
        Add bootstrap error classes to fields and move errors from new_password2 to new_password1
        so that errors are displayed in one place on the left side of the form
        """
        super().add_error_classes()
        if "new_password1" in self.errors or "new_password2" in self.errors:
            self.fields["new_password1"].widget.attrs.update({"class": "form-control is-invalid"})
            self.fields["new_password2"].widget.attrs.update({"class": "form-control is-invalid"})
            errors_p1 = self.errors.get("new_password1", [])
            self.errors["new_password1"] = errors_p1 + self.errors.get("new_password2", [])
            if "new_password2" in self.errors:
                del self.errors["new_password2"]


class ProfileEditForm(ProfileForm):
    class Meta(ProfileForm.Meta):
        exclude = [
            "note",
            "why_account_needed",
        ]

    # REMOVED: __init__ that pre-populated organization from JSON
    # Pre-population now happens via affiliations-data hidden input in template
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Pre-populate organization field with title from JSON
        if self.instance and self.instance.organization:
            org_data = self.instance.organization
            if isinstance(org_data, dict):
                self.initial["organization"] = org_data.get("title", "")
    """
