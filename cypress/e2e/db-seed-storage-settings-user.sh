#!/bin/bash

# Create test user for storage settings tests
docker exec studio bash -c \
    "python manage.py shell < ./cypress/e2e/setup-scripts/seed_storage_settings_user.py"
