# Generated by Django 5.1.1 on 2024-09-27 12:11

import tagulous.models.fields
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("apps", "0012_rstudioinstance_environment"),
    ]

    operations = [
        migrations.AlterField(
            model_name="customappinstance",
            name="tags",
            field=tagulous.models.fields.TagField(
                _set_tag_meta=True,
                blank=True,
                force_lowercase=True,
                help_text="Add keywords to help categorize your app",
                to="apps.tagulous_customappinstance_tags",
            ),
        ),
        migrations.AlterField(
            model_name="dashinstance",
            name="tags",
            field=tagulous.models.fields.TagField(
                _set_tag_meta=True,
                blank=True,
                force_lowercase=True,
                help_text="Add keywords to help categorize your app",
                to="apps.tagulous_dashinstance_tags",
            ),
        ),
        migrations.AlterField(
            model_name="shinyinstance",
            name="shiny_site_dir",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AlterField(
            model_name="shinyinstance",
            name="tags",
            field=tagulous.models.fields.TagField(
                _set_tag_meta=True,
                blank=True,
                force_lowercase=True,
                help_text="Add keywords to help categorize your app",
                to="apps.tagulous_shinyinstance_tags",
            ),
        ),
        migrations.AlterField(
            model_name="tissuumapsinstance",
            name="tags",
            field=tagulous.models.fields.TagField(
                _set_tag_meta=True,
                blank=True,
                force_lowercase=True,
                help_text="Add keywords to help categorize your app",
                to="apps.tagulous_tissuumapsinstance_tags",
            ),
        ),
    ]