"""DB seed script for e2e cypress superuser tests."""

import json
import os.path

from django.conf import settings
from django.contrib.auth.models import User
from django.db import transaction
from apps.constants import SLUG_MODEL_FORM_MAP
from apps.helpers import create_instance_from_form
from apps.models import Apps
from projects.models import Environment, Flavor, Project, ProjectTemplate
from projects.tasks import create_resources_from_template

from studio.utils import get_logger
logger = get_logger(__name__)

cypress_path = os.path.join(settings.BASE_DIR, "cypress/fixtures")
logger.info("RUNNING CYPRESS TESTS SETUP SCRIPTS")
logger.debug(f"Now loading the json users file from fixtures path: {cypress_path}")  # /app/cypress/fixtures

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

with transaction.atomic():
    logger.debug("Creating regular user")
    user = User.objects.create_user(username, email, pwd)
    user.save()

    logger.debug("Create a dummy project belonging to the regular user to be inspected by the superuser tests")
    project = Project.objects.create_project(
        name="e2e-superuser-testuser-proj-test", owner=user, description="Description by regular user"
    )
    project.save()

    # Create a private app belonging to the regular user to be inspected by the superuser
    try:
        logger.debug("Create resources from project template")
        project_template = ProjectTemplate.objects.get(pk=1)
        create_resources_from_template(user.username, project.slug, project_template.template)
    except ProjectTemplate.DoesNotExist:
        logger.error("Project template not found")
        raise ValueError("Project template not found")
    except Exception as e:
        logger.error(f"Error creating resources from project template: {e}")
        raise ValueError(f"Error creating resources from project template: {e}")

    flavor = Flavor.objects.filter(project=project).first()

    # define variables needed
    app_slug = "jupyter-lab"

    data = {
        "name": "Regular user's private app",
        "flavor": str(flavor.pk),
        "access": "private",
        "volume": None
    }

    model_form_tuple = SLUG_MODEL_FORM_MAP.get(app_slug, None)
    if not model_form_tuple:
        raise ValueError(f"Form class not found for app slug {app_slug}")

    # Create form
    form = model_form_tuple.Form(data, project_pk=project.pk)

    if form.is_valid():
        # now create app
        create_instance_from_form(form, project, app_slug)
    else:
        raise ValueError(f"Form is invalid: {form.errors.as_data()}")

