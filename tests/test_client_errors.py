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
    resp = client.post("/api/client-errors", data="not json", content_type="application/json")
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


# ── Content-type enforcement (P2-3) ─────────────────────────────────────────


def test_text_plain_rejected_415(client):
    """Pre-Phase-3, force=True allowed text/plain to bypass CORS preflight.

    Now must be application/json.
    """
    resp = client.post("/api/client-errors", data='{"entries":[]}', content_type="text/plain")
    assert resp.status_code == 415
    assert resp.get_json()["error"] == "content-type must be application/json"


def test_no_content_type_accepted(client):
    """Empty content-type still accepted (browsers omit it for sendBeacon)."""
    resp = client.post("/api/client-errors", data='{"entries":[]}', content_type="")
    # Empty content-type → no rejection (some clients don't set it)
    assert resp.status_code in (204, 200)


def test_json_with_charset_accepted(client):
    """`application/json; charset=utf-8` is valid (split on `;`)."""
    resp = client.post(
        "/api/client-errors",
        data='{"entries":[{"level":"error","event":"e","message":"m"}]}',
        content_type="application/json; charset=utf-8",
    )
    assert resp.status_code == 200


# ── PII strip (P1-I) ────────────────────────────────────────────────────────


def test_url_query_string_not_logged(client):
    """URL with ?token=xyz should be stripped to scheme+host+path before logging."""
    # We don't directly inspect the log here — this just ensures the endpoint
    # doesn't crash when a URL with query string is sent. The PII strip happens
    # inside `_strip_query` which is unit-tested below.
    resp = client.post(
        "/api/client-errors",
        json={
            "entries": [
                {
                    "level": "error",
                    "event": "x",
                    "message": "m",
                    "url": "https://app.example.com/dashboard?token=secret&user=42",
                }
            ]
        },
    )
    assert resp.status_code == 200


def test_strip_query_helper():
    """Direct unit test of _strip_query: removes query + fragment, preserves base."""
    from app import _strip_query

    assert _strip_query("https://x.com/a?b=c") == "https://x.com/a"
    assert _strip_query("https://x.com/a#frag") == "https://x.com/a"
    assert _strip_query("https://x.com/a?b=c#d") == "https://x.com/a"
    assert _strip_query("https://x.com/no-query") == "https://x.com/no-query"
    assert _strip_query(None) is None
    assert _strip_query("") is None


# ── ANSI escape sanitization (P2-4) ─────────────────────────────────────────


def test_ansi_escape_sanitized_in_message(client):
    """Malicious ANSI escape from browser entry must NOT reach the console."""
    resp = client.post(
        "/api/client-errors",
        json={
            "entries": [
                {
                    "level": "error",
                    "event": "x",
                    # \x1b[2J\x1b[H clears screen + cursor home
                    "message": "boom\x1b[2J\x1b[H",
                }
            ]
        },
    )
    assert resp.status_code == 200


def test_truncate_strips_control_chars():
    """_truncate replaces all C0 control chars (incl. \\x1b for ANSI) with `?`."""
    from app import _truncate

    out = _truncate("safe\x1b[2Jrest")
    assert "\x1b" not in out
    assert "?" in out


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
    resp = client.post("/api/client-errors", data="x" * 50_000, content_type="application/json")
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
