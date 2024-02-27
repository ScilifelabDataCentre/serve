#!/bin/bash

# Create test user for brute force login tests
docker exec studio bash -c \
    "python manage.py shell < ./cypress/e2e/setup-scripts/seed_brute_force_login_user.py"
