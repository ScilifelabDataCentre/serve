"""DB seed script for e2e cypress contributor tests."""

import json
import os.path

from django.conf import settings
from django.contrib.auth import get_user_model

from projects.models import Project, ProjectTemplate

User = get_user_model()

cypress_path = os.path.join(settings.BASE_DIR, "cypress/fixtures")
print(f"Now loading the json users file from fixtures path: {cypress_path}")  # /app/cypress/fixtures

with open(os.path.join(cypress_path, "users.json"), "r") as f:
    testdata = json.load(f)

    # Create the contributor user
    userdata = testdata["contributor"]
    username = userdata["username"]
    email = userdata["email"]
    pwd = userdata["password"]

    if not User.objects.filter(email=email).exists():
        user = User.objects.create_user(username, email, pwd)
    else:
        user = User.objects.get(username=email)
    project_template = ProjectTemplate.objects.get(pk=1)

    # Check if project exists, otherwise, create it
    if not Project.objects.filter(name="e2e-delete-proj-test").exists():
        _ = Project.objects.create_project(
            name="e2e-delete-proj-test", owner=user, description="", project_template=project_template
        )

    # Create the contributor's collaborator user
    co_userdata = testdata["contributor_collaborator"]
    co_username = co_userdata["username"]
    co_email = co_userdata["email"]
    co_pwd = co_userdata["password"]

    if not User.objects.filter(username=co_email).exists():
        co_user = User.objects.create_user(co_username, co_email, co_pwd)
    else:
        co_user = User.objects.get(username=co_email)

    # Check if project exists, otherwise, create it
    if not Project.objects.filter(name="e2e-collaborator-proj-test").exists():
        _ = Project.objects.create_project(
            name="e2e-collaborator-proj-test", owner=co_user, description="", project_template=project_template
        )
