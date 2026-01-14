# Future migration: common/migrations/XXXX_migrate_affiliation_to_organization.py

from django.db import migrations
import json
import requests
import logging

logger = logging.getLogger(__name__)


def fetch_ror_id(university_name):
    """
    Fetch ROR ID from ROR API for a given university name
    Returns the ROR ID or "migrated_from_legacy" as fallback
    """
    try:
        response = requests.get("https://api.ror.org/organizations", params={"query": university_name}, timeout=5)
        response.raise_for_status()
        data = response.json()

        # Look for exact or close match
        if data.get("items"):
            for item in data.get("items", []):
                # Extract the organization title from names array
                item_title = ""
                for name in item.get("names", []):
                    if "ror_display" in name.get("types", []):
                        item_title = name.get("value", "")
                        break

                # If no ror_display found, use the first name
                if not item_title and item.get("names"):
                    item_title = item["names"][0].get("value", "")

                # Check for exact match (case-insensitive)
                if item_title.lower() == university_name.lower():
                    ror_id = item.get("id", "migrated_from_legacy")
                    logger.info(f"Found ROR ID for {university_name}: {ror_id}")
                    return ror_id

            # If no exact match, take the first result as best guess
            if data.get("items"):
                first_item = data["items"][0]
                ror_id = first_item.get("id", "migrated_from_legacy")
                logger.warning(f"No exact match for {university_name}, using first result: {ror_id}")
                return ror_id

    except Exception as e:
        logger.warning(f"Failed to fetch ROR ID for {university_name}: {e}")

    return "migrated_from_legacy"


def migrate_affiliation_to_organization(apps, schema_editor):
    """
    Migrate existing affiliation data to the new organization field with ROR lookup
    """
    UserProfile = apps.get_model("common", "UserProfile")

    # Load universities mapping from file
    try:
        with open("static/common/universities.json", "r") as f:
            universities = json.load(f).get("universities", {})
    except Exception as e:
        logger.error(f"Failed to load universities.json: {e}")
        # Fallback to hardcoded mapping if file not found
        universities = {
            "bth": "Blekinge Institute of Technology",
            "chalmers": "Chalmers University of Technology",
            "du": "Dalarna University",
            "fhs": "Swedish Defence University",
            "gih": "Swedish School of Sport and Health Sciences",
            "gu": "Göteborgs University",
            "hb": "University of Borås",
            "hh": "Halmstad University",
            "hhs": "Stockholm School of Economics",
            "hig": "University of Gävle",
            "his": "University of Skövde",
            "hkr": "Kristianstad University",
            "hv": "University West",
            "ju": "Jönköping University",
            "kau": "Karlstad University",
            "ki": "(KI) Karolinska institutet",
            "kth": "KTH Royal Institute of Technology",
            "liu": "Linköpings University",
            "lnu": "Linnaeus University",
            "lth": "LTH Lund University",
            "ltu": "Luleå University of Technology",
            "lu": "Lund University",
            "mau": "Malmö University",
            "mdu": "Mälardalen University",
            "miun": "Mid Sweden University",
            "oru": "Örebro University",
            "other": "Other",
            "sh": "Södertörn University",
            "slu": "Swedish University of Agricultural Sciences",
            "su": "Stockholms University",
            "umu": "Umeå University",
            "uu": "Uppsala University",
        }

    migrated_count = 0
    failed_count = 0
    affiliation_code_not_found_count = 0

    for profile in UserProfile.objects.all():
        if profile.affiliation and not profile.organization:
            # Check if affiliation code exists in mapping
            if profile.affiliation not in universities:
                logger.warning(
                    f"Affiliation code '{profile.affiliation}' not found in universities mapping for {profile.user.email}"
                )
                title = "Other"
                ror_id = "migrated_from_legacy"
                affiliation_code_not_found_count += 1
            else:
                # Get university name from affiliation code
                university_name = universities[profile.affiliation]
                title = university_name

                # Fetch ROR ID from API
                ror_id = fetch_ror_id(university_name)

            # Create organization data from affiliation
            profile.organization = {
                "title": title,
                "ror_id": ror_id,
                "legacy_affiliation": profile.affiliation,  # Keep original for reference
            }

            try:
                profile.save()
                migrated_count += 1
                print(f"Migrated {profile.user.email}: {profile.affiliation} -> {university_name} (ROR: {ror_id})")
            except Exception as e:
                failed_count += 1
                logger.error(f"Failed to migrate {profile.user.email}: {e}")

    print(
        f"\nMigration complete: {migrated_count} profiles migrated, {failed_count} failed, {affiliation_code_not_found_count} affiliation code not found"
    )


def reverse_migration(apps, schema_editor):
    """
    Reverse migration if needed
    """
    UserProfile = apps.get_model("common", "UserProfile")

    for profile in UserProfile.objects.all():
        if profile.organization:
            # Restore from legacy_affiliation if available
            legacy_aff = profile.organization.get("legacy_affiliation")
            if legacy_aff:
                profile.affiliation = legacy_aff
                profile.organization = {}
                profile.save()
                print(f"Reversed migration for {profile.user.email}")


class Migration(migrations.Migration):
    dependencies = [
        ("common", "0007_add_userprofile_organization"),
    ]

    operations = [
        migrations.RunPython(migrate_affiliation_to_organization, reverse_migration),
    ]
