"""Non-mocked Playwright render test for _render_html_to_png.

Gated by RUN_PLAYWRIGHT_LIVE=1 (like the RUN_OPENAI_LIVE live tests) because it
launches a real headless Chromium (~2-3s) and needs the browser installed.

WHY THIS EXISTS: the route-level screenshot tests mock _render_html_to_png
wholesale, so a real defect in the render itself was invisible. The Playwright
smoke caught one — `page.screenshot(path=...".png.tmp")` raised "Unsupported
screenshot mime type ... None" because Playwright infers format from the file
extension and the atomic-write temp file ends in ".tmp". This test exercises the
real path end-to-end and asserts a valid PNG, so that class of bug fails in CI
(when the flag is set) rather than only in a manual browser smoke.

Run: RUN_PLAYWRIGHT_LIVE=1 uv run pytest tests/test_render_live.py -v
"""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_PLAYWRIGHT_LIVE"),
    reason="set RUN_PLAYWRIGHT_LIVE=1 to run the real headless-Chromium render",
)

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def test_render_html_to_png_produces_valid_png(flask_app, tmp_path):
    import app as app_module

    src = tmp_path / "page.html"
    src.write_text("<!doctype html><html><body><h1>render me</h1></body></html>")
    out = tmp_path / "shot.png"

    # _render_html_to_png reads current_app.config["RENDER_SEMAPHORE"], so it must
    # run inside an application context.
    with flask_app.app_context():
        app_module._render_html_to_png(str(src), str(out))

    assert out.is_file(), "render did not produce the output file"
    data = out.read_bytes()
    assert data.startswith(_PNG_MAGIC), "output is not a valid PNG (the .tmp-extension bug)"
    assert len(data) > 1000, "PNG is implausibly small — render likely blank/failed"
