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

# Set default PORT environment variable
ENV PORT=8080

# Expose port (Railway/Render will set $PORT)
EXPOSE 8080

# Use shell form to ensure proper variable expansion
CMD ["/bin/bash", "/app/entrypoint.sh"]
