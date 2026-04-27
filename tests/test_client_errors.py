"""Coverage for /api/client-errors — the frontend error ingestion endpoint.

Phase 1 of ROADMAP. Lifts the 5 inline assertions from .github/workflows/ci.yml
into proper pytest cases + adds regression tests for the CodeRabbit/Gemini fixes
shipped in PR #1 (RFC 9110 204-no-body, AttributeError on list-body, critical
level whitelist, oversized payload rejection).
"""

from __future__ import annotations
import pytest


# ── Happy path ──────────────────────────────────────────────────────────────


def test_valid_single_entry_returns_200_accepted_1(client):
    resp = client.post(
        "/api/client-errors",
        json={"entries": [{"level": "error", "event": "boom", "message": "test"}]},
    )
    assert resp.status_code == 200
    assert resp.get_json() == {"accepted": 1}


def test_valid_multiple_entries(client):
    """Up to _FRONTEND_MAX_ENTRIES_PER_REQUEST (20) entries accepted."""
    entries = [{"level": "error", "event": "e", "message": f"m{i}"} for i in range(5)]
    resp = client.post("/api/client-errors", json={"entries": entries})
    assert resp.status_code == 200
    assert resp.get_json()["accepted"] == 5


def test_entries_truncated_at_20(client):
    """Caller sends 30 → server processes 20 only (regression for cap)."""
    entries = [{"level": "error", "event": "e", "message": f"m{i}"} for i in range(30)]
    resp = client.post("/api/client-errors", json={"entries": entries})
    assert resp.status_code == 200
    assert resp.get_json()["accepted"] == 20


# ── RFC 9110 §15.3.5 enforcement (no body on 204) ────────────────────────────


def test_empty_entries_returns_204_with_no_body(client):
    """Zero accepted entries → 204 with EMPTY body, never a JSON payload."""
    resp = client.post("/api/client-errors", json={"entries": []})
    assert resp.status_code == 204
    assert resp.data == b""


def test_missing_entries_key_returns_204(client):
    """Body is dict but no 'entries' key → 204 (no work to do)."""
    resp = client.post("/api/client-errors", json={"foo": "bar"})
    assert resp.status_code == 204
    assert resp.data == b""


def test_bad_json_returns_204(client):
    """Invalid JSON parses silently to None → 204 (RFC compliance)."""
    resp = client.post(
        "/api/client-errors", data="not json", content_type="application/json"
    )
    assert resp.status_code == 204
    assert resp.data == b""


# ── Regression for AttributeError on non-dict body (CodeRabbit P1) ──────────


def test_list_body_does_not_crash(client):
    """body=[] used to raise AttributeError on body.get() — must NOT 500."""
    resp = client.post("/api/client-errors", json=[])
    assert resp.status_code == 204
    assert resp.data == b""


def test_string_body_does_not_crash(client):
    """body='string' is not a dict → 204."""
    resp = client.post("/api/client-errors", json="just a string")
    assert resp.status_code == 204


def test_null_body_does_not_crash(client):
    """body=null parses to None, isinstance check trips, returns 204 (no body)."""
    resp = client.post("/api/client-errors", json=None)
    assert resp.status_code == 204
    assert resp.data == b""


# ── Validation: invalid shapes ──────────────────────────────────────────────


def test_entries_as_string_returns_400(client):
    """body={'entries': 'not a list'} — invalid shape → 400."""
    resp = client.post("/api/client-errors", json={"entries": "not a list"})
    assert resp.status_code == 400


def test_entries_as_dict_returns_400(client):
    """body={'entries': {}} — invalid shape → 400."""
    resp = client.post("/api/client-errors", json={"entries": {}})
    assert resp.status_code == 400


# ── Level whitelist (regression for 'critical' rejection) ────────────────────


@pytest.mark.parametrize("level", ["debug", "info", "warning", "error", "critical"])
def test_all_valid_levels_accepted(client, level):
    resp = client.post(
        "/api/client-errors",
        json={"entries": [{"level": level, "event": "x", "message": "m"}]},
    )
    assert resp.status_code == 200
    assert resp.get_json()["accepted"] == 1


def test_invalid_level_coerced_to_error(client):
    """Unknown level → still accepted, coerced to 'error' internally."""
    resp = client.post(
        "/api/client-errors",
        json={"entries": [{"level": "INVALID_LEVEL", "event": "x", "message": "m"}]},
    )
    assert resp.status_code == 200
    assert resp.get_json()["accepted"] == 1


def test_dunder_level_does_not_invoke_special_method(client):
    """Defense in depth: even if level whitelist is bypassed, getattr fallback
    must not invoke __class__/__init__ etc. on the logger.

    The actual mitigation is the `level not in (...)` check before `getattr`.
    """
    resp = client.post(
        "/api/client-errors",
        json={"entries": [{"level": "__class__", "event": "x", "message": "m"}]},
    )
    # Should be coerced to 'error' and accepted normally
    assert resp.status_code == 200


# ── Body size enforcement ───────────────────────────────────────────────────


def test_body_under_per_route_cap_accepted(client):
    """31 KB body is accepted (under 32 KB per-route cap)."""
    big_msg = "x" * 30_000
    resp = client.post(
        "/api/client-errors",
        json={"entries": [{"level": "error", "event": "big", "message": big_msg}]},
    )
    # Accepted; message gets truncated by _truncate but entry counted
    assert resp.status_code == 200


def test_body_over_per_route_cap_rejected_413(client):
    """50 KB body exceeds 32 KB per-route cap → 413."""
    resp = client.post(
        "/api/client-errors", data="x" * 50_000, content_type="application/json"
    )
    assert resp.status_code == 413


def test_body_over_app_cap_rejected_413(client):
    """2 MiB body exceeds the app-wide 1 MiB MAX_CONTENT_LENGTH → 413."""
    resp = client.post(
        "/api/client-errors",
        data="x" * (2 * 1024 * 1024),
        content_type="application/json",
    )
    assert resp.status_code == 413


# ── Field truncation (private but worth locking down) ───────────────────────


def test_long_field_does_not_crash_endpoint(client):
    """A 5K char message gets _truncate'd to 2K — endpoint still 200."""
    big = "x" * 5_000  # under per-route cap, way over per-field cap (2KB)
    resp = client.post(
        "/api/client-errors",
        json={"entries": [{"level": "error", "event": "x", "message": big}]},
    )
    assert resp.status_code == 200
    assert resp.get_json()["accepted"] == 1
