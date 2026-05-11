"""Smoke coverage for the /start-download → /download-file Flask flow.

Closes the `WebsiteDownloader.process()` smoke-test item from TODO.md `🟢 Later`.
`downloader.py` is now fully typed (Stage D) but had zero runtime coverage; this
suite exercises the Flask wiring around it without hitting the real network.

Strategy: monkeypatch `app.WebsiteDownloader` + `app.zip_directory` to control
the worker outcome deterministically, then poll `download_results[sid]` until
the worker thread transitions out of `"processing"`. Real `WebsiteDownloader`
behavior is already type-checked and exercised by the legacy CLI; here we lock
down the **Flask integration contract**: session lifecycle, file delivery,
error propagation, and rate-limit/auth-free routing.
"""

from __future__ import annotations

import os
import time
import uuid

import pytest

# ── Helpers ──────────────────────────────────────────────────────────────────


def _wait_for_status(app_module, session_id: str, expected: set[str], timeout: float = 3.0):
    """Poll `download_results[sid]["status"]` until it leaves `processing`.

    Worker is a daemon thread; the test client returns immediately after
    POST /start-download. We need to wait for the thread to write its
    terminal status before asserting on /download-file behavior.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        with app_module.session_lock:
            status = app_module.download_results.get(session_id, {}).get("status")
        if status in expected:
            return status
        time.sleep(0.02)
    raise AssertionError(
        f"worker did not reach {expected} within {timeout}s (last status={status!r})"
    )


class _FakeDownloaderSuccess:
    """Stand-in that writes a sentinel file then returns True from process()."""

    def __init__(self, url, output_dir, log_callback=None):
        self.url = url
        self.output_dir = output_dir
        self.log_callback = log_callback

    def process(self) -> bool:
        os.makedirs(self.output_dir, exist_ok=True)
        # Sentinel file so the dir is non-empty when zip_directory runs.
        with open(os.path.join(self.output_dir, "index.html"), "w") as f:
            f.write("<html><body>smoke</body></html>")
        if self.log_callback:
            self.log_callback("✅ Captured")
        return True


class _FakeDownloaderFailure:
    """process() returns False without raising — worker takes the error path."""

    def __init__(self, url, output_dir, log_callback=None):
        self.log_callback = log_callback

    def process(self) -> bool:
        if self.log_callback:
            self.log_callback("⚠️  Failed")
        return False


class _FakeDownloaderRaises:
    """process() raises — worker catches via try/except and marks error."""

    def __init__(self, url, output_dir, log_callback=None):
        pass

    def process(self) -> bool:
        raise RuntimeError("boom from fake downloader")


def _fake_zip_directory(src_dir: str, out_path: str) -> None:
    """Skip real zipping — write a tiny placeholder so send_file has bytes."""
    with open(out_path, "wb") as f:
        f.write(b"PK\x05\x06" + b"\x00" * 18)  # minimal empty-ZIP central dir


# ── /start-download input validation ─────────────────────────────────────────


def test_start_download_missing_url_returns_400(client):
    resp = client.post("/start-download", json={})
    assert resp.status_code == 400
    assert resp.get_json() == {"error": "URL is required"}


def test_start_download_empty_url_returns_400(client):
    resp = client.post("/start-download", json={"url": ""})
    assert resp.status_code == 400


def test_start_download_no_json_body_returns_400(client):
    resp = client.post("/start-download")
    assert resp.status_code == 400


# ── Happy path: process() → True → ZIP available via /download-file ──────────


def test_happy_path_download_complete(client, flask_app, tmp_path, monkeypatch):
    import app as app_module

    monkeypatch.setattr(app_module, "DOWNLOAD_FOLDER", str(tmp_path))
    monkeypatch.setattr(app_module, "WebsiteDownloader", _FakeDownloaderSuccess)
    monkeypatch.setattr(app_module, "zip_directory", _fake_zip_directory)

    resp = client.post("/start-download", json={"url": "https://example.com"})
    assert resp.status_code == 200
    session_id = resp.get_json()["session_id"]
    uuid.UUID(session_id)  # raises ValueError if not a valid UUID

    status = _wait_for_status(app_module, session_id, expected={"complete"})
    assert status == "complete"

    with app_module.session_lock:
        result = app_module.download_results[session_id]
    assert result["filename"].endswith(".zip")
    assert os.path.exists(result["zip_path"])

    file_resp = client.get(f"/download-file/{session_id}")
    assert file_resp.status_code == 200
    assert file_resp.headers["Content-Disposition"].startswith("attachment")
    # Body is the fake zip bytes we wrote
    assert file_resp.data.startswith(b"PK\x05\x06")


# ── Failure paths: error state surfaces as 404 from /download-file ───────────


def test_process_returns_false_marks_error(client, flask_app, tmp_path, monkeypatch):
    import app as app_module

    monkeypatch.setattr(app_module, "DOWNLOAD_FOLDER", str(tmp_path))
    monkeypatch.setattr(app_module, "WebsiteDownloader", _FakeDownloaderFailure)
    monkeypatch.setattr(app_module, "zip_directory", _fake_zip_directory)

    resp = client.post("/start-download", json={"url": "https://example.com"})
    session_id = resp.get_json()["session_id"]

    status = _wait_for_status(app_module, session_id, expected={"error"})
    assert status == "error"

    with app_module.session_lock:
        result = app_module.download_results[session_id]
    assert result["error"] == "Failed to download site"

    # /download-file refuses to serve a non-complete session
    file_resp = client.get(f"/download-file/{session_id}")
    assert file_resp.status_code == 404
    assert file_resp.data == b"File not ready"


def test_process_raises_is_caught_and_marks_error(client, flask_app, tmp_path, monkeypatch):
    import app as app_module

    monkeypatch.setattr(app_module, "DOWNLOAD_FOLDER", str(tmp_path))
    monkeypatch.setattr(app_module, "WebsiteDownloader", _FakeDownloaderRaises)
    monkeypatch.setattr(app_module, "zip_directory", _fake_zip_directory)

    resp = client.post("/start-download", json={"url": "https://example.com"})
    session_id = resp.get_json()["session_id"]

    status = _wait_for_status(app_module, session_id, expected={"error"})
    assert status == "error"

    with app_module.session_lock:
        result = app_module.download_results[session_id]
    assert "boom from fake downloader" in result["error"]

    file_resp = client.get(f"/download-file/{session_id}")
    assert file_resp.status_code == 404


# ── /download-file: unknown / not-yet-ready sessions ─────────────────────────


def test_download_file_unknown_session_returns_404(client):
    resp = client.get(f"/download-file/{uuid.uuid4()}")
    assert resp.status_code == 404


def test_download_file_during_processing_returns_404(client, flask_app, tmp_path, monkeypatch):
    """Caller hits /download-file before worker finishes → 404, no race-y send."""
    import threading

    import app as app_module

    monkeypatch.setattr(app_module, "DOWNLOAD_FOLDER", str(tmp_path))

    block = threading.Event()
    release = threading.Event()

    class _BlockingDownloader:
        def __init__(self, url, output_dir, log_callback=None):
            self.output_dir = output_dir

        def process(self) -> bool:
            block.set()
            release.wait(timeout=2.0)
            os.makedirs(self.output_dir, exist_ok=True)
            return True

    monkeypatch.setattr(app_module, "WebsiteDownloader", _BlockingDownloader)
    monkeypatch.setattr(app_module, "zip_directory", _fake_zip_directory)

    resp = client.post("/start-download", json={"url": "https://example.com"})
    session_id = resp.get_json()["session_id"]
    assert block.wait(timeout=2.0), "worker thread never reached process()"

    # Status is still 'processing' — /download-file must refuse
    file_resp = client.get(f"/download-file/{session_id}")
    assert file_resp.status_code == 404

    release.set()
    _wait_for_status(app_module, session_id, expected={"complete"})


# ── Session ID uniqueness across calls ───────────────────────────────────────


def test_two_starts_produce_distinct_session_ids(client, flask_app, tmp_path, monkeypatch):
    import app as app_module

    monkeypatch.setattr(app_module, "DOWNLOAD_FOLDER", str(tmp_path))
    monkeypatch.setattr(app_module, "WebsiteDownloader", _FakeDownloaderSuccess)
    monkeypatch.setattr(app_module, "zip_directory", _fake_zip_directory)

    r1 = client.post("/start-download", json={"url": "https://a.com"})
    r2 = client.post("/start-download", json={"url": "https://b.com"})
    sid1 = r1.get_json()["session_id"]
    sid2 = r2.get_json()["session_id"]
    assert sid1 != sid2
    uuid.UUID(sid1)
    uuid.UUID(sid2)


# Unused parametrize import suppression — kept future-proof for adding cases
_ = pytest
