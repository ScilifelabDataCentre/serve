import pytest
from django.contrib.auth.models import User
from django.core import mail
from django.core.mail.message import EmailMultiAlternatives
from django.test import Client, override_settings
from django.urls import reverse

from common.models import EmailSendingTable
from common.tasks import send_email_task


@pytest.mark.django_db
def test_render_email_bodies_manual_message_strips_plaintext():
    user = User.objects.create_user(username="u1", email="u1@example.com", password="pw", first_name="Alice")

    instance = EmailSendingTable(
        to_user=user,
        to_email=user.email,
        subject="Hello",
        message="<p>Hello <strong>world</strong></p><p>Next line</p>",
        template=None,
    )

    plain, html = instance.render_email_bodies()
    assert html is not None
    assert "<strong>world</strong>" in html
    assert "Hello world\n\nNext line" == plain


@pytest.mark.django_db
def test_render_email_bodies_plaintext_does_not_concatenate_paragraphs():
    user = User.objects.create_user(username="u1b", email="u1b@example.com", password="pw", first_name="Alice")

    instance = EmailSendingTable(
        to_user=user,
        to_email=user.email,
        subject="Hello",
        message="<p>Dear X,</p><p>Here is some test email.</p><p>Kind regards,</p>",
        template=None,
    )

    plain, _html = instance.render_email_bodies()
    assert "Dear X,\n\nHere is some test email.\n\nKind regards," == plain


@pytest.mark.django_db
def test_render_email_bodies_template_renders_and_strips_plaintext():
    user = User.objects.create_user(username="u2", email="u2@example.com", password="pw", first_name="Alice")

    instance = EmailSendingTable(
        to_user=user,
        to_email=user.email,
        subject="Subject",
        message="<p>ignored</p>",
        template=EmailSendingTable.EmailTemplate.account_enabled,
    )

    plain, html = instance.render_email_bodies()
    assert html is not None
    assert "Dear Alice" in html
    assert "Dear Alice" in plain
    assert "<p>" not in plain


@pytest.mark.django_db
@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
def test_send_email_task_sends_multipart_when_html_message_provided():
    mail.outbox.clear()

    fn = send_email_task.run if hasattr(send_email_task, "run") else send_email_task
    fn(
        subject="Subj",
        message="Plain body",
        html_message="<p>HTML body</p>",
        recipient_list=["to@example.com"],
        fail_silently=False,
        from_email="from@example.com",
    )

    assert len(mail.outbox) == 1
    email = mail.outbox[0]
    assert isinstance(email, EmailMultiAlternatives)
    assert email.body == "Plain body"
    assert ("<p>HTML body</p>", "text/html") in getattr(email, "alternatives", [])


@pytest.mark.django_db
def test_admin_preview_endpoint_renders_preview_without_sending_email():
    # Setup users
    superuser = User.objects.create_superuser(username="admin", email="admin@example.com", password="pw")
    recipient = User.objects.create_user(username="u3", email="u3@example.com", password="pw", first_name="Alice")

    # Ensure no email is sent as a side-effect of preview
    mail.outbox.clear()

    client = Client()
    client.force_login(superuser)

    url = reverse("admin:common_emailsendingtable_preview")
    resp = client.post(
        url,
        data={
            "from_email": "serve@scilifelab.se",
            "to_user": recipient.pk,
            "subject": "Test",
            "message": "<p>Ignored</p>",
            "template": EmailSendingTable.EmailTemplate.account_enabled,
            # status/to_email are readonly in admin and are derived / not posted
        },
    )

    assert resp.status_code == 200
    content = resp.content.decode("utf-8")
    assert "Email preview" in content
    assert "Dear Alice" in content
    assert len(mail.outbox) == 0
