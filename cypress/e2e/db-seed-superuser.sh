#!/bin/bash

# Create test user for superuser tests
docker exec studio bash -c \
    "python manage.py shell < ./cypress/e2e/setup-scripts/seed_superuser.py"
