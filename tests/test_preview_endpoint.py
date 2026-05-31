"""Tests for the personalize_preview file-serving endpoint (Task 1).

Covers happy-path serving (html/css in subdir/svg), Cache-Control header,
security rejections (extension allowlist, double-extension, traversal,
absolute-path injection, missing file/dir), and the CSP defense-in-depth
header (R2-PRC004 delta: script-src 'none' + sandbox + nosniff).

Capture fixtures (capture_root, tmp_capture, tmp_capture_with_svg) live in
conftest.py because Task 3's tests reuse them from a different file.
"""

from __future__ import annotations


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

    def test_cache_control_header_present(self, client, tmp_capture):
        r = client.get(f"/personalize/preview/{tmp_capture}/index.html")
        assert r.status_code == 200
        assert r.headers.get("Cache-Control")
        assert "max-age=3600" in r.headers["Cache-Control"]

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

    def test_html_preview_has_no_restrictive_csp(self, client, tmp_capture):
        # HTML must render full-fidelity in the allow-scripts iframe (R1-PRC006):
        # no script-blocking CSP on HTML documents.
        r = client.get(f"/personalize/preview/{tmp_capture}/index.html")
        assert r.status_code == 200
        assert "script-src 'none'" not in r.headers.get("Content-Security-Policy", "")
        assert r.headers.get("X-Content-Type-Options") == "nosniff"

    def test_svg_preview_has_strict_csp(self, client, tmp_capture_with_svg):
        # SVG served as a document gets script-src 'none' to kill the
        # inline-<script> XSS vector (R2-PRC004). .svg stays in the allowlist.
        r = client.get(f"/personalize/preview/{tmp_capture_with_svg}/logo.svg")
        assert r.status_code == 200
        csp = r.headers.get("Content-Security-Policy", "")
        assert "script-src 'none'" in csp
        assert "sandbox" in csp
