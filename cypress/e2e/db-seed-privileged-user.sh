#!/bin/bash

# Create test users for privileged user tests
docker exec studio bash -c \
    "python manage.py shell < ./cypress/e2e/setup-scripts/seed_privileged_user.py"
