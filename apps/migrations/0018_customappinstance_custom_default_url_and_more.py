# Generated by Django 5.1.1 on 2024-10-29 14:36

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("apps", "0017_alter_streamlitinstance_port"),
    ]

    operations = [
        migrations.AddField(
            model_name="customappinstance",
            name="custom_default_url",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
    ]