#!/bin/bash

if [ -n "${RESET_DB}" ] && [ "${RESET_DB}" = "true" ] && [ -n "${DEBUG}" ] && [ "${DEBUG}" = "true" ]; then
    echo "RESETTING DATABASE..."
    python manage.py reset_db --no-input --close-sessions
    echo "Uninstalling all Helm releases in serve-dev namespace"
    helm uninstall $(helm ls --all --short -n serve-dev) -n serve-dev
fi

echo "Running studio migrations..."

# Replace storageclass in project template fixture
if [ -n "$STUDIO_STORAGECLASS" ]; then
    sed -i "s/microk8s-hostpath/$STUDIO_STORAGECLASS/g" ./fixtures/projects_templates.json
fi

# Replace accessmode
if [ -n "$STUDIO_ACCESSMODE" ]; then
    sed -i "s/ReadWriteMany/$STUDIO_ACCESSMODE/g" ./fixtures/projects_templates.json
    sed -i "s/ReadWriteMany/$STUDIO_ACCESSMODE/g" ./fixtures/apps_fixtures.json
fi

python manage.py migrate

python manage.py migrate waffle
python manage.py waffle_switch docker_image_architecture_validator off --create
python manage.py waffle_switch background_tasks_nonblocking_deploy on --create
python manage.py waffle_switch christmas_theme off --create

# NOTE: The following fixtures and super user creation are executed as a helm post-install k8s job, thus disabled here.
# However for testing and developement purpose, activate them when not using a post-install job

echo "Loading Studio Fixtures..."
python manage.py install_fixtures

# This script goes through all app instances and assigns/removes permissions to users based on the instance access level
python manage.py runscript app_instance_permissions

# HELM deployment: DJANGO_SUPERUSER_PASSWORD should be an env var within the stackn-studio pod
# python manage.py createsuperuser --email $DJANGO_SUPERUSER_EMAIL --username $DJANGO_SUPERUSER --no-input

# ONLY for local testing with docker-compose
#python manage.py createsuperuser --email 'admin@test.com' --username 'admin' --no-input
python manage.py runscript admin_token
