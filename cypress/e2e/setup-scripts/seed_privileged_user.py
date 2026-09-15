"""DB seed script for e2e cypress privileged user tests."""

import json
import os.path

from django.conf import settings

from common.management.manage_test_data import TestDataManager

cypress_path = os.path.join(settings.BASE_DIR, "cypress/fixtures")
print(f"Now loading the json users file from fixtures path: {cypress_path}")

with open(os.path.join(cypress_path, "users.json")) as f:
    testdata = json.load(f)

TestDataManager(user_data=testdata["privileged_user"]).create_privileged_user()
TestDataManager(user_data=testdata["privileged_collaborator"]).create_privileged_user()
