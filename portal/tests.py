from unittest.mock import patch

import pytest
from django.contrib.messages import get_messages
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.backends.db import SessionStore
from django.core import mail
from django.template.response import TemplateResponse
from django.test import Client, RequestFactory, override_settings
from django.urls import reverse

from portal import views
from portal.forms import TeachingRequestForm


@pytest.mark.django_db
def test_index():
    # Get correct request
    request = RequestFactory().get(reverse("portal:apps"))

    # Create session
    s = SessionStore()

    # Add session to request
    request.session = s

    # Get response. Since index is a function, this is the correct way
    response = views.public_apps(request)

    # Check if it returns the correct status code
    assert response.status_code == 200
    assert "<title>Apps and models | SciLifeLab Serve (beta)</title>" in response.content.decode()


@pytest.mark.django_db
def test_home_view_class():
    # Get correct request
    request = RequestFactory().get(reverse("portal:home"))

    # Create session
    s = SessionStore()

    # Add session to request
    request.session = s

    # Get response. Since HomeView is a class, this is the correct way
    response = views.HomeView.as_view()(request)

    # Check status code
    assert response.status_code == 200
    assert "<title>Home | SciLifeLab Serve (beta)</title>" in response.content.decode()


@pytest.mark.django_db
def test_about_view():
    # Get correct request
    request = RequestFactory().get(reverse("portal:about"))
    response = views.about(request)

    # Check status code
    assert response.status_code == 200
    assert "<title>About the platform | SciLifeLab Serve (beta)</title>" in response.content.decode()


@pytest.mark.django_db
def test_teaching_view_get():
    """Test that GET request to teaching view shows the form."""
    # Use Client for proper context access
    client = Client()
    response = client.get(reverse("portal:teaching"))

    # Check status code
    assert response.status_code == 200
    assert "<title>Use in courses | SciLifeLab Serve (beta)</title>" in response.content.decode()

    # Check that form is in context
    assert "form" in response.context
    assert isinstance(response.context["form"], TeachingRequestForm)

    # Check that form fields are rendered
    content = response.content.decode()
    assert "Your name" in content
    assert "Your email address" in content
    assert "course_description" in content


@pytest.mark.django_db
@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
@patch("portal.views.send_email_task")
@patch("portal.forms.AltchaField.clean")
def test_teaching_view_post_valid(mock_altcha_clean, mock_send_email_task):
    """Test that POST with valid data queues the email and redirects."""
    # Mock Altcha validation to return a valid value
    mock_altcha_clean.return_value = "valid_altcha_solution"

    # Prepare valid form data
    form_data = {
        "name": "John Doe",
        "email": "john.doe@example.com",
        "course_title": "Introduction to Python",
        "course_dates": "2024-01-15 to 2024-01-17",
        "course_description": "A comprehensive course on Python programming for beginners.",
        "captcha": "valid_altcha_solution",
    }

    # Create POST request
    request = RequestFactory().post(reverse("portal:teaching"), data=form_data)

    # Create session for messages framework
    s = SessionStore()
    request.session = s
    # Set up messages storage
    messages = FallbackStorage(request)
    request._messages = messages

    response = views.teaching(request)

    # Check that the email task was queued (sending is now off-request)
    mock_send_email_task.delay.assert_called_once()
    call_kwargs = mock_send_email_task.delay.call_args.kwargs

    # Check email content
    assert call_kwargs["subject"] == "New teaching request - SciLifeLab Serve"
    assert "serve@scilifelab.se" in call_kwargs["recipient_list"]
    body = call_kwargs["message"]
    assert "John Doe" in body
    assert "john.doe@example.com" in body
    assert "Introduction to Python" in body
    assert "2024-01-15 to 2024-01-17" in body
    assert "A comprehensive course on Python programming for beginners." in body

    # Check redirect (status 302)
    assert response.status_code == 302
    assert response.url == reverse("portal:teaching")


@pytest.mark.django_db
@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
@patch("portal.views.send_email_task")
@patch("portal.forms.AltchaField.clean")
def test_teaching_view_post_valid_minimal(mock_altcha_clean, mock_send_email_task):
    """Test that POST with minimal required fields queues the email."""
    # Mock Altcha validation to return a valid value
    mock_altcha_clean.return_value = "valid_altcha_solution"

    # Prepare minimal valid form data (only required fields)
    form_data = {
        "name": "Jane Smith",
        "email": "jane.smith@example.com",
        "course_description": "Workshop on data analysis.",
        "captcha": "valid_altcha_solution",
    }

    # Create POST request
    request = RequestFactory().post(reverse("portal:teaching"), data=form_data)

    # Create session for messages framework
    s = SessionStore()
    request.session = s
    # Set up messages storage
    messages = FallbackStorage(request)
    request._messages = messages

    views.teaching(request)

    # Check that the email task was queued
    mock_send_email_task.delay.assert_called_once()
    body = mock_send_email_task.delay.call_args.kwargs["message"]

    # Check email content
    assert "Jane Smith" in body
    assert "jane.smith@example.com" in body
    assert "Not provided" in body  # For optional fields
    assert "Workshop on data analysis." in body


@pytest.mark.django_db
def test_teaching_view_post_invalid():
    """Test that POST with invalid data shows form errors."""
    # Prepare invalid form data (missing required fields)
    form_data = {
        "name": "",  # Missing required field
        "email": "invalid-email",  # Invalid email format
        "course_description": "",  # Missing required field
    }

    # Use Client for proper context access
    client = Client()
    response = client.post(reverse("portal:teaching"), data=form_data)

    # Check that form is returned with errors (status 200, not redirect)
    assert response.status_code == 200

    # Check that form is in context
    assert "form" in response.context
    form = response.context["form"]
    assert not form.is_valid()

    # Check that errors are present
    assert "name" in form.errors
    assert "email" in form.errors
    assert "course_description" in form.errors

    # Check that no email was sent
    assert len(mail.outbox) == 0


@pytest.mark.django_db
@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
@patch("portal.views.send_email_task")
@patch("portal.forms.AltchaField.clean")
def test_teaching_view_email_content_format(mock_altcha_clean, mock_send_email_task):
    """Test that email content is properly formatted."""
    # Mock Altcha validation to return a valid value
    mock_altcha_clean.return_value = "valid_altcha_solution"

    form_data = {
        "name": "Test User",
        "email": "test@example.com",
        "course_title": "Test Course",
        "course_dates": "2024-02-01",
        "course_description": "Test description with multiple lines.\nLine 2.\nLine 3.",
        "captcha": "valid_altcha_solution",
    }

    request = RequestFactory().post(reverse("portal:teaching"), data=form_data)
    s = SessionStore()
    request.session = s
    # Set up messages storage
    messages = FallbackStorage(request)
    request._messages = messages

    views.teaching(request)

    # Check the email task was queued
    mock_send_email_task.delay.assert_called_once()
    body = mock_send_email_task.delay.call_args.kwargs["message"]

    # Check email structure
    assert "A new teaching request has been submitted:" in body
    assert "Name: Test User" in body
    assert "Email: test@example.com" in body
    assert "Course/Workshop/Webinar Title: Test Course" in body
    assert "Date(s) and Time(s): 2024-02-01" in body
    assert "Description:" in body
    assert "Test description with multiple lines." in body
    assert "This email was sent from the SciLifeLab Serve teaching request form." in body


@pytest.mark.django_db
@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="serve@scilifelab.se",
    EMAIL_FROM="noreply-serve@scilifelab.se",
)
@patch("portal.views.send_email_task")
@patch("portal.forms.AltchaField.clean")
def test_teaching_view_email_recipient(mock_altcha_clean, mock_send_email_task):
    """Test that email is sent to ADMIN_EMAIL from EMAIL_FROM."""
    # Mock Altcha validation to return a valid value
    mock_altcha_clean.return_value = "valid_altcha_solution"

    form_data = {
        "name": "Test User",
        "email": "test@example.com",
        "course_description": "Test description",
        "captcha": "valid_altcha_solution",
    }

    request = RequestFactory().post(reverse("portal:teaching"), data=form_data)
    s = SessionStore()
    request.session = s
    # Set up messages storage
    messages = FallbackStorage(request)
    request._messages = messages

    views.teaching(request)

    # Check email recipient and sender passed to the queued task
    mock_send_email_task.delay.assert_called_once()
    call_kwargs = mock_send_email_task.delay.call_args.kwargs
    assert "serve@scilifelab.se" in call_kwargs["recipient_list"]
    assert call_kwargs["from_email"] == "noreply-serve@scilifelab.se"


@pytest.mark.django_db
@patch("portal.forms.AltchaField.clean")
def test_teaching_form_validation(mock_altcha_clean):
    """Test TeachingRequestForm validation."""
    # Mock Altcha validation to return a valid value
    mock_altcha_clean.return_value = "valid_altcha_solution"

    # Test valid form
    valid_data = {
        "name": "John Doe",
        "email": "john@example.com",
        "course_description": "Test course",
        "captcha": "valid_altcha_solution",
    }
    form = TeachingRequestForm(data=valid_data)
    assert form.is_valid()

    # Test missing required fields
    invalid_data = {
        "name": "",
        "email": "",
        "course_description": "",
        "captcha": "valid_altcha_solution",
    }
    form = TeachingRequestForm(data=invalid_data)
    assert not form.is_valid()
    assert "name" in form.errors
    assert "email" in form.errors
    assert "course_description" in form.errors

    # Test invalid email
    invalid_email_data = {
        "name": "John Doe",
        "email": "not-an-email",
        "course_description": "Test course",
        "captcha": "valid_altcha_solution",
    }
    form = TeachingRequestForm(data=invalid_email_data)
    assert not form.is_valid()
    assert "email" in form.errors

    # Test optional fields can be empty
    minimal_data = {
        "name": "John Doe",
        "email": "john@example.com",
        "course_title": "",
        "course_dates": "",
        "course_description": "Test course",
        "captcha": "valid_altcha_solution",
    }
    form = TeachingRequestForm(data=minimal_data)
    assert form.is_valid()

    # Test missing captcha
    from django.core.exceptions import ValidationError

    mock_altcha_clean.side_effect = ValidationError("Invalid Altcha solution")
    no_captcha_data = {
        "name": "John Doe",
        "email": "john@example.com",
        "course_description": "Test course",
    }
    form = TeachingRequestForm(data=no_captcha_data)
    assert not form.is_valid()
    assert "captcha" in form.errors


@pytest.mark.django_db
@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
@patch("portal.forms.AltchaField.clean")
def test_teaching_view_email_sending_error(mock_altcha_clean):
    """Test error handling when queuing the email task fails."""
    # Mock Altcha validation to return a valid value
    mock_altcha_clean.return_value = "valid_altcha_solution"

    form_data = {
        "name": "Test User",
        "email": "test@example.com",
        "course_description": "Test description",
        "captcha": "valid_altcha_solution",
    }

    # Mock the email task enqueue to raise (e.g. broker unavailable)
    with patch("portal.views.send_email_task") as mock_send_email_task:
        mock_send_email_task.delay.side_effect = Exception("Broker unavailable")

        request = RequestFactory().post(reverse("portal:teaching"), data=form_data)
        s = SessionStore()
        request.session = s
        # Set up messages storage
        messages = FallbackStorage(request)
        request._messages = messages

        response = views.teaching(request)

        # Check that the error path is taken (response should be 200, not redirect)
        assert response.status_code == 200

        # Verify the task enqueue was attempted
        mock_send_email_task.delay.assert_called_once()


@pytest.mark.django_db
@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
@patch("portal.views.send_email_task")
@patch("portal.forms.AltchaField.clean")
def test_teaching_view_success_message(mock_altcha_clean, mock_send_email_task):
    """Test that success message is displayed after successful submission."""
    # Mock Altcha validation to return a valid value
    mock_altcha_clean.return_value = "valid_altcha_solution"

    # Use Django Client for proper message handling
    client = Client()

    form_data = {
        "name": "Test User",
        "email": "test@example.com",
        "course_description": "Test description",
        "captcha": "valid_altcha_solution",
    }

    response = client.post(reverse("portal:teaching"), data=form_data, follow=True)

    # Check redirect happened
    assert response.status_code == 200

    # Email is queued off-request
    mock_send_email_task.delay.assert_called_once()

    # Check for success message in response
    messages = list(get_messages(response.wsgi_request))
    assert len(messages) == 1
    assert "success" in str(messages[0].tags)
    assert "submitted successfully" in str(messages[0])


@pytest.mark.django_db
@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
@patch("portal.forms.AltchaField.clean")
def test_teaching_view_form_field_max_length(mock_altcha_clean):
    """Test that form respects max_length constraints."""
    # Mock Altcha validation to return a valid value
    mock_altcha_clean.return_value = "valid_altcha_solution"

    # Test name field max_length
    form_data = {
        "name": "A" * 201,  # Exceeds max_length of 200
        "email": "test@example.com",
        "course_description": "Test description",
        "captcha": "valid_altcha_solution",
    }
    form = TeachingRequestForm(data=form_data)
    assert not form.is_valid()
    assert "name" in form.errors

    # Test email field max_length
    form_data = {
        "name": "Test User",
        "email": "a" * 250 + "@example.com",  # Exceeds max_length of 254
        "course_description": "Test description",
        "captcha": "valid_altcha_solution",
    }
    form = TeachingRequestForm(data=form_data)
    assert not form.is_valid()
    assert "email" in form.errors

    # Test valid max_length
    form_data = {
        "name": "A" * 200,  # Exactly max_length
        "email": "a" * 240 + "@example.com",  # Within max_length
        "course_description": "Test description",
        "captcha": "valid_altcha_solution",
    }
    form = TeachingRequestForm(data=form_data)
    assert form.is_valid()


@pytest.mark.django_db
def test_privacy_view():
    # Get correct request
    request = RequestFactory().get(reverse("portal:privacy"))
    response = views.privacy(request)

    # Check status code
    assert response.status_code == 200
    assert "<title>Privacy policy | SciLifeLab Serve (beta)</title>" in response.content.decode()


@pytest.mark.django_db
def test_roadmap_view():
    client = Client()
    response = client.get(reverse("portal:roadmap"))
    assert response.status_code == 200
    assert "<title>Roadmap | SciLifeLab Serve (beta)</title>" in response.content.decode()


@pytest.mark.django_db
def test_cite_view():
    client = Client()
    response = client.get(reverse("portal:cite"))
    assert response.status_code == 200
    assert "<title>Citing us | SciLifeLab Serve (beta)</title>" in response.content.decode()


@pytest.mark.django_db
def test_contact_view():
    client = Client()
    response = client.get(reverse("portal:contact"))
    assert response.status_code == 200
    assert "<title>Contact us | SciLifeLab Serve (beta)</title>" in response.content.decode()


@pytest.mark.django_db
def test_collections_index_view():
    client = Client()
    response = client.get(reverse("portal:collections_index"))
    assert response.status_code == 200
    assert "<title>Collections | SciLifeLab Serve (beta)</title>" in response.content.decode()


@pytest.mark.django_db
def test_events_view():
    client = Client()
    response = client.get(reverse("portal:events"))
    assert response.status_code == 200
    assert "<title>Events | SciLifeLab Serve (beta)</title>" in response.content.decode()


@pytest.mark.django_db
def test_events_rss_view():
    client = Client()
    response = client.get(reverse("portal:events-rss"))
    assert response.status_code == 200
    assert response["Content-Type"] == "application/rss+xml; charset=utf-8"


@pytest.mark.django_db
def test_news_view():
    client = Client()
    response = client.get(reverse("portal:news"))
    assert response.status_code == 200
    assert "<title>Platform news | SciLifeLab Serve (beta)</title>" in response.content.decode()


@pytest.mark.django_db
def test_news_rss_view():
    client = Client()
    response = client.get(reverse("portal:news-rss"))
    assert response.status_code == 200
    assert response["Content-Type"] == "application/rss+xml; charset=utf-8"
