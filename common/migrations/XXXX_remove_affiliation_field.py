# Future migration: common/migrations/XXXX_remove_affiliation_field.py
from django.db import migrations

class Migration(migrations.Migration):
    dependencies = [
        ('common', 'XXXX_migrate_affiliation_to_organization'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='userprofile',
            name='affiliation',
        ),
    ]