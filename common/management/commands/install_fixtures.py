import hashlib

from django.core.management import call_command
from django.core.management.base import BaseCommand

from common.models import FixtureVersion


class Command(BaseCommand):
    help = "Load fixtures if they have changed"

    def handle(self, *args, **kwargs):
        # Define all fixtures here
        files = [
            "appcats_fixtures.json",
            "apps_fixtures.json",
            "intervals_fixtures.json",
            "periodic_tasks_fixtures.json",
            "objecttype_fixtures.json",
            "groups_fixtures.json",
            "projects_templates.json",
        ]
        fixture_files = ["fixtures/" + file for file in files]

        for fixture in fixture_files:
            # Create hash for each file
            with open(fixture, "rb") as file:
                content = file.read()
                current_hash = hashlib.sha256(content).hexdigest()

            # Check if the object exists and if it has changed
            obj, created = FixtureVersion.objects.get_or_create(filename=fixture)
            if created or obj.hash != current_hash:
                call_command("loaddata", fixture)
                obj.hash = current_hash
                obj.save()
            else:
                self.stdout.write(self.style.SUCCESS(f"No changes in {fixture}"))
