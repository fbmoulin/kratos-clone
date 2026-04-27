"""Tests for scripts.post_process — Stage 3 helpers."""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from PIL import Image

from scripts.post_process import AssetAudit, audit_assets, inline_small_assets


def _png(size: tuple[int, int] = (16, 16), color: str = "blue") -> bytes:
    img = Image.new("RGB", size, color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def capture_dir(tmp_path: Path) -> Path:
    """Realistic capture layout: index.html + assets/ with 3 files."""
    (tmp_path / "index.html").write_text(
        "<html><body>"
        '<img src="assets/small.png">'
        '<img src="assets/medium.png">'
        '<img src="assets/big.png">'
        '<a href="https://external.com">ext</a>'
        "</body></html>",
        encoding="utf-8",
    )
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "small.png").write_bytes(_png((4, 4)))
    (assets / "medium.png").write_bytes(_png((64, 64)))
    (assets / "big.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 20_000)
    return tmp_path


class TestAuditAssets:
    def test_counts_files_and_total_size(self, capture_dir):
        audit = audit_assets(capture_dir)
        assert isinstance(audit, AssetAudit)
        assert audit.count == 3
        assert audit.total_bytes > 0
        assert all(p.suffix == ".png" for p in audit.paths)

    def test_empty_assets_dir_ok(self, tmp_path):
        (tmp_path / "assets").mkdir()
        audit = audit_assets(tmp_path)
        assert audit.count == 0
        assert audit.total_bytes == 0

    def test_missing_assets_dir_returns_empty(self, tmp_path):
        audit = audit_assets(tmp_path)
        assert audit.count == 0


class TestInlineSmallAssets:
    def test_inlines_small_pngs_below_threshold(self, capture_dir):
        small_size = (capture_dir / "assets" / "small.png").stat().st_size
        big_size = (capture_dir / "assets" / "big.png").stat().st_size
        # Pick threshold strictly between small and big so the assertion is
        # robust to PNG-compression variance.
        threshold = (small_size + big_size) // 2
        assert small_size < threshold < big_size

        out_html = capture_dir / "inlined.html"
        n = inline_small_assets(capture_dir / "index.html", out_html, max_bytes=threshold)
        out = out_html.read_text()
        # At minimum, small.png is inlined and big.png is left as a file ref.
        assert n >= 1
        assert "data:image/png;base64," in out
        assert 'src="assets/small.png"' not in out
        assert 'src="assets/big.png"' in out

    def test_zero_threshold_inlines_nothing(self, capture_dir):
        out_html = capture_dir / "inlined.html"
        n = inline_small_assets(capture_dir / "index.html", out_html, max_bytes=0)
        assert n == 0
        # Output should be byte-equivalent to input apart from re-serialization.
        assert "data:image/" not in out_html.read_text()

    def test_external_links_untouched(self, capture_dir):
        out_html = capture_dir / "inlined.html"
        inline_small_assets(capture_dir / "index.html", out_html, max_bytes=10_000)
        assert 'href="https://external.com"' in out_html.read_text()
