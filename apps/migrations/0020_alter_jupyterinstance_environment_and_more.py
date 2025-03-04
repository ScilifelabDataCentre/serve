# Generated by Django 5.1.1 on 2024-12-12 10:06

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("apps", "0019_alter_shinyinstance_shiny_site_dir"),
        ("projects", "0008_project_deleted_on"),
    ]

    operations = [
        migrations.AlterField(
            model_name="jupyterinstance",
            name="environment",
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.RESTRICT, to="projects.environment"
            ),
        ),
        migrations.AlterField(
            model_name="rstudioinstance",
            name="environment",
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.RESTRICT, to="projects.environment"
            ),
        ),
    ]
