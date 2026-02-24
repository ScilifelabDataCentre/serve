from django.db import migrations, models
import logging

logger = logging.getLogger(__name__)


def populate_affiliations_from_organization(apps, schema_editor):
    """
    Populate the new affiliations list from the existing organization (dict) + department (str).
    Migration 0008 already moved all users from affiliation codes to organization dicts,
    so we only need to read organization + department here.
    """
    UserProfile = apps.get_model("common", "UserProfile")

    migrated_count = 0
    skipped_already_set_count = 0
    skipped_no_org_count = 0
    skipped_invalid_org_count = 0
    failed_count = 0

    for profile in UserProfile.objects.all():
        email = getattr(profile.user, "email", "unknown")

        # Skip profiles that already have affiliations populated
        if profile.affiliations:
            skipped_already_set_count += 1
            print(f"Skipped {email}: affiliations already set ({len(profile.affiliations)} entries)")
            continue

        org = profile.organization

        # Skip profiles with no organization data
        if not org:
            skipped_no_org_count += 1
            print(f"Skipped {email}: no organization data")
            continue

        # Handle case where organization is not a dict (unexpected but defensive)
        if not isinstance(org, dict):
            skipped_invalid_org_count += 1
            logger.warning(f"Skipped {email}: organization is not a dict (type: {type(org).__name__})")
            print(f"Skipped {email}: organization is not a dict (type: {type(org).__name__})")
            continue

        # Skip if organization dict has no title (unexpected but defensive)
        if not org.get("title"):
            skipped_invalid_org_count += 1
            logger.warning(f"Skipped {email}: organization dict has no title: {org}")
            print(f"Skipped {email}: organization dict has no title")
            continue

        profile.affiliations = [
            {
                "title": org["title"],
                "ror_id": org.get("ror_id", "no ror"),
                "department": profile.department or "",
            }
        ]

        try:
            profile.save(update_fields=["affiliations"])
            migrated_count += 1
            print(
                f"Migrated {email}: {org['title']} (ROR: {org.get('ror_id', 'no ror')},"
                f" dept: {profile.department or 'none'})"
            )
        except Exception as e:
            failed_count += 1
            logger.error(f"Failed to migrate {email}: {e}")
            print(f"Failed {email}: {e}")

    print(
        f"\nAffiliations migration complete: {migrated_count} migrated,"
        f" {skipped_already_set_count} already set,"
        f" {skipped_no_org_count} no organization,"
        f" {skipped_invalid_org_count} invalid organization,"
        f" {failed_count} failed"
    )


class Migration(migrations.Migration):
    dependencies = [
        ("common", "0009_userprofile_orcid_access_token_userprofile_orcid_id_and_more"),
    ]

    operations = [
        # Step 1: Add the new affiliations field
        migrations.AddField(
            model_name="userprofile",
            name="affiliations",
            field=models.JSONField(blank=True, default=list),
        ),
        # Step 2: Populate affiliations from organization + department
        migrations.RunPython(
            populate_affiliations_from_organization,
            reverse_code=migrations.RunPython.noop,
        ),
        # Step 3: Remove legacy fields (auto-reversed by Django as AddField)
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
