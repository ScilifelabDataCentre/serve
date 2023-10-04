"""DB seed script for e2e cypress superuser tests."""

import json
import os.path

from django.conf import settings
from django.contrib.auth.models import User

from projects.models import Project

cypress_path = os.path.join(settings.BASE_DIR, "cypress/fixtures")
print(f"Now loading the json users file from fixtures path: {cypress_path}")  # /app/cypress/fixtures

with open(os.path.join(cypress_path, "users.json"), "r") as f:
    testdata = json.load(f)

    userdata = testdata["superuser"]

    username = userdata["username"]
    email = userdata["email"]
    pwd = userdata["password"]

    # Create the superuser
    superuser = User.objects.create_superuser(username, email, pwd)
    superuser.save()

    # Create a dummy project to be inspected by the superuser tests
    Project.objects.create_project(name="e2e-superuser-proj-test", owner=superuser, description="", repository="")
