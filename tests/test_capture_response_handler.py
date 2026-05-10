"""P2-12: authenticated response skip + octet-stream warning.

Tests for ``HardenedCapture._on_response`` covering:

* Responses whose originating request carried an ``Authorization`` header
  are dropped before the body is fetched (no double-charge to disk caps,
  no leaked secrets in ``captured_assets``).
* The skip is counted on ``_authed_skipped`` and surfaces in the manifest.
* The auth-skip log line fires exactly once (one-shot guard).
* Capturing an ``application/octet-stream`` body emits a one-shot warning.
* Unauthenticated responses still flow through to the existing capture path.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from kratos_clone.capture import CaptureConfig, HardenedCapture


def _make_capture(tmp_path: Path) -> HardenedCapture:
    cfg = CaptureConfig()
    cap = HardenedCapture("https://example.com/", str(tmp_path), cfg)
    # ``run()`` would normally create assets_dir; we have to make it ourselves
    # because we are exercising ``_on_response`` in isolation.
    cap.assets_dir.mkdir(parents=True, exist_ok=True)
    return cap


def _make_response(*, url, ctype, body=b"x", status=200, request_headers=None):
    """Build a Playwright-Response-shaped mock."""
    req = MagicMock()
    req.all_headers = AsyncMock(return_value=request_headers or {})
    req.headers = request_headers or {}
    resp = MagicMock()
    resp.url = url
    resp.status = status
    resp.headers = {"content-type": ctype}
    resp.request = req
    resp.body = AsyncMock(return_value=body)
    return resp


@pytest.mark.asyncio
async def test_skips_authed_response(tmp_path):
    cap = _make_capture(tmp_path)
    resp = _make_response(
        url="https://example.com/private.js",
        ctype="application/javascript",
        request_headers={"authorization": "Bearer secret"},
    )
    await cap._on_response(resp)
    assert cap._authed_skipped == 1
    assert resp.url not in cap.captured_assets
    # body() must not have been awaited (skip happens before body fetch)
    resp.body.assert_not_called()


@pytest.mark.asyncio
async def test_authed_skip_counts_multiple(tmp_path):
    cap = _make_capture(tmp_path)
    for i in range(3):
        resp = _make_response(
            url=f"https://example.com/p{i}.js",
            ctype="application/javascript",
            request_headers={"Authorization": "Bearer x"},
        )
        await cap._on_response(resp)
    assert cap._authed_skipped == 3


@pytest.mark.asyncio
async def test_unauthed_response_captured(tmp_path):
    cap = _make_capture(tmp_path)
    resp = _make_response(
        url="https://example.com/app.js",
        ctype="application/javascript",
        body=b"console.log(1);",
        request_headers={},
    )
    await cap._on_response(resp)
    assert cap._authed_skipped == 0
    assert "https://example.com/app.js" in cap.captured_assets


@pytest.mark.asyncio
async def test_octet_stream_warns_once(tmp_path):
    cap = _make_capture(tmp_path)
    logged: list[str] = []
    cap.log = lambda msg: logged.append(msg)
    for i in range(3):
        resp = _make_response(
            url=f"https://example.com/blob{i}.bin",
            ctype="application/octet-stream",
            body=b"\x00\x01",
            request_headers={},
        )
        await cap._on_response(resp)
    octet_warnings = [m for m in logged if "octet-stream" in m]
    assert len(octet_warnings) == 1, f"expected exactly one warning, got {octet_warnings}"
    assert cap._octet_stream_warned is True


@pytest.mark.asyncio
async def test_authed_skip_warns_once(tmp_path):
    cap = _make_capture(tmp_path)
    logged: list[str] = []
    cap.log = lambda msg: logged.append(msg)
    for i in range(3):
        resp = _make_response(
            url=f"https://example.com/p{i}.js",
            ctype="application/javascript",
            request_headers={"authorization": "Bearer x"},
        )
        await cap._on_response(resp)
    auth_warnings = [m for m in logged if "Authorization" in m or "authenticated" in m.lower()]
    assert len(auth_warnings) == 1


@pytest.mark.asyncio
async def test_authed_skip_counted_in_manifest_field(tmp_path):
    """The new ``_authed_skipped`` counter is the source for the manifest field."""
    cap = _make_capture(tmp_path)
    resp = _make_response(
        url="https://example.com/secret.js",
        ctype="application/javascript",
        request_headers={"authorization": "Bearer x"},
    )
    await cap._on_response(resp)
    # Mirror what ``run()`` writes into manifest.json.
    assert cap._authed_skipped == 1
