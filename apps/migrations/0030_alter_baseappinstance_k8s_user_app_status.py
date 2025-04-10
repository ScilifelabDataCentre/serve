# Generated by Django 5.1.1 on 2025-03-25 11:40

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("apps", "0029_alter_shinyinstance_path"),
    ]

    operations = [
        migrations.AlterField(
            model_name="baseappinstance",
            name="k8s_user_app_status",
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.RESTRICT,
                related_name="%(class)s",
                to="apps.k8suserappstatus",
            ),
        ),
    ]
