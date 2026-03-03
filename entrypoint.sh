#!/bin/sh
set -e

# Apply database migrations
echo "Running migrations..."
python manage.py migrate --noinput

# Collect static files
echo "Collecting static files..."
python manage.py collectstatic --noinput || true

exec "$@"
