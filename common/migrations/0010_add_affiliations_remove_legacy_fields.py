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


def reverse_affiliations_to_organization(apps, schema_editor):
    """
    Reverse migration: restore organization (dict) and department (str) from affiliations list.
    Takes the first affiliation entry as the primary one, since the old schema only supported
    a single organization + department.
    """
    UserProfile = apps.get_model("common", "UserProfile")

    restored_count = 0
    skipped_no_affiliations_count = 0
    skipped_invalid_count = 0
    failed_count = 0

    for profile in UserProfile.objects.all():
        email = getattr(profile.user, "email", "unknown")

        if not profile.affiliations or not isinstance(profile.affiliations, list):
            skipped_no_affiliations_count += 1
            print(f"Reverse skipped {email}: no affiliations data")
            continue

        first = profile.affiliations[0]

        if not isinstance(first, dict) or not first.get("title"):
            skipped_invalid_count += 1
            logger.warning(f"Reverse skipped {email}: first affiliation is invalid: {first}")
            print(f"Reverse skipped {email}: first affiliation is invalid")
            continue

        profile.organization = {
            "title": first["title"],
            "ror_id": first.get("ror_id", "no ror"),
        }
        profile.department = first.get("department", "")

        if len(profile.affiliations) > 1:
            dropped = profile.affiliations[1:]
            dropped_summary = "; ".join(
                f"{a.get('title', '?')} (ROR: {a.get('ror_id', '?')}, dept: {a.get('department', '?')})"
                for a in dropped
            )
            logger.warning(
                f"Reverse {email}: had {len(profile.affiliations)} affiliations,"
                " only the first was restored to organization/department."
                f" Dropped affiliations: {dropped_summary}"
            )
            print(f"Reverse {email}: dropped {len(dropped)} extra affiliation(s): {dropped_summary}")

        try:
            profile.save(update_fields=["organization", "department"])
            restored_count += 1
            print(
                f"Reversed {email}: {first['title']} (ROR: {first.get('ror_id', 'no ror')},"
                f" dept: {first.get('department', 'none')})"
            )
        except Exception as e:
            failed_count += 1
            logger.error(f"Failed to reverse {email}: {e}")
            print(f"Reverse failed {email}: {e}")

    print(
        f"\nReverse migration complete: {restored_count} restored,"
        f" {skipped_no_affiliations_count} no affiliations,"
        f" {skipped_invalid_count} invalid affiliations,"
        f" {failed_count} failed"
    )

    if any(
        len(p.affiliations) > 1
        for p in UserProfile.objects.all()
        if p.affiliations and isinstance(p.affiliations, list)
    ):
        print(
            "\nWARNING: Some profiles had multiple affiliations. Only the first was restored."
            " Additional affiliations were lost. Check logs for details."
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
            reverse_code=reverse_affiliations_to_organization,
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
