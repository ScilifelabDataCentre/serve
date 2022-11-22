# Generated by Django 3.2.11 on 2022-02-01 11:37

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('models', '0008_alter_model_release_type'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='objecttype',
            name='apps',
        ),
        migrations.AddField(
            model_name='objecttype',
            name='app_slug',
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
    ]