#!/bin/bash
set -e

# Giving time to studio container to run DB migrations
sleep 25

CELERY_LOG_LEVEL=${CELERY_LOG_LEVEL:-info}
echo "Starting celery worker at log level: ${CELERY_LOG_LEVEL}"

# Bound the number of prefork worker processes. Each child opens its own psycopg
# connection pool (see DATABASES.OPTIONS.pool in studio/settings.py), so leaving this
# at Celery's default (= CPU count) can exhaust Postgres max_connections.
CELERY_CONCURRENCY=${CELERY_CONCURRENCY:-4}
echo "Starting celery worker with concurrency: ${CELERY_CONCURRENCY}"

if $DEBUG ; then
    watchmedo auto-restart -R --patterns="*.py" -- celery -A studio worker -l "${CELERY_LOG_LEVEL}" --scheduler django --concurrency="${CELERY_CONCURRENCY}"
else
    celery -A studio worker -l "${CELERY_LOG_LEVEL}" --scheduler django --concurrency="${CELERY_CONCURRENCY}"
fi
