#!/bin/bash

# Create test user for user-manage-apps tests
docker exec studio bash -c \
    "python manage.py shell < ./cypress/e2e/setup-scripts/seed_user_manage_apps_user.py"
