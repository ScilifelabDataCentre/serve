# Generated by Django 5.1.1 on 2024-11-27 12:47

import apps.models.app_types.shiny
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("apps", "0018_customappinstance_default_url_subpath"),
    ]

    operations = [
        migrations.AlterField(
            model_name="shinyinstance",
            name="shiny_site_dir",
            field=models.CharField(
                blank=True, default="", max_length=255, validators=[apps.helpers.validate_path_k8s_label_compatible]
            ),
        ),
    ]