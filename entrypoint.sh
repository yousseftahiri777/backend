#!/bin/bash
set -e

echo "=== Running database migrations ==="
for i in 1 2 3 4 5; do
  if alembic upgrade head; then
    echo "=== Migrations complete ==="
    break
  fi
  if [ "$i" -eq 5 ]; then
    echo "ERROR: migrations failed after 5 attempts"
    exit 1
  fi
  echo "Migration attempt $i failed — retrying in 5s..."
  sleep 5
done

echo "=== Starting uvicorn server ==="
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2
