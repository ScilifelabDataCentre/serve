#!/bin/bash
set -e

# Giving time to studio container to run DB migrations
sleep 25

CELERY_LOG_LEVEL=${CELERY_LOG_LEVEL:-info}
echo "Starting celery worker at log level: ${CELERY_LOG_LEVEL}"

if $DEBUG ; then
    watchmedo auto-restart -R --patterns="*.py" -- celery -A studio worker -l "${CELERY_LOG_LEVEL}" --scheduler django
else
    celery -A studio worker -l "${CELERY_LOG_LEVEL}" --scheduler django
fi
