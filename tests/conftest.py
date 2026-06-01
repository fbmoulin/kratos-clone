"""Shared pytest fixtures.

Critical pattern: app is imported with NO side effects (factory pattern, audit P2-7).
Each test gets a fresh client + clean in-memory state."""

from __future__ import annotations

import pytest


@pytest.fixture
def flask_app():
    """Side-effect-free Flask app instance. No janitor, no boot cleanup, no rate limits.

    Rate limiting is disabled in tests because all requests come from 127.0.0.1
    and the per-IP cap (60/min) would short-circuit parametrized assertions.
    Production gets the limit via the @limiter.limit decorator.
    """
    import app as app_module

    app_module.create_app(start_janitor=False, run_boot_cleanup=False)
    app_module.app.config["RATELIMIT_ENABLED"] = False
    app_module._reset_state()
    yield app_module.app
    app_module._reset_state()


@pytest.fixture
def client(flask_app):
    """Flask test client backed by the side-effect-free app fixture."""
    return flask_app.test_client()


@pytest.fixture
def capture_root(tmp_path, monkeypatch):
    """Point the app's DOWNLOAD_FOLDER at a tmp dir so _validate_html_dir accepts
    dirs created under it (realpath confinement is relative to DOWNLOAD_FOLDER)."""
    import app as app_module

    root = tmp_path / "downloads"
    root.mkdir()
    monkeypatch.setattr(app_module, "DOWNLOAD_FOLDER", str(root))
    return root


@pytest.fixture
def tmp_capture(capture_root):
    """A capture dir <root>/cap1 with index.html + personalized.html + a css asset.
    Returns the single-segment dir name (per route's <string:html_dir> contract)."""
    d = capture_root / "cap1"
    (d / "assets").mkdir(parents=True)
    (d / "index.html").write_text("<!doctype html><title>orig</title>")
    (d / "personalized.html").write_text("<!doctype html><title>new</title>")
    (d / "assets" / "style.css").write_text("body{color:red}")
    return "cap1"


@pytest.fixture
def tmp_capture_with_svg(tmp_capture, capture_root):
    """tmp_capture plus a logo.svg containing an inline <script> (the XSS vector
    that CSP script-src 'none' neutralizes)."""
    (capture_root / tmp_capture / "logo.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
    )
    return tmp_capture
