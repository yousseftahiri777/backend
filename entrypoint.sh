#!/bin/bash
set -e

echo "=== DATABASE_URL check ==="
if [ -z "$DATABASE_URL" ]; then
  echo "ERROR: DATABASE_URL is not set!"
  exit 1
fi
echo "DATABASE_URL is set (host: $(echo $DATABASE_URL | sed 's/.*@//' | sed 's/\/.*//'))"

echo "=== Running database migrations ==="
alembic upgrade head

echo "=== Starting uvicorn server ==="
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2
