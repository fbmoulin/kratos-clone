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
    misconfig = [e for e in logs if e.get("event") == "rate_limit_storage_misconfigured"]
    assert misconfig == []


def test_no_warning_for_multiworker_with_shared_backend():
    """Multi-worker is fine when storage is a shared backend (Redis)."""
    with capture_logs() as logs:
        _warn_if_rate_limit_misconfigured(storage_uri="redis://cache.internal:6379/0", workers=4)
    misconfig = [e for e in logs if e.get("event") == "rate_limit_storage_misconfigured"]
    assert misconfig == []


def test_warning_emitted_for_multiworker_with_memory_storage():
    """The whole point of M-4: warn on the silent footgun."""
    with capture_logs() as logs:
        _warn_if_rate_limit_misconfigured(storage_uri="memory://", workers=4)
    misconfig = [e for e in logs if e.get("event") == "rate_limit_storage_misconfigured"]
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
    misconfig = [e for e in logs if e.get("event") == "rate_limit_storage_misconfigured"]
    assert len(misconfig) == 1


def test_warning_emitted_for_async_memory_backend():
    """Flask-Limiter's `async+memory://` has the same per-process bucket problem."""
    with capture_logs() as logs:
        _warn_if_rate_limit_misconfigured(storage_uri="async+memory://", workers=4)
    misconfig = [e for e in logs if e.get("event") == "rate_limit_storage_misconfigured"]
    assert len(misconfig) == 1
    assert misconfig[0]["storage_uri"] == "async+memory://"


def test_create_app_survives_nonnumeric_web_concurrency(monkeypatch):
    """A non-numeric WEB_CONCURRENCY (e.g. 'auto', '') must not abort boot.

    Regression guard: the M-4 check parses WEB_CONCURRENCY with int(); a raw
    parse would raise ValueError and take down startup on platforms that set
    it to a non-integer. Boot must survive and fall back to 1 worker.
    """
    import app as app_module

    monkeypatch.setenv("WEB_CONCURRENCY", "auto")
    with capture_logs() as logs:
        app_module.create_app(start_janitor=False, run_boot_cleanup=False)
    parse_fail = [e for e in logs if e.get("event") == "web_concurrency_parse_failed"]
    assert len(parse_fail) == 1
    assert parse_fail[0]["provided"] == "auto"
    assert parse_fail[0]["fallback"] == 1


def test_create_app_rejects_zero_workers(monkeypatch):
    """WEB_CONCURRENCY=0 parses cleanly as int but is invalid — fall back."""
    import app as app_module

    monkeypatch.setenv("WEB_CONCURRENCY", "0")
    with capture_logs() as logs:
        app_module.create_app(start_janitor=False, run_boot_cleanup=False)
    parse_fail = [e for e in logs if e.get("event") == "web_concurrency_parse_failed"]
    assert len(parse_fail) == 1
    assert parse_fail[0]["provided"] == "0"


def test_create_app_rejects_negative_workers(monkeypatch):
    """WEB_CONCURRENCY=-1 parses cleanly as int but is invalid — fall back."""
    import app as app_module

    monkeypatch.setenv("WEB_CONCURRENCY", "-1")
    with capture_logs() as logs:
        app_module.create_app(start_janitor=False, run_boot_cleanup=False)
    parse_fail = [e for e in logs if e.get("event") == "web_concurrency_parse_failed"]
    assert len(parse_fail) == 1
    assert parse_fail[0]["provided"] == "-1"


def test_create_app_treats_empty_web_concurrency_as_default(monkeypatch):
    """WEB_CONCURRENCY='' (set-but-empty) should be silent like unset, not 'parse failed'."""
    import app as app_module

    monkeypatch.setenv("WEB_CONCURRENCY", "")
    with capture_logs() as logs:
        app_module.create_app(start_janitor=False, run_boot_cleanup=False)
    parse_fail = [e for e in logs if e.get("event") == "web_concurrency_parse_failed"]
    assert parse_fail == []
