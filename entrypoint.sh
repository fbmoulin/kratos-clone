#!/bin/bash
set -e

# Railway/Render expose the public port via $PORT. Default to 8080 locally.
PORT="${PORT:-8080}"

echo "Starting gunicorn on port ${PORT}..."

# Single worker on purpose: each download spawns a Chromium instance
# (~150-300MB) and holds response bodies in RAM. Multiple workers would
# multiply memory usage and easily blow the 512MB Railway free-tier limit.
# Threads handle SSE long-poll while a download runs in another thread.
exec gunicorn wsgi:app \
    --bind "0.0.0.0:${PORT}" \
    --workers 1 \
    --threads 4 \
    --timeout 600 \
    --graceful-timeout 30 \
    --max-requests 50 \
    --max-requests-jitter 10 \
    --worker-class gthread \
    --access-logfile - \
    --error-logfile -
