#!/usr/bin/env bash
# Regenerate requirements.txt after a dependency change.
#
# Why this exists: requirements.txt is generated from uv.lock and is what
# Dockerfile installs, so the two must agree. Dependabot's uv ecosystem updates
# pyproject.toml and uv.lock; the export must then be refreshed.
#
# Usage:
#   scripts/relock.sh                      # reconcile the lock with pyproject.toml
#   scripts/relock.sh certifi anyio ...    # additionally advance the named packages
#
# WHICH packages to name — measured 2026-08-02 on PR #70, and it is the opposite of
# the obvious guess. When the CI drift guard fails on a dependabot PR, name the
# TRANSITIVE packages the diff shows as drifted, NOT the direct dependencies the PR
# bumps. `uv lock --upgrade-package` resolves each name to the LATEST version its
# constraint allows, not to the version the PR declares — so naming a direct dep
# overshoots the PR you are trying to land. Measured: naming `openai playwright` on
# PR #70 moved them to 2.52.0 and 1.62.0, past the 2.50.0 / 1.61.0 that PR was
# reviewed for. Copy the drifted names straight out of the guard's own diff.
#
# And do NOT "fix" a red guard by running `uv export` alone. It regenerates from the
# lock, so it resolves the mismatch in the wrong direction and DOWNGRADES every
# transitive dependabot advanced — measured on PR #70: 12 packages, `certifi` (the CA
# trust store) among them.
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
