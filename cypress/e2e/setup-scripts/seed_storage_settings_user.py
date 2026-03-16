"""DB seed script for e2e cypress storage settings tests."""

import json
import os.path

from django.conf import settings
from django.contrib.auth.models import User

cypress_path = os.path.join(settings.BASE_DIR, "cypress/fixtures")
print(f"Now loading the json users file from fixtures path: {cypress_path}")

with open(os.path.join(cypress_path, "users.json"), "r") as f:
    testdata = json.load(f)

    userdata = testdata["storage_settings_user"]

    username = userdata["username"]
    email = userdata["email"]
    pwd = userdata["password"]

    user = User.objects.create_user(username, email, pwd)
    user.save()
