#!/bin/sh
set -e

mkdir -p /app/data
python manage.py migrate --noinput
python manage.py collectstatic --noinput >/dev/null 2>&1 || true

if [ -n "${DJANGO_SUPERUSER_USERNAME:-}" ] && [ -n "${DJANGO_SUPERUSER_PASSWORD:-}" ]; then
  # --email sempre presente: o Django 5.2 recusa --noinput sem ele. O erro
  # aparece no log em vez de sumir, e o container continua subindo.
  python manage.py createsuperuser --noinput --email "${DJANGO_SUPERUSER_EMAIL:-}" \
    || echo "AVISO: nao foi possivel criar o superusuario (veja o erro acima)." >&2
fi

exec "$@"
