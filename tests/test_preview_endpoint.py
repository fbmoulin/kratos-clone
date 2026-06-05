"""Tests for the personalize_preview file-serving endpoint (Task 1).

Covers happy-path serving (html/css in subdir/svg), Cache-Control header,
security rejections (extension allowlist, double-extension, traversal,
absolute-path injection, missing file/dir), and the CSP defense-in-depth
header (R2-PRC004 delta: script-src 'none' + sandbox + nosniff).

Capture fixtures (capture_root, tmp_capture, tmp_capture_with_svg) live in
conftest.py because Task 3's tests reuse them from a different file.
"""

from __future__ import annotations

import os
import sys

import pytest

# A 1x1 transparent PNG (smallest valid PNG) used by route-level happy-path
# tests so we never launch a real browser in the unit suite.
PNG_1x1 = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000a49444154789c6360000002000154a24f5f0000000049454e44ae426082"
)


class TestPersonalizePreview:
    # --- Happy paths -------------------------------------------------------

    def test_serves_html_200(self, client, tmp_capture):
        r = client.get(f"/personalize/preview/{tmp_capture}/index.html")
        assert r.status_code == 200
        assert b"orig" in r.data

    def test_serves_personalized_html_200(self, client, tmp_capture):
        r = client.get(f"/personalize/preview/{tmp_capture}/personalized.html")
        assert r.status_code == 200
        assert b"new" in r.data

    def test_serves_css_in_subdir_200(self, client, tmp_capture):
        r = client.get(f"/personalize/preview/{tmp_capture}/assets/style.css")
        assert r.status_code == 200
        assert b"color:red" in r.data

    def test_html_revalidates_no_cache(self, client, tmp_capture):
        # Review #1: index.html / personalized.html are regenerated on each
        # personalize run, so they must revalidate — otherwise a re-personalized
        # dir serves stale HTML from the browser cache for up to max-age.
        for name in ("index.html", "personalized.html"):
            r = client.get(f"/personalize/preview/{tmp_capture}/{name}")
            assert r.status_code == 200, name
            assert "no-cache" in r.headers.get("Cache-Control", ""), name

    def test_static_asset_still_cached(self, client, tmp_capture):
        # Hashed/static assets keep the long cache; only mutable HTML revalidates.
        r = client.get(f"/personalize/preview/{tmp_capture}/assets/style.css")
        assert r.status_code == 200
        assert "max-age=3600" in r.headers.get("Cache-Control", "")

    def test_serves_svg_200(self, client, tmp_capture_with_svg):
        r = client.get(f"/personalize/preview/{tmp_capture_with_svg}/logo.svg")
        assert r.status_code == 200

    # --- Security rejections ----------------------------------------------

    def test_extension_not_allowed_400(self, client, capture_root, tmp_capture):
        (capture_root / tmp_capture / "secret.txt").write_text("nope")
        r = client.get(f"/personalize/preview/{tmp_capture}/secret.txt")
        assert r.status_code == 400

    def test_double_extension_400(self, client, capture_root, tmp_capture):
        (capture_root / tmp_capture / "index.html.txt").write_text("nope")
        r = client.get(f"/personalize/preview/{tmp_capture}/index.html.txt")
        assert r.status_code == 400

    def test_dotdot_traversal_in_html_dir_not_200(self, client, tmp_capture):
        # ".." collapses to html_dir="etc" via Werkzeug path normalization;
        # _validate_html_dir rejects it (outside downloads/) -> 400. Never a 200.
        r = client.get("/personalize/preview/../index.html")
        assert r.status_code == 400

    def test_url_encoded_traversal_not_200(self, client, tmp_capture):
        # %2E%2E%2F decodes to "../"; Werkzeug merge-slash/normalize returns a
        # 308 redirect to the canonical path before the view runs. Never a 200.
        r = client.get("/personalize/preview/%2E%2E%2F/index.html")
        assert r.status_code == 308

    def test_absolute_path_injection_not_found(self, client):
        # html_dir "etc" resolves under DOWNLOAD_FOLDER and won't exist -> 404.
        r = client.get("/personalize/preview/etc/passwd.html")
        assert r.status_code == 404

    def test_missing_file_404(self, client, tmp_capture):
        r = client.get(f"/personalize/preview/{tmp_capture}/nope.html")
        assert r.status_code == 404

    def test_missing_dir_404(self, client):
        r = client.get("/personalize/preview/doesnotexist/index.html")
        assert r.status_code == 404

    # --- CSP cases (R2-PRC004: content-type-aware, SVG-only) --------------

    def test_html_in_iframe_has_relaxed_csp(self, client, tmp_capture):
        # Inside the modal's sandboxed iframe (Sec-Fetch-Dest: iframe), captured
        # SPA JS must run full-fidelity (R1-PRC006) — so NO locking CSP. Covers
        # personalized.html, the file the iframe actually loads.
        for name in ("index.html", "personalized.html"):
            r = client.get(
                f"/personalize/preview/{tmp_capture}/{name}",
                headers={"Sec-Fetch-Dest": "iframe"},
            )
            assert r.status_code == 200, name
            assert "default-src 'none'" not in r.headers.get("Content-Security-Policy", ""), name
            assert r.headers.get("X-Content-Type-Options") == "nosniff"

    def test_html_top_level_open_has_restrictive_csp(self, client, tmp_capture):
        # Review #3: a top-level navigation (Sec-Fetch-Dest != "iframe") to ANY
        # captured HTML — including personalized.html, which the prior
        # index.html-only guard left unprotected — gets a locked-down CSP so
        # first-party scripts can't execute on the Flask origin.
        for name in ("index.html", "personalized.html"):
            r = client.get(f"/personalize/preview/{tmp_capture}/{name}")
            assert r.status_code == 200, name
            csp = r.headers.get("Content-Security-Policy", "")
            assert "default-src 'none'" in csp, name
            assert "sandbox" in csp, name

    def test_svg_preview_has_strict_csp(self, client, tmp_capture_with_svg):
        # SVG served as a document gets script-src 'none' to kill the
        # inline-<script> XSS vector (R2-PRC004). .svg stays in the allowlist.
        r = client.get(f"/personalize/preview/{tmp_capture_with_svg}/logo.svg")
        assert r.status_code == 200
        csp = r.headers.get("Content-Security-Policy", "")
        assert "script-src 'none'" in csp
        assert "sandbox" in csp


class TestPersonalizeScreenshot:
    """Route-level tests for /api/personalize/screenshot/<html_dir>.

    Playwright is never launched here: the render path is exercised by
    monkeypatching app._render_html_to_png. The render helper itself is covered
    only at the unit level (network guard) — a live browser launch belongs in
    a gated integration test, not this suite.
    """

    # --- Query / path validation ------------------------------------------

    def test_which_missing_400(self, client, tmp_capture):
        r = client.get(f"/api/personalize/screenshot/{tmp_capture}")
        assert r.status_code == 400

    def test_which_invalid_400(self, client, tmp_capture):
        r = client.get(f"/api/personalize/screenshot/{tmp_capture}?which=sideways")
        assert r.status_code == 400

    def test_html_dir_invalid_400(self, client):
        # "." is rejected by _validate_html_dir's empty/dot guard -> 400 (the
        # invalid-html_dir branch). Real ".." segments are handled at the routing
        # layer (308/404), exercised by the sibling preview-endpoint tests.
        r = client.get("/api/personalize/screenshot/.?which=before")
        assert r.status_code == 400

    def test_missing_dir_404(self, client):
        r = client.get("/api/personalize/screenshot/doesnotexist?which=before")
        assert r.status_code == 404

    def test_before_missing_index_404(self, client, capture_root):
        # Dir exists but has no index.html -> 404 for which=before.
        (capture_root / "empty").mkdir()
        r = client.get("/api/personalize/screenshot/empty?which=before")
        assert r.status_code == 404

    def test_after_missing_personalized_404(self, client, capture_root):
        # tmp_capture has index.html but a fresh dir without personalized.html.
        (capture_root / "noperso").mkdir()
        (capture_root / "noperso" / "index.html").write_text("<title>x</title>")
        r = client.get("/api/personalize/screenshot/noperso?which=after")
        assert r.status_code == 404

    # --- Render happy path / cache / capacity -----------------------------

    def test_happy_path_after_renders_png(self, client, tmp_capture, monkeypatch):
        import app as app_module

        def fake_render(src_html_path, out_png_path):
            # The route hands us the cache_path; write a valid PNG there.
            with open(out_png_path, "wb") as fh:
                fh.write(PNG_1x1)

        monkeypatch.setattr(app_module, "_render_html_to_png", fake_render)
        r = client.get(f"/api/personalize/screenshot/{tmp_capture}?which=after")
        assert r.status_code == 200
        assert r.headers["Content-Type"] == "image/png"
        assert r.data == PNG_1x1

    def test_cache_hit_skips_render(self, client, tmp_capture, capture_root, monkeypatch):
        import app as app_module

        # Pre-create the cache file so the route short-circuits the render.
        (capture_root / tmp_capture / "preview-after.png").write_bytes(PNG_1x1)
        calls = []

        def spy_render(src_html_path, out_png_path):
            calls.append((src_html_path, out_png_path))

        monkeypatch.setattr(app_module, "_render_html_to_png", spy_render)
        r = client.get(f"/api/personalize/screenshot/{tmp_capture}?which=after")
        assert r.status_code == 200
        assert r.headers["Content-Type"] == "image/png"
        assert calls == []  # cache hit -> render never invoked

    def test_capacity_exhausted_503(self, client, tmp_capture, monkeypatch):
        import app as app_module

        def boom(src_html_path, out_png_path):
            raise app_module.RenderCapacityExhausted()

        monkeypatch.setattr(app_module, "_render_html_to_png", boom)
        r = client.get(f"/api/personalize/screenshot/{tmp_capture}?which=after")
        assert r.status_code == 503
        assert r.headers.get("Retry-After") == "30"

    def test_render_failure_returns_logged_500(self, client, tmp_capture, monkeypatch):
        # A non-capacity render failure (e.g. Playwright TimeoutError) is caught,
        # logged, and returned as structured JSON 500 — not a bare HTML 500 page.
        import app as app_module

        def boom(src_html_path, out_png_path):
            raise RuntimeError("playwright timeout")

        monkeypatch.setattr(app_module, "_render_html_to_png", boom)
        r = client.get(f"/api/personalize/screenshot/{tmp_capture}?which=after")
        assert r.status_code == 500
        assert r.get_json()["error"] == "screenshot render failed"


class TestValidateHtmlDir:
    """Direct unit tests of app._validate_html_dir (R1-PRC007 helper).

    Task 1/2 exercised the helper only indirectly through the preview/screenshot
    routes; these cover its policy directly, including a portable symlink-escape
    case (R2-PRC003)."""

    def test_empty_returns_none(self, capture_root):
        import app as app_module

        assert app_module._validate_html_dir("") is None

    def test_dot_returns_none(self, capture_root):
        import app as app_module

        assert app_module._validate_html_dir(".") is None

    def test_dotslash_returns_none(self, capture_root):
        import app as app_module

        assert app_module._validate_html_dir("./") is None

    def test_whitespace_returns_none(self, capture_root):
        import app as app_module

        assert app_module._validate_html_dir("   ") is None

    def test_absolute_path_returns_none(self, capture_root):
        import app as app_module

        assert app_module._validate_html_dir("/etc") is None

    def test_traversal_returns_none(self, capture_root):
        import app as app_module

        assert app_module._validate_html_dir("../etc") is None

    def test_midpath_traversal_returns_none(self, capture_root):
        import app as app_module

        assert app_module._validate_html_dir("foo/../../etc") is None

    def test_valid_dir_returns_realpath(self, capture_root, tmp_capture):
        import app as app_module

        result = app_module._validate_html_dir(tmp_capture)
        assert result is not None and result.endswith(tmp_capture)

    # R2-PRC003: portable symlink-escape test
    @pytest.mark.skipif(
        sys.platform == "win32",
        reason="os.symlink requires admin/Developer Mode on Windows",
    )
    def test_rejects_symlink_escape(self, capture_root):
        import app as app_module

        outside = capture_root.parent / "outside"
        outside.mkdir()
        (outside / "secret.html").write_text("x")
        os.symlink(outside, capture_root / "evil")  # symlink inside base -> outside
        assert app_module._validate_html_dir("evil") is None


def test_screenshot_semaphore_default_value(client):
    """create_app() (via the client fixture) wires RENDER_SEMAPHORE with the
    default capacity of 2 when KCD_MAX_CONCURRENT_RENDERS is unset."""
    sem = client.application.config["RENDER_SEMAPHORE"]
    assert sem._value == 2


def test_capacity_override_via_env(monkeypatch):
    """R2-PRC008: monkeypatch.setenv + a fresh create_app() picks up the
    override with no importlib.reload (semaphore built at app-construction)."""
    monkeypatch.setenv("KCD_MAX_CONCURRENT_RENDERS", "1")
    import app as app_module

    test_app = app_module.create_app(start_janitor=False, run_boot_cleanup=False)
    sem = test_app.config["RENDER_SEMAPHORE"]
    assert sem._value == 1


def test_block_external_aborts_non_file_urls():
    """R2-PRC007: the request-blocking callback is module-level + unit-testable
    without a live Playwright instance."""
    import asyncio

    import app as app_module

    aborted, continued = [], []

    class FakeRequest:
        def __init__(self, url):
            self.url = url

    class FakeRoute:
        def __init__(self, url):
            self.request = FakeRequest(url)

        async def abort(self):
            aborted.append(self.request.url)

        async def continue_(self):
            continued.append(self.request.url)

    asyncio.run(app_module._block_external(FakeRoute("https://fonts.googleapis.com/x.css")))
    asyncio.run(app_module._block_external(FakeRoute("file:///tmp/index.html")))
    assert aborted == ["https://fonts.googleapis.com/x.css"]
    assert continued == ["file:///tmp/index.html"]
