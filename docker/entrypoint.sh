#!/bin/sh
# Container entrypoint.
#
# Kept intentionally small and explicit:
#   1. wait for the database to accept connections (compose healthchecks can still race a TCP answer),
#   2. collect static files into the shared volume Nginx serves,
#   3. optionally apply migrations (ENABLE_MIGRATIONS=1, off by default in production),
#   4. exec the container command so signals (SIGTERM) reach gunicorn/celery directly.
set -eu

echo "[entrypoint] waiting for database at ${POSTGRES_HOST:-db}:${POSTGRES_PORT:-5432} ..."
attempt=0
until python - <<'PY'
import os
import sys

import psycopg

try:
    psycopg.connect(
        dbname=os.environ.get("POSTGRES_DB", "eng_tracker"),
        user=os.environ.get("POSTGRES_USER", "eng_tracker"),
        password=os.environ.get("POSTGRES_PASSWORD", ""),
        host=os.environ.get("POSTGRES_HOST", "db"),
        port=os.environ.get("POSTGRES_PORT", "5432"),
        connect_timeout=3,
    ).close()
except Exception:
    sys.exit(1)
PY
do
  attempt=$((attempt + 1))
  if [ "$attempt" -ge 40 ]; then
    echo "[entrypoint] database did not become available; giving up" >&2
    exit 1
  fi
  sleep 2
done
echo "[entrypoint] database is reachable"

if [ "${COLLECTSTATIC:-1}" = "1" ]; then
  echo "[entrypoint] collecting static files"
  python manage.py collectstatic --noinput --clear
fi

if [ "${ENABLE_MIGRATIONS:-0}" = "1" ]; then
  echo "[entrypoint] applying migrations"
  python manage.py migrate --noinput
fi

if [ "${ENSURE_STORAGE_BUCKET:-1}" = "1" ]; then
  echo "[entrypoint] ensuring the object-storage bucket exists"
  # Idempotent, and a no-op when STORAGE_BACKEND=local. Failing here (rather than on the first
  # upload) turns a misconfigured endpoint into a startup error with a clear message.
  python manage.py ensure_storage_bucket --quiet || {
    echo "[entrypoint] WARNING: could not verify the storage bucket; uploads may fail" >&2
  }
fi

echo "[entrypoint] starting: $*"
exec "$@"