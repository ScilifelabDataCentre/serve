import json
import re

import pytest
from django.urls import reverse

from common.forms import (
    EMAIL_ALLOW_REGEX,
    UNIVERSITIES,
    ProfileForm,
    SignUpForm,
    UserForm,
    approved_email_domains,
)


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
        ("newinstitute.se", False),
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


@pytest.mark.parametrize("new_organization", [{"name": "New Institute"}, "New Institute"])
def test_new_affiliation_does_not_approve_email_without_opt_in(new_organization):
    organizations = [*UNIVERSITIES, ("newinstitute", new_organization)]

    assert "newinstitute.se" not in approved_email_domains(organizations)
