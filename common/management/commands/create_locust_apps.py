from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.helpers import create_app_instance
from apps.models import Apps
from projects.models import Flavor, Project

User = get_user_model()


class Command(BaseCommand):
    help = "Creates projects for locust users"

    def handle(self, *args, **options):
        identifier = "locust_test_user"

        users = User.objects.filter(email__contains=identifier).order_by("date_joined")

        for user in users:
            project = Project.objects.filter(owner=user).first()

            if project is not None:
                flavor = Flavor.objects.filter(project=project).first()
                app = Apps.objects.filter(slug="jupyter-lab").order_by("-revision").first()

                if flavor is not None and app is not None:
                    data = {
                        "app_name": f"JL-{user.email}",
                        "app_description": "Test app for Locust load testing",
                        "flavor": str(flavor.pk),
                        "permission": "private",
                    }

                    successful, project_slug, app_category_slug = create_app_instance(
                        user, project, app, app.settings, data=data
                    )
                else:
                    self.stdout.write(self.style.WARNING(f"Flavor or app not found for user: {user.email}"))
            else:
                self.stdout.write(self.style.WARNING(f"Project not found for user: {user.email}"))

        self.stdout.write(self.style.SUCCESS(f"Successfully created {users.count()} apps"))
