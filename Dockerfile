# Use official Python base image. Pinned to 3.12 to match pyproject
# `requires-python = ">=3.12"` and the CI matrix (3.12) — prod must run the
# same interpreter the test suite + mypy strict gate validate against.
FROM python:3.12-slim-bookworm

# Install system dependencies for Playwright
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# The uv binary, pinned BY DIGEST rather than by tag. Same reasoning as the
# SHA-pinned astral-sh/setup-uv in CI: a re-pointed tag would silently change what
# runs during the build. This is the multi-arch index digest for 0.12.1 (resolved
# 2026-08-03), so it stays correct on both amd64 and arm64; the four per-arch
# manifest digests are deliberately NOT what is pinned here.
# Version 0.12.1 matches the pin in .github/workflows/ci.yml — keep them together.
COPY --from=ghcr.io/astral-sh/uv:0.12.1@sha256:cf4eedcaa81655197f625739489effcbe71b61ceb1506f332c3facae5deceded /uv /uvx /bin/

# Use the base image's interpreter, never a uv-managed download. Without this uv may
# fetch its own CPython, which would (a) grow the image and (b) mean the container
# runs an interpreter the CI matrix and the mypy strict gate never validated. With
# it, a missing/incompatible system Python fails the build loudly instead.
ENV UV_PYTHON_DOWNLOADS=never

# Dependency manifests only, BEFORE the source, so this layer caches independently
# of code changes. uv.lock is the install source — see .dockerignore, which must
# keep letting it through.
COPY pyproject.toml uv.lock .python-version ./

# Install runtime dependencies from the lock into /app/.venv.
#
# `--locked`, never `--frozen`: --frozen exits 0 on a pyproject/lock mismatch and
# installs the version that violates the declared constraint (reproduced in a
# disposable worktree). Same contract every CI job uses.
#
# `--no-dev` matches what the retired requirements.txt was exported with, so the
# runtime package set is unchanged by this switch — measured, 42 packages either way
# on Linux.
#
# One sync, not the two from Astral's guide: that pattern's second step installs the
# PROJECT itself, and pyproject.toml sets `package = false`. Measured on this repo, a
# second `uv sync` after `COPY . .` reports "Checked 42 packages" and installs
# nothing. WORKDIR /app puts the source on sys.path and every module is top-level, so
# nothing needs the project pip-installed.
RUN uv sync --locked --no-dev

# 🔴 Load-bearing, and the failure it prevents is runtime-only and silent.
# entrypoint.sh calls BARE `gunicorn`. uv installs console scripts into
# /app/.venv/bin, not into the system prefix, so without this the image builds green
# and the container dies the moment it starts.
#
# Consequence for operators: `docker exec <c> pip install X` is now a silent no-op —
# `pip` still resolves to /usr/local/bin/pip (system site-packages) while `python`
# resolves to /app/.venv/bin/python, so the package installs somewhere the app never
# reads. The correct form is:
#   docker exec <c> uv pip install --python /app/.venv/bin/python X
#
# Note also that /app/.venv/bin/python is a SYMLINK to /usr/local/bin/python3.12. It
# works because the target lives in this same image. A future multi-stage build that
# copies only /app/.venv into a different final stage would produce a dangling
# symlink unless that stage uses this same base image.
ENV PATH="/app/.venv/bin:$PATH"

# Install Playwright browsers and dependencies.
#
# Ordering is load-bearing twice over: this must run AFTER the venv is on PATH (or it
# resolves a different Python and installs the browser where the app cannot find it),
# and while still root (`--with-deps` shells out to apt).
#
# ⚠️ Coupling with a known audit finding: docs/AUDIT.md carries a P3 for this image
# having no USER directive. Adding a non-root USER without also moving this line
# above it will break the build.
RUN playwright install --with-deps chromium

# Copy application files
COPY . .

# Create downloads directory
RUN mkdir -p downloads

# Copy and set entrypoint script
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Build identity, surfaced by /health so a 200 proves WHICH commit is answering.
# Pass it at build time:
#   docker build --build-arg GIT_SHA="$(git rev-parse HEAD)" .
# Declared here, below every COPY, on purpose: an ARG invalidates the build cache for
# each layer beneath it, so placing it above the uv sync and playwright installs would
# rebuild those on every commit. Left empty by default — app.py treats a blank value
# as unset and falls through to the platform's own variable, then to "unknown".
ARG GIT_SHA=""
ENV KC_BUILD_SHA=$GIT_SHA

# Set default PORT environment variable
ENV PORT=8080

# Expose port (Railway/Render will set $PORT)
EXPOSE 8080

# Use shell form to ensure proper variable expansion
CMD ["/bin/bash", "/app/entrypoint.sh"]
