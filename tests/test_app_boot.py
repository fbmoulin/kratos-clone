"""Boot-time invariants in app.py — config validation that runs at startup.

Currently covers M-4: warn when RATE_LIMIT_STORAGE_URI is in-memory and
WEB_CONCURRENCY indicates multiple gunicorn workers (silent rate-limit
multiplication risk).
"""

from __future__ import annotations

from structlog.testing import capture_logs

from app import _warn_if_rate_limit_misconfigured


def test_no_warning_for_single_worker_with_memory_storage():
    """Default deploy (workers=1, memory://) → silent, no warning."""
    with capture_logs() as logs:
        _warn_if_rate_limit_misconfigured(storage_uri="memory://", workers=1)
    misconfig = [e for e in logs if e.get("event") == "rate_limit_storage_misconfig"]
    assert misconfig == []


def test_no_warning_for_multiworker_with_shared_backend():
    """Multi-worker is fine when storage is a shared backend (Redis)."""
    with capture_logs() as logs:
        _warn_if_rate_limit_misconfigured(storage_uri="redis://cache.internal:6379/0", workers=4)
    misconfig = [e for e in logs if e.get("event") == "rate_limit_storage_misconfig"]
    assert misconfig == []


def test_warning_emitted_for_multiworker_with_memory_storage():
    """The whole point of M-4: warn on the silent footgun."""
    with capture_logs() as logs:
        _warn_if_rate_limit_misconfigured(storage_uri="memory://", workers=4)
    misconfig = [e for e in logs if e.get("event") == "rate_limit_storage_misconfig"]
    assert len(misconfig) == 1
    entry = misconfig[0]
    assert entry["workers"] == 4
    assert entry["storage_uri"] == "memory://"
    assert entry["log_level"] == "warning"
    # Operator-facing kwargs must include both the cause and the fix
    assert "reason" in entry
    assert "fix" in entry


def test_warning_treats_memory_storage_options_as_in_memory():
    """`memory://` URIs may carry options (e.g. `memory://?expiration=60`)."""
    with capture_logs() as logs:
        _warn_if_rate_limit_misconfigured(storage_uri="memory://?option=x", workers=2)
    misconfig = [e for e in logs if e.get("event") == "rate_limit_storage_misconfig"]
    assert len(misconfig) == 1
