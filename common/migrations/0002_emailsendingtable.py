# Generated by Django 5.1.1 on 2025-06-24 15:25

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("common", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="EmailSendingTable",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "from_email",
                    models.EmailField(
                        choices=[
                            ("serve@scilifelab.se", "serve@scilifelab.se"),
                            ("noreply-serve@scilifelab.se", "noreply-serve@scilifelab.se"),
                        ],
                        max_length=254,
                    ),
                ),
                ("to_email", models.EmailField(max_length=254)),
                (
                    "subject",
                    models.CharField(
                        help_text="Subject of the email.If there is already exists a ticket on Edge, you can use it's subject to track email history through it.",
                        max_length=255,
                    ),
                ),
                (
                    "message",
                    models.TextField(
                        blank=True,
                        default="",
                        help_text="Email message to be sent. If base template is selected, this will be rendered using the template. You can use HTML tags here.",
                        null=True,
                    ),
                ),
                (
                    "template",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("admin/email/base.html", "admin/email/base.html"),
                            (
                                "admin/email/user-in-not-from-a-swedish-uni.html",
                                "admin/email/user-in-not-from-a-swedish-uni.html",
                            ),
                            ("admin/email/account-enabled-email.html", "admin/email/account-enabled-email.html"),
                        ],
                        max_length=100,
                        null=True,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[("sent", "Sent"), ("failed", "Failed")], default="pending", max_length=10
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "to_user",
                    models.ForeignKey(
                        null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL
                    ),
                ),
            ],
        ),
    ]
