"""DB seed script for e2e cypress contributor tests."""

import json
import os.path

from django.conf import settings
from django.contrib.auth.models import User

cypress_path = os.path.join(settings.BASE_DIR, "cypress/fixtures")
print(f"Now loading the json users file from fixtures path: {cypress_path}")  # /app/cypress/fixtures

with open(os.path.join(cypress_path, "users.json"), "r") as f:
    testdata = json.load(f)

    userdata = testdata["deploy_app_user"]

    username = userdata["username"]
    email = userdata["email"]
    pwd = userdata["password"]

    # Create the deploy-app-user user
    user = User.objects.create_user(username, email, pwd)
    user.save()
