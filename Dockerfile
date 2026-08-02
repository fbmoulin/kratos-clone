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

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers and dependencies
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
# each layer beneath it, so placing it above the pip and playwright installs would
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
