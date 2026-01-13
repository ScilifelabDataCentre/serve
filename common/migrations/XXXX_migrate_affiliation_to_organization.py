# Future migration: common/migrations/XXXX_migrate_affiliation_to_organization.py
 
from django.db import migrations
import json

def migrate_affiliation_to_organization(apps):
    """
    Migrate existing affiliation data to the new organization field
    """
    UserProfile = apps.get_model('common', 'UserProfile')
    
    # University code to name mapping (from your universities.json)
    # Load this from your static file or hardcode it
    with open('static/common/universities.json', 'r') as f:
        universities = json.load(f).get('universities', {})
    
    for profile in UserProfile.objects.all():
        if profile.affiliation and not profile.organization:
            # Create organization data from affiliation
            university_name = universities.get(profile.affiliation, profile.affiliation)
            profile.organization = {
                "title": university_name,
                "ror_id": "migrated_from_legacy",  # Flag for legacy data
                "legacy_affiliation": profile.affiliation  # Keep original for reference
            }
            profile.save()
            print(f"Migrated {profile.user.email}: {profile.affiliation} -> {university_name}")

#"""
def reverse_migration(apps):
    """
     Reverse migration if needed
    """
    UserProfile = apps.get_model('common', 'UserProfile')
    
    for profile in UserProfile.objects.all():
        if profile.organization and profile.organization.get('ror_id') == 'migrated_from_legacy':
            # Restore from legacy_affiliation if available
            legacy_aff = profile.organization.get('legacy_affiliation')
            if legacy_aff:
                profile.affiliation = legacy_aff
                profile.organization = {}
                profile.save()
#"""

class Migration(migrations.Migration):
    dependencies = [
        ('common', '0009_add_userprofile_organization'),
    ]

    operations = [
        migrations.RunPython(
            migrate_affiliation_to_organization,
            reverse_migration
        ),
    ]