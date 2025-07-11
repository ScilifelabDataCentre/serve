#!/bin/bash

# If we have set a local, custom settings.py, then use that.
#[ -f studio/local_settings.py ] && echo "Using local settings file" && export DJANGO_SETTINGS_MODULE=studio.local_settings

# To allow setting up fixtures and init DB data for only the first time
if $INIT; then

    if [ -n "${RESET_DB}" ] && [ "${RESET_DB}" = "true" ] && [ -n "${DEBUG}" ] && [ "${DEBUG}" = "true" ]; then
        echo "RESETTING DATABASE..."
        python manage.py reset_db --no-input --close-sessions
        echo "Uninstalling all Helm releases in serve-dev namespace"
        helm uninstall $(helm ls --all --short -n serve-dev) -n serve-dev
    fi

    echo "Running studio migrations..."

    python manage.py makemigrations
    python manage.py migrate

    python manage.py migrate waffle
    python manage.py waffle_flag enable_depictio --create --everyone
    python manage.py waffle_switch docker_image_architecture_validator off --create

    #Replace storageclass in project template fixture
    sed -i "s/microk8s-hostpath/$STUDIO_STORAGECLASS/g" ./fixtures/projects_templates.json

    #Replace accessmode
    sed -i "s/ReadWriteMany/$STUDIO_ACCESSMODE/g" ./fixtures/projects_templates.json
    sed -i "s/ReadWriteMany/$STUDIO_ACCESSMODE/g" ./fixtures/apps_fixtures.json

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
fi

echo "Starting the Studio server..."

if $DEBUG ; then
    python manage.py runserver 0.0.0.0:8080
else
    python -m uvicorn studio.asgi:application --host 0.0.0.0 --port 8080
fi

# Alternative to be used:
# watchmedo auto-restart -R --patterns="*.py" -- daphne studio.asgi:application -b 0.0.0.0 -p 8080
# gunicorn studio.wsgi -b 0.0.0.0:8080 --reload
