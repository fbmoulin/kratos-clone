"""Coverage for GET /api/captures — capture directory listing.

Spec: `docs/superpowers/specs/2026-05-14-ui-u1-u5-elapsed-timer-and-captures-dropdown.md`
Closes audit item U5 (free-text html_dir → datalist with real captures).

Filter contract: subdirectories of DOWNLOAD_FOLDER that are NOT
session UUIDs and NOT files. Sorted alphabetically.
"""

from __future__ import annotations

import os
import uuid

# ── Happy paths ──────────────────────────────────────────────────────────────


def test_returns_empty_when_no_captures(client, flask_app, tmp_path, monkeypatch):
    """Cold-start scenario: DOWNLOAD_FOLDER exists but empty."""
    import app as app_module

    monkeypatch.setattr(app_module, "DOWNLOAD_FOLDER", str(tmp_path))
    resp = client.get("/api/captures")
    assert resp.status_code == 200
    assert resp.get_json() == {"captures": []}


def test_returns_empty_when_folder_missing(client, flask_app, tmp_path, monkeypatch):
    """Folder doesn't exist yet (boot before janitor ran) — no error, empty list."""
    import app as app_module

    monkeypatch.setattr(app_module, "DOWNLOAD_FOLDER", str(tmp_path / "does-not-exist"))
    resp = client.get("/api/captures")
    assert resp.status_code == 200
    assert resp.get_json() == {"captures": []}


def test_returns_real_capture_dirs(client, flask_app, tmp_path, monkeypatch):
    """Real (non-UUID) directory names should appear."""
    import app as app_module

    monkeypatch.setattr(app_module, "DOWNLOAD_FOLDER", str(tmp_path))
    (tmp_path / "site-A").mkdir()
    (tmp_path / "nexusflow-clone").mkdir()

    resp = client.get("/api/captures")
    assert resp.status_code == 200
    data = resp.get_json()
    assert sorted(data["captures"]) == ["nexusflow-clone", "site-A"]


def test_results_are_sorted_alphabetically(client, flask_app, tmp_path, monkeypatch):
    """Deterministic order — operator + tests both expect alphabetical."""
    import app as app_module

    monkeypatch.setattr(app_module, "DOWNLOAD_FOLDER", str(tmp_path))
    for name in ("zebra", "alpha", "mike", "bravo"):
        (tmp_path / name).mkdir()

    resp = client.get("/api/captures")
    assert resp.get_json()["captures"] == ["alpha", "bravo", "mike", "zebra"]


# ── Filter contract ──────────────────────────────────────────────────────────


def test_session_uuid_dirs_are_excluded(client, flask_app, tmp_path, monkeypatch):
    """Dirs named like a UUID4 are session dirs — must NOT appear in captures."""
    import app as app_module

    monkeypatch.setattr(app_module, "DOWNLOAD_FOLDER", str(tmp_path))
    (tmp_path / "real-site").mkdir()
    (tmp_path / str(uuid.uuid4())).mkdir()  # an in-flight session dir
    (tmp_path / "f47ac10b-58cc-4372-a567-0e02b2c3d479").mkdir()  # fixed UUID4

    resp = client.get("/api/captures")
    assert resp.get_json()["captures"] == ["real-site"]


def test_zip_files_are_excluded(client, flask_app, tmp_path, monkeypatch):
    """`<sid>.zip` files live next to capture dirs but must not be listed."""
    import app as app_module

    monkeypatch.setattr(app_module, "DOWNLOAD_FOLDER", str(tmp_path))
    (tmp_path / "site-B").mkdir()
    (tmp_path / "loose-file.txt").write_text("")
    (tmp_path / f"{uuid.uuid4()}.zip").write_bytes(b"PK\x05\x06" + b"\x00" * 18)

    resp = client.get("/api/captures")
    assert resp.get_json()["captures"] == ["site-B"]


def test_non_uuid_names_with_hyphens_are_kept(client, flask_app, tmp_path, monkeypatch):
    """Names that look UUID-ish but aren't valid UUIDs must NOT be filtered."""
    import app as app_module

    monkeypatch.setattr(app_module, "DOWNLOAD_FOLDER", str(tmp_path))
    # Hyphen-rich but not a UUID
    (tmp_path / "site-a-b-c-d-e").mkdir()
    # Right-length but invalid hex
    (tmp_path / "zzzzzzzz-zzzz-zzzz-zzzz-zzzzzzzzzzzz").mkdir()

    resp = client.get("/api/captures")
    captures = resp.get_json()["captures"]
    assert "site-a-b-c-d-e" in captures
    assert "zzzzzzzz-zzzz-zzzz-zzzz-zzzzzzzzzzzz" in captures


# ── Response shape ───────────────────────────────────────────────────────────


def test_response_is_json_with_captures_key(client, flask_app, tmp_path, monkeypatch):
    """API contract: top-level object with `captures: list[str]`."""
    import app as app_module

    monkeypatch.setattr(app_module, "DOWNLOAD_FOLDER", str(tmp_path))
    (tmp_path / "x").mkdir()

    resp = client.get("/api/captures")
    assert resp.content_type.startswith("application/json")
    data = resp.get_json()
    assert isinstance(data, dict)
    assert "captures" in data
    assert isinstance(data["captures"], list)
    assert all(isinstance(c, str) for c in data["captures"])


# Silence unused-import warning when fixtures handle the imports for us
_ = os
