"""DB seed script for e2e cypress collections tests."""

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

    userdata = testdata["collections_user"]

    username = userdata["username"]
    email = userdata["email"]
    pwd = userdata["password"]

    # Create a superuser because that's the one that can currently create collections
    superuser = User.objects.create_superuser(username, email, pwd)
    superuser.save()

    # Create a project for apps to be included in the collection
    project = Project.objects.create_project(
        name="e2e-collections-test-proj", owner=superuser, description="e2e-collections-test-proj-desc"
    )
    project.save()

    # Create an app to be included in a collection
    # create resources inside the project
    project_template = ProjectTemplate.objects.get(pk=1)
    create_resources_from_template(superuser.username, project.slug, project_template.template)
    # define variables needed
    app = Apps.objects.filter(slug="dashapp").order_by("-revision").first()
    flavor = Flavor.objects.filter(project=project).first()
    environment = Environment.objects.filter(project=project).first()
    data = {
        "app_name": "collection-app-name",
        "app_description": "collection-app-description",
        "flavor": str(flavor.pk),
        "permission": "public",
        "environment": str(environment.pk),
    }
    # now create app
    create_app_instance(superuser, project, app, app.settings, data=data)
