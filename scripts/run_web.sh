#!/bin/bash

# If we have set a local, custom settings.py, then use that.
#[ -f studio/local_settings.py ] && echo "Using local settings file" && export DJANGO_SETTINGS_MODULE=studio.local_settings

# To allow setting up fixtures and init DB data for only the first time
if $INIT; then
    # Run the dedicated initialization script for all DB related commands
    sh scripts/init_run_web.sh
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
