#!/bin/bash
set -e

# Railway/Render expose the public port via $PORT. Default to 8080 locally.
PORT="${PORT:-8080}"

echo "Starting gunicorn on port ${PORT}..."

# Single worker on purpose: each download spawns a Chromium instance
# (~150-300MB) and holds response bodies in RAM. Multiple workers would
# multiply memory usage and easily blow the 512MB Railway free-tier limit.
# Threads handle SSE long-poll while a download runs in another thread.
#
# WEB_CONCURRENCY is the gunicorn-standard env var (also used by Render and
# Heroku) — surfaced here so create_app() can read it and warn at boot if
# operators scale to >1 worker without also pointing RATE_LIMIT_STORAGE_URI
# at a shared backend (M-4 mitigation).
#
# Pre-validate before handing to gunicorn: gunicorn's own --workers parser
# rejects non-numeric values with a cryptic argparse error; catching it here
# gives an actionable message AND lets the app boot with a safe fallback
# (paired with create_app's Python-side guard for non-gunicorn entrypoints).
#
# NOTE: do NOT override --workers via GUNICORN_CMD_ARGS — set WEB_CONCURRENCY
# instead. The Python boot check (M-4) reads WEB_CONCURRENCY only; a CLI
# override via GUNICORN_CMD_ARGS would diverge silently from what Python sees.
WEB_CONCURRENCY="${WEB_CONCURRENCY:-1}"
if ! [[ "${WEB_CONCURRENCY}" =~ ^[1-9][0-9]*$ ]]; then
    echo "entrypoint: WEB_CONCURRENCY must be a positive integer; got '${WEB_CONCURRENCY}'. Falling back to 1." >&2
    WEB_CONCURRENCY=1
fi
export WEB_CONCURRENCY
exec gunicorn wsgi:app \
    --bind "0.0.0.0:${PORT}" \
    --workers "${WEB_CONCURRENCY}" \
    --threads 4 \
    --timeout 600 \
    --graceful-timeout 30 \
    --max-requests 50 \
    --max-requests-jitter 10 \
    --worker-class gthread \
    --access-logfile - \
    --error-logfile -
