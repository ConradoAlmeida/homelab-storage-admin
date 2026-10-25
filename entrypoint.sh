#!/bin/sh
set -e

mkdir -p /app/data
python manage.py migrate --noinput
python manage.py collectstatic --noinput >/dev/null 2>&1 || true

if [ -n "${DJANGO_SUPERUSER_USERNAME:-}" ] && [ -n "${DJANGO_SUPERUSER_PASSWORD:-}" ]; then
  python manage.py createsuperuser --noinput 2>/dev/null || true
fi

exec "$@"
