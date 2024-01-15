import logging

from django.apps import apps
from django.conf import settings as django_settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from projects.exceptions import ProjectCreationException
from projects.models import Project, ProjectTemplate
from projects.tasks import create_resources_from_template

User = get_user_model()


class Command(BaseCommand):
    help = "Creates projects for locust users"

    def handle(self, *args, **options):
        identifier = "locust_test_user"
        users = User.objects.filter(email__contains=identifier).order_by("date_joined")

        for i, user in enumerate(users, 1):
            try:
                project = Project.objects.create_project(
                    name=f"locust_test_project_{i}",
                    owner=user,
                    description="Just a test project for locust load test",
                    status="created",
                )

            except ProjectCreationException:
                self.stdout.write(self.style.ERROR("ERROR: Failed to create project database object."))

            try:
                # Create resources from the chosen template
                project_template = ProjectTemplate.objects.get(pk=1)
                create_resources_from_template.delay(user.username, project.slug, project_template.template)
            except ProjectCreationException:
                self.stdout.write(self.style.ERROR("ERROR: Failed to create project resources"))

        if not users:
            self.stdout.write(self.style.ERROR(f'No users matching "{identifier}"'))

        self.stdout.write(self.style.SUCCESS(f"Successfully created {users.count()} projects"))
