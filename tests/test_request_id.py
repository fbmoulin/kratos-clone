"""Tests for the request_id middleware."""

from __future__ import annotations

import re

UUID4_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")


def test_generates_id_when_header_missing(client):
    resp = client.get("/health")
    rid = resp.headers.get("X-Request-ID")
    assert rid is not None, "X-Request-ID header must be set"
    assert UUID4_RE.match(rid), f"expected UUID4 format, got {rid!r}"


def test_propagates_id_from_request_header(client):
    rid_in = "11111111-2222-4333-8444-555555555555"
    resp = client.get("/health", headers={"X-Request-ID": rid_in})
    assert resp.headers.get("X-Request-ID") == rid_in


def test_safe_request_id_rejects_unsafe_chars():
    """Direct unit test — Werkzeug refuses to even send headers with \\r\\n,
    so the middleware's defense-in-depth regex is unreachable end-to-end.
    We still verify the helper directly so the regex stays correct."""
    from app import _safe_request_id

    # Spaces, semicolons, etc. trigger the fallback to a fresh UUID4.
    out = _safe_request_id("inj ect ; rm -rf /")
    assert UUID4_RE.match(out)
    out = _safe_request_id("with spaces")
    assert UUID4_RE.match(out)
    out = _safe_request_id(None)
    assert UUID4_RE.match(out)
    # A safe id passes through unchanged.
    safe = "abc123_-XYZ"
    assert _safe_request_id(safe) == safe


def test_caps_id_length(client):
    long_id = "a" * 200
    resp = client.get("/health", headers={"X-Request-ID": long_id})
    rid = resp.headers.get("X-Request-ID")
    assert rid is not None
    assert len(rid) <= 64


def test_unique_ids_across_requests(client):
    rids = {client.get("/health").headers.get("X-Request-ID") for _ in range(5)}
    assert len(rids) == 5
