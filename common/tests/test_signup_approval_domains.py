import json
import re

import pytest
from django.urls import reverse

from common.forms import EMAIL_ALLOW_REGEX, ProfileForm, SignUpForm, UserForm


@pytest.mark.django_db
@pytest.mark.parametrize(
    "domain, approved",
    [
        ("uu.se", True),
        ("department.uu.se", True),
        ("scilifelab.se", True),
        ("student.uu.se", False),
        ("stud.uu.se", False),
        ("scilifelab.se.example.com", False),
        ("uu.se.example.com", False),
        ("example.com", False),
    ],
)
def test_signup_approval_requires_an_approved_domain(domain, approved):
    email = f"researcher@{domain}"
    user_form = UserForm(
        {
            "username": email,
            "first_name": "Test",
            "last_name": "Researcher",
            "email": email,
            "password1": "V3ryLongUniquePassword!",
            "password2": "V3ryLongUniquePassword!",
        }
    )
    profile_form = ProfileForm(
        {
            "affiliations-data": json.dumps([{"title": "Test institution", "ror_id": "no ror"}]),
        }
    )

    signup_form = SignUpForm(user=user_form, profile=profile_form)
    assert signup_form.is_valid() is approved
    assert signup_form.is_approved is approved


@pytest.mark.django_db
def test_signup_page_uses_the_server_approval_pattern(client):
    response = client.get(reverse("common:signup"))

    assert response.status_code == 200
    match = re.search(
        rb'<script id="approved-email-domain-pattern" type="application/json">(.*?)</script>',
        response.content,
    )
    assert match is not None
    assert json.loads(match.group(1)) == EMAIL_ALLOW_REGEX.pattern
