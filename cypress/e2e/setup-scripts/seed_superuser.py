"""DB seed script for e2e cypress superuser tests."""

import json
import os.path

from django.conf import settings
from django.contrib.auth.models import User

from apps.helpers import create_app_instance
from apps.models import Apps
from projects.models import Environment, Flavor, Project, ProjectTemplate
from projects.tasks import create_resources_from_template

cypress_path = os.path.join(settings.BASE_DIR, "cypress/fixtures")
print(f"Now loading the json users file from fixtures path: {cypress_path}")  # /app/cypress/fixtures

with open(os.path.join(cypress_path, "users.json"), "r") as f:
    testdata = json.load(f)

    s_userdata = testdata["superuser"]
    s_username = s_userdata["username"]
    s_email = s_userdata["email"]
    s_pwd = s_userdata["password"]
    # Create the superuser
    superuser = User.objects.create_superuser(s_username, s_email, s_pwd)
    superuser.save()

    userdata = testdata["superuser_testuser"]
    username = userdata["username"]
    email = userdata["email"]
    pwd = userdata["password"]
    # Create the regular user
    user = User.objects.create_user(username, email, pwd)
    user.save()

    # Create a dummy project belonging to the regular user to be inspected by the superuser tests
    project = Project.objects.create_project(
        name="e2e-superuser-testuser-proj-test", owner=user, description="Description by regular user"
    )
    project.save()

    # Create a private app belonging to the regular user to be inspected by the superuser
    # create resources inside the project
    project_template = ProjectTemplate.objects.get(pk=1)
    create_resources_from_template(user.username, project.slug, project_template.template)
    # define variables needed
    app = Apps.objects.filter(slug="jupyter-lab").order_by("-revision").first()
    flavor = Flavor.objects.filter(project=project).first()
    environment = Environment.objects.filter(project=project).first()
    data = {
        "app_name": "Regular user's private app",
        "app_description": "Test app for superuser testing",
        "flavor": str(flavor.pk),
        "permission": "private",
        "environment": str(environment.pk),
    }
    # now create app
    create_app_instance(user, project, app, app.settings, data=data)
