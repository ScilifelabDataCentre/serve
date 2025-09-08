import datetime
import json
import unicodedata
from random import choice

import pytest
from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import User
from django.core import mail
from django.http import HttpRequest
from django.test import Client, override_settings
from hypothesis import Verbosity, given, settings
from hypothesis import strategies as st
from hypothesis.extra.django import TestCase, TransactionTestCase

from common.forms import (
    DEPARTMENTS,
    EMAIL_ALLOW_REGEX,
    UNIVERSITIES,
    ProfileEditForm,
    ProfileForm,
    SignUpForm,
    TokenVerificationForm,
    UserEditForm,
    UserForm,
)
from common.models import EmailVerificationTable, UserProfile
from common.views import VerificationTokenResetView


def get_affilitaion(email):
    return email.split("@")[1].split(".")[-2].lower()


@st.composite
def input_form(
    draw,
    email=st.emails(domains=st.from_regex(EMAIL_ALLOW_REGEX, fullmatch=True)),
    name=st.text(min_size=3, max_size=20),
    surname=st.text(min_size=3, max_size=20),
    affiliation_getter=get_affilitaion,
    why_account_needed=st.text(min_size=10, max_size=100),
    department=st.sampled_from(DEPARTMENTS),
):
    mail = draw(email)
    pwd = draw(st.text(min_size=8).map(make_password))
    department = draw(department)
    affiliation = affiliation_getter(mail)
    name_ = unicodedata.normalize("NFKD", draw(name).replace("\x00", "\uFFFD"))
    surname_ = unicodedata.normalize("NFKD", draw(surname).replace("\x00", "\uFFFD"))
    why_account_needed = draw(why_account_needed)
    if why_account_needed is not None:
        why_account_needed = unicodedata.normalize("NFKD", why_account_needed.replace("\x00", "\uFFFD"))

    user_form = UserForm(
        {
            "first_name": name_,
            "last_name": surname_,
            "email": mail,
            "password1": pwd,
            "password2": pwd,
            "username": mail,
        }
    )

    profile_form = ProfileForm(
        {
            "why_account_needed": why_account_needed,
            "department": department,
            "affiliation": affiliation,
        }
    )

    form = SignUpForm(user=user_form, profile=profile_form)
    return form


# Override the INACTIVE_USERS setting for this test case
# This results in users being inactive after registration
@override_settings(INACTIVE_USERS=True)
class TestSignUp(TransactionTestCase):
    # Using hypothesis for generating test cases with input_form
    @given(form=input_form())
    @settings(verbosity=Verbosity.verbose, max_examples=1, deadline=None)  # Configure hypothesis settings
    def test_pass_validation(self, form):
        # Check if the form is valid
        # is_val call implicitly calls the form's clean methods, which populates the cleaned_data attribute
        is_val = form.is_valid()

        # Assert that the user and profile forms have cleaned_data attribute.
        # It means that the clean methods were called
        assert hasattr(form.user, "cleaned_data")
        assert hasattr(form.profile, "cleaned_data")

        # Assert that the form is valid; if not, show form errors
        assert is_val, (form.user.errors, form.profile.errors)

        # Save the form and obtain the profile instance
        profile = form.save()

        # Check if the username is the same as the email, which is a common pattern
        assert profile.user.username == profile.user.email

        # Verify that an email has been sent
        assert mail.outbox[0].subject == "Verify your email address on SciLifeLab Serve"
        assert mail.outbox[0].to == [profile.user.email]  # Check if the email is sent to the user's email

        # Check if an entry in EmailVerificationTable exists for the user
        assert EmailVerificationTable.objects.filter(user=profile.user).exists()

        # Retrieve the token from EmailVerificationTable and check if it's in the email body
        token = EmailVerificationTable.objects.get(user=profile.user).token
        assert token in mail.outbox[0].body


@override_settings(INACTIVE_USERS=True)
class TestEmailSending(TransactionTestCase):
    # Use hypothesis for property-based testing
    @given(form=input_form())
    @settings(verbosity=Verbosity.verbose, max_examples=1, deadline=None)  # Set Hypothesis test settings
    def test_email_verification_email_not_from_university(self, form):
        # Check if the form is valid
        # is_val call implicitly calls the form's clean methods, which populates the cleaned_data attribute
        is_val = form.is_valid()

        # Assert that the user and profile forms have cleaned_data attribute.
        # It means that the clean methods were called
        assert hasattr(form.user, "cleaned_data")
        assert hasattr(form.profile, "cleaned_data")

        # Assert form is valid; if not, show form errors
        assert is_val, (form.user.errors, form.profile.errors)

        # Explicitly set form approval to False
        # This is required, because emails that are being generated are from university,
        # which sets the form to approved
        # But we need to test the case when the email is not from university,
        # which is essentially when is_approved is False
        form.is_approved = False
        form.save()  # Save the form changes

        # Retrieve the user object based on the email from the form's cleaned data
        user = User.objects.get(email=form.user.cleaned_data["email"])

        # Retrieve the token for the user from EmailVerificationTable
        token = EmailVerificationTable.objects.get(user=user.id).token
        assert token in mail.outbox[0].body  # Check if the token is in the first sent email

        # Simulate a POST request to the verification URL with the token
        resp = self.client.post("/verify/", {"token": token})
        assert resp.status_code == 302  # Check if the response is a redirect (status code 302)

        # Assert that the second email sent contains the specific activation message
        assert f"Please go to the admin page to activate account for {user.email}" in mail.outbox[1].body


@override_settings(INACTIVE_USERS=True)
class TestAccountVerification(TestCase):
    # Use hypothesis for property-based testing
    @given(form=input_form())
    @settings(verbosity=Verbosity.verbose, max_examples=1, deadline=None)  # Set Hypothesis test settings
    def test_send_email_after_token_expired(self, form):
        # setup
        # is_val call implicitly calls the form's clean methods, which populates the cleaned_data attribute
        form.is_valid()

        # Explicitly set form approval to False
        # This is required, because emails that are being generated are from university,
        # which sets the form to approved
        form.is_approved = False
        form.save()  # Save the form changes

        # Retrieve the user object based on the email from the form's cleaned data
        user = User.objects.get(email=form.user.cleaned_data["email"])
        email_verification_table: EmailVerificationTable = EmailVerificationTable.objects.get(user=user.id)
        # set date to initial commit to serve:)
        very_old_date = datetime.datetime(2020, 4, 8, 21, 34)
        old_token = email_verification_table.token
        email_verification_table.date_created = very_old_date
        email_verification_table.save()

        # actual test case
        verification_form = TokenVerificationForm({"token": email_verification_table.token})
        assert not verification_form.is_valid()

        errors = verification_form.errors

        assert "Token has expired. Please request a new one." in errors["token"]

        # Send email with a new token
        VerificationTokenResetView.reset_token(user.email)
        email_verification_table = EmailVerificationTable.objects.get(user=user.id)
        assert email_verification_table.date_created != very_old_date
        assert email_verification_table.token != old_token
        assert email_verification_table.token in mail.outbox[1].body


@pytest.mark.django_db
@given(
    form=input_form(
        email=st.emails().filter(lambda x: get_affilitaion(x) not in [unis[0] for unis in UNIVERSITIES]),
        affiliation_getter=lambda x: "other",
        why_account_needed=st.text(min_size=10, max_size=100),
    )
)
@settings(verbosity=Verbosity.verbose, max_examples=1)
def test_pass_validation_other_email_request_account(form):
    is_val = form.is_valid()
    assert hasattr(form.user, "cleaned_data")
    assert hasattr(form.profile, "cleaned_data")
    assert is_val, form.user.errors


@pytest.mark.django_db
@given(
    form=input_form(
        affiliation_getter=lambda x: choice(
            [unis[0] for unis in UNIVERSITIES if unis[0] not in (get_affilitaion(x), "other")]
        )
    )
)
@settings(verbosity=Verbosity.verbose, max_examples=1)
def test_invalid_input_affiliation_ne_email(form):
    is_val = form.is_valid()
    assert hasattr(form.user, "cleaned_data")
    assert hasattr(form.profile, "cleaned_data")
    assert not is_val
    assert {"affiliation": ["Email affiliation is different from selected university"]} == form.profile.errors


@pytest.mark.django_db
@given(form=input_form(affiliation_getter=lambda x: "other"))
@settings(verbosity=Verbosity.verbose, max_examples=1)
def test_invalid_input_affilitaion_is_other(form):
    is_val = form.is_valid()
    assert hasattr(form.user, "cleaned_data")
    assert hasattr(form.profile, "cleaned_data")
    assert not is_val
    assert {"affiliation": ["You are required to select a university affiliation"]} == form.profile.errors


@pytest.mark.django_db
@given(form=input_form(department=st.sampled_from(["", None])))
@settings(verbosity=Verbosity.verbose, max_examples=1)
def test_invalid_input_department_is_empty(form):
    is_val = form.is_valid()
    assert hasattr(form.profile, "cleaned_data")
    assert not is_val
    assert {"department": ["You are required to select your department"]} == form.profile.errors


@pytest.mark.django_db
@given(
    form=input_form(
        email=st.emails().filter(lambda x: get_affilitaion(x) not in [unis[0] for unis in UNIVERSITIES]),
        affiliation_getter=lambda x: "other",
        why_account_needed=st.sampled_from(["", None]),
    )
)
@settings(verbosity=Verbosity.verbose, max_examples=1)
def test_fail_validation_other_email_request_account_field_empty(form):
    is_val = form.is_valid()
    assert not is_val, (form.user.errors, form.profile.errors)
    assert {"why_account_needed": ["Please describe why you need an account"]} == form.profile.errors


@pytest.mark.django_db
@given(
    form=input_form(
        email=st.emails().filter(lambda x: get_affilitaion(x) not in [unis[0] for unis in UNIVERSITIES]),
        affiliation_getter=lambda x: choice([unis[0] for unis in UNIVERSITIES if unis[0] != "other"]),
    )
)
@settings(verbosity=Verbosity.verbose, max_examples=1)
def test_fail_validation_other_email_affiliation_selected(form):
    is_val = form.is_valid()
    assert not is_val, (form.user.errors, form.profile.errors)
    assert {
        "email": [
            "Email was not recognized as a researcher email from a Swedish university. \n"
            "Please select 'Other' in affiliation or use your Swedish university researcher email."
        ]
    } == form.user.errors


@pytest.mark.parametrize(
    "first_name, last_name",
    [
        ("abc", "xyz"),
        ("122124", "57457458"),
        ("/&)(&(/))", "@#€%€%&"),
    ],
)
def test_pass_validation_user_edit_form(first_name, last_name):
    request = HttpRequest()
    request.POST = {
        "first_name": first_name,
        "last_name": last_name,
    }
    form = UserEditForm(request.POST, instance=UserProfile(), initial={"email": "a@uu.se"})
    assert form.is_valid()


@pytest.mark.parametrize(
    "first_name, last_name",
    [
        ("", "xyz"),
        ("abc", ""),
        ("", ""),
        ("   ", "   "),
        (None, ""),
        ("", None),
        (None, None),
    ],
)
def test_fail_validation_user_edit_form(first_name, last_name):
    request = HttpRequest()
    request.POST = {"first_name": first_name, "last_name": last_name}
    form = UserEditForm(request.POST, instance=UserProfile(), initial={"email": "a@uu.se"})
    assert not form.is_valid()


@pytest.mark.parametrize(
    "department",
    [
        ("abc"),
        ("122445"),
        ("@#%&&"),
        (""),
        ("  "),
        (None),
    ],
)
def test_pass_validation_profile_edit_form(department):
    request = HttpRequest()
    request.POST = {
        "department": department,
    }
    form = ProfileEditForm(
        request.POST,
        instance=UserProfile(),
        initial={
            "affiliation": "uu",
        },
    )
    assert form.is_valid()
