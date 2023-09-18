import pytest
from django.test import TestCase
from django.core.exceptions import ValidationError
from django import forms
from hypothesis import given, settings, Verbosity, strategies as st
from hypothesis.extra.django import from_field

from common.forms import SignUpForm, EMAIL_ALLOW_REGEX

@given(email=from_field(forms.EmailField()))
def test_raise_not_swedish_university_email_validation(email):
    form = SignUpForm(
        {
            "username": "test",
            "first_name": "test",
            "last_name": "test",
            "email": "noname@xyz.se",
            "password1": "test",
            "password2": "test",
        }
    )
    form.cleaned_data = {"email": email}
    form.clean("email")
    with pytest.raises(ValidationError):
        form.clean_email()


@given(email=st.from_regex(EMAIL_ALLOW_REGEX))
def test_pass_swedish_university_email_validation(email):
    form = SignUpForm(
        {
            "username": "test",
            "first_name": "test",
            "last_name": "test",
            "email": email,
            "password1": "test",
            "password2": "test",
        }
    )
    form.cleaned_data = {"email": email}
    form.clean_email()

