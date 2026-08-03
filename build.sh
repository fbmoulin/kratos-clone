#!/usr/bin/env bash
set -e

# NOTE — this script has no live consumer. Both documented deploy paths build from
# the Dockerfile: Render (render.yaml sets `env: docker`, and Render's docs state you
# cannot customise the build command) and Railway (per RAILWAY_DEPLOY.md, it detects
# the Dockerfile). It is kept, and kept correct, because "it is dead code" is exactly
# the belief that decays — and a script that installs from a file the repo no longer
# has is a trap for whoever runs it next.

echo "Installing Python dependencies from uv.lock..."
# --locked, never --frozen: --frozen exits 0 on a pyproject/lock mismatch and installs
# the version that violates the declared constraint. --no-dev keeps this to the
# runtime set, matching the Dockerfile.
uv sync --locked --no-dev

echo "Installing Playwright Chromium..."
# Via `uv run` so it resolves the Playwright inside .venv, not a stray global one.
uv run playwright install chromium

echo "Attempting to install system dependencies (may fail, that's ok)..."
uv run playwright install-deps chromium || echo "System deps install failed, continuing..."

echo "Build completed successfully!"
