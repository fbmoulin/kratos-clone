#!/usr/bin/env bash
# Regenerate requirements.txt after a dependency change.
#
# Why this exists: requirements.txt is generated from uv.lock and is what
# Dockerfile installs, so the two must agree. Dependabot's uv ecosystem updates
# pyproject.toml and uv.lock; the export must then be refreshed.
#
# Usage:
#   scripts/relock.sh                 # reconcile the lock with pyproject.toml
#   scripts/relock.sh pillow openai   # additionally advance only the named packages
#
# NEVER run `uv lock --upgrade` for this: it re-resolves every package in the lock
# (measured: 24 version changes on this repo, including the mypy and ruff that gate
# CI), turning a one-package security bump into an unreviewed toolchain swap.
set -euo pipefail

cd "$(dirname "$0")/.."

# `uv lock --upgrade-package NAME` is a resolution hint ("ignore this package's
# existing pin"), not a lookup. Measured on uv 0.10.12: it exits 0 for a name that
# is in neither uv.lock nor pyproject.toml. A typo therefore produces a successful
# run and an empty diff, which reads exactly like "already up to date". Reject
# unknown names up front so the operator sees the typo instead of a false all-clear.
assert_in_lock() {
  local pkg="$1" normalized
  # PEP 503 normalisation: lowercase, and any run of - _ . collapses to a single -
  normalized=$(printf '%s' "$pkg" | tr '[:upper:]' '[:lower:]' | sed -E 's/[-_.]+/-/g')
  if ! grep -qE "^name = \"${normalized}\"$" uv.lock; then
    echo "error: '${pkg}' is not in uv.lock, so there is nothing to upgrade." >&2
    echo "       Check the spelling, or add the dependency to pyproject.toml first." >&2
    exit 1
  fi
}

if [ "$#" -gt 0 ]; then
  for pkg in "$@"; do
    assert_in_lock "$pkg"
  done
  for pkg in "$@"; do
    echo "==> uv lock --upgrade-package $pkg"
    uv lock --upgrade-package "$pkg"
  done
else
  echo "==> uv lock"
  uv lock
fi

echo "==> uv export --locked"
uv export --locked --format requirements-txt --no-dev --no-emit-project --no-hashes \
  -o requirements.txt

echo "==> git diff --stat"
git --no-pager diff --stat uv.lock requirements.txt
echo
echo "Review the diff above. If it is larger than the PR it belongs to, you ran too wide a"
echo "scope — reset and pass explicit package names."
