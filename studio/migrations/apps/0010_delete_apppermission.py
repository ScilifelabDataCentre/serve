# Generated by Django 4.1.7 on 2023-03-22 10:36

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('apps', '0009_alter_appinstance_options'),
    ]

    operations = [
        migrations.DeleteModel(
            name='AppPermission',
        ),
    ]