from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from apps.models import Apps
from projects.models import Environment, Flavor, Project, ProjectTemplate

User = get_user_model()


class Command(BaseCommand):
    help = "Seed data used by automated accessibility checks"

    def handle(self, *args, **kwargs):
        user_data = {
            "username": "e2e_a11y_user",
            "email": "no-reply-a11y@scilifelab.uu.se",
            "password": "tesT12345@",
        }

        user, created = User.objects.get_or_create(
            email=user_data["email"],
            defaults={"username": user_data["username"]},
        )

        if created:
            user.set_password(user_data["password"])
        else:
            user.username = user_data["username"]
        user.is_active = True
        user.save()

        project_template = ProjectTemplate.objects.get(pk=1)
        project = Project.objects.filter(owner=user, name="e2e-a11y-project", status="active").first()

        if project is None:
            project = Project.objects.create_project(
                name="e2e-a11y-project",
                owner=user,
                description="Project used by automated accessibility checks.",
                project_template=project_template,
            )

        Flavor.objects.get_or_create(
            project=project,
            name="a11y-default",
            defaults={
                "cpu_req": "200m",
                "cpu_lim": "2000m",
                "mem_req": "0.5Gi",
                "mem_lim": "4Gi",
                "gpu_req": "0",
                "gpu_lim": "0",
                "ephmem_req": "200Mi",
                "ephmem_lim": "5000Mi",
            },
        )

        jupyter_app = Apps.objects.filter(slug="jupyter-lab").order_by("-revision").first()
        if jupyter_app is not None:
            Environment.objects.get_or_create(
                project=project,
                app=jupyter_app,
                name="A11y Jupyter Lab Minimal",
                defaults={
                    "repository": "docker.io",
                    "image": "jupyter/minimal-notebook:latest",
                },
            )

        self.stdout.write(self.style.SUCCESS("Accessibility seed data is ready."))
