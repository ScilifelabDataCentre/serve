from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from django.contrib.auth import get_user_model

from apps.helpers import create_app_instance
from apps.models import Apps
from projects.models import Project, Flavor

User = get_user_model()

class Command(BaseCommand):
    help = "Creates projects for locust users"

    def handle(self, *args, **options):
        identifier = f'locust_test_user'

        users = User.objects.filter(email__contains=identifier)
        print(users, flush=True)
        for user in users:
            
            
            project = Project.objects.filter(owner=user).first()

            flavor = Flavor.objects.filter(project=project).first()
            app = Apps.objects.filter(slug="jupyter-lab").order_by("-revision")[0]
            
            data = {"app_name": f"JL-{user.email}", 
                    "app_description": "Test app for Locust load testing",
                    "flavor": str(flavor.pk),
                    "permission": "private"}
            
            successful, project_slug, app_category_slug = create_app_instance(user, project, app, app.settings, data=data)
            if successful:       
                self.stdout.write(
                    self.style.SUCCESS(f"Successfully created an app instance in {project.name}")
                )
            else:
                self.stdout.write(
                    self.style.ERROR("Something went wrong and the app was not created")
                )


        self.stdout.write(
            self.style.SUCCESS(f"Successfully created {users.count()} apps")
        )









