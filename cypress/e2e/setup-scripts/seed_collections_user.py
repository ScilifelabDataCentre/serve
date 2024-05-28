"""DB seed script for e2e cypress collections tests."""

import json
import os.path

from django.conf import settings
from django.contrib.auth.models import User
from django.db import transaction

from apps.constants import APP_REGISTRY
from apps.helpers import create_instance_from_form
from apps.models import Apps
from projects.models import Flavor, Project, ProjectTemplate
from projects.tasks import create_resources_from_template

cypress_path = os.path.join(settings.BASE_DIR, "cypress/fixtures")
print(f"Now loading the json users file from fixtures path: {cypress_path}")  # /app/cypress/fixtures

with open(os.path.join(cypress_path, "users.json"), "r") as f:
    testdata = json.load(f)


userdata = testdata["collections_user"]

username = userdata["username"]
email = userdata["email"]
pwd = userdata["password"]

with transaction.atomic():
    # Create a superuser because that's the one that can currently create collections
    superuser = User.objects.create_superuser(username, email, pwd)
    superuser.save()

    project_template = ProjectTemplate.objects.get(pk=1)
    # Create a project for apps to be included in the collection
    project = Project.objects.create_project(
        name="e2e-collections-test-proj",
        owner=superuser,
        description="e2e-collections-test-proj-desc",
        project_template=project_template,
    )
    project.save()

    # Create an app to be included in a collection
    # create resources inside the project

    create_resources_from_template(superuser.username, project.slug, project_template.template)
    # define variables needed
    app = Apps.objects.filter(slug="dashapp").order_by("-revision").first()
    flavor = Flavor.objects.filter(project=project).first()

    # define variables needed
    app_slug = "dashapp"

    data = {
        "name": "collection-app-name",
        "description": "collection-app-description",
        "flavor": str(flavor.pk),
        "access": "public",
        "port": 8000,
        "image": "some-image",
        "source_code_url": "https://someurlthatdoesnotexist.com",
    }

    # Check if the model form tuple exists
    if app_slug not in APP_REGISTRY:
        raise ValueError(f"Form class not found for app slug {app_slug}")

    model_form_tuple = APP_REGISTRY.get(app_slug)

    # Create form
    form = model_form_tuple.Form(data, project_pk=project.pk)

    if form.is_valid():
        # now create app
        create_instance_from_form(form, project, app_slug)
    else:
        raise ValueError(f"Form is invalid: {form.errors.as_data()}")
