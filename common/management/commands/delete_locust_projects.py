import logging

from django.core.management.base import BaseCommand, CommandError
from django.apps import apps
from django.conf import settings as django_settings
from django.contrib.auth import get_user_model


from projects.exceptions import ProjectCreationException
from projects.models import (
    Project,
    ProjectTemplate,
)
from projects.tasks import delete_project

User = get_user_model()

class Command(BaseCommand):
    help = "Creates projects for locust users"

    def handle(self, *args, **options):
        identifier = f'locust_test_user'

        projects_to_delete = Project.objects.filter(owner__email__contains=identifier)

        for project in projects_to_delete:
            delete_project.delay(project.pk)
            self.stdout.write(
                self.style.SUCCESS(f"Successfully deleted project {project.name}")
            )

        self.stdout.write(
            self.style.SUCCESS(f"Successfully deleted {projects_to_delete.count()} projects")
        )








