from django.db import migrations, models


def populate_affiliations_from_organization(apps, schema_editor):
    """
    Populate the new affiliations list from the existing organization (dict) + department (str).
    Migration 0008 already moved all users from affiliation codes to organization dicts,
    so we only need to read organization + department here.
    """
    UserProfile = apps.get_model("common", "UserProfile")

    for profile in UserProfile.objects.all():
        if profile.affiliations:
            continue

        org = profile.organization
        if org and isinstance(org, dict) and org.get("title"):
            profile.affiliations = [
                {
                    "title": org["title"],
                    "ror_id": org.get("ror_id", "no ror"),
                    "department": profile.department or "",
                }
            ]
            profile.save(update_fields=["affiliations"])


class Migration(migrations.Migration):
    dependencies = [
        ("common", "0009_userprofile_orcid_access_token_userprofile_orcid_id_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="userprofile",
            name="affiliations",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.RunPython(
            populate_affiliations_from_organization,
            reverse_code=migrations.RunPython.noop,
        ),
        migrations.RemoveField(
            model_name="userprofile",
            name="affiliation",
        ),
        migrations.RemoveField(
            model_name="userprofile",
            name="organization",
        ),
        migrations.RemoveField(
            model_name="userprofile",
            name="department",
        ),
    ]
