"""Tests for personalize.sanitize — closes audit P2-11."""

from __future__ import annotations

import io

import pytest
from PIL import Image

from personalize.sanitize import (
    sanitize_brief_text,
    strip_dangerous_html,
    strip_exif,
    verify_image_bytes,
)

PNG_HEADER = b"\x89PNG\r\n\x1a\n"
JPEG_HEADER = b"\xff\xd8\xff"


def _png_bytes(size: tuple[int, int] = (8, 8), color: str = "red") -> bytes:
    img = Image.new("RGB", size, color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _png_bytes_with_exif() -> bytes:
    img = Image.new("RGB", (8, 8), "blue")
    buf = io.BytesIO()
    exif = img.getexif()
    exif[0x010E] = "embedded brand secret"
    img.save(buf, format="PNG", exif=exif.tobytes())
    return buf.getvalue()


class TestSanitizeBrief:
    def test_strips_null_bytes(self):
        assert "\x00" not in sanitize_brief_text("hello\x00world")

    def test_strips_other_control_chars(self):
        out = sanitize_brief_text("hello\x07\x1bworld")
        assert "\x07" not in out and "\x1b" not in out
        assert "hello" in out and "world" in out

    def test_preserves_unicode(self):
        s = "Olá, mundo — café 🇧🇷 résumé"
        assert sanitize_brief_text(s) == s

    def test_truncates_to_max_len(self):
        assert len(sanitize_brief_text("x" * 5000, max_len=100)) == 100

    def test_empty_string_ok(self):
        assert sanitize_brief_text("") == ""

    def test_rejects_non_string(self):
        with pytest.raises(TypeError):
            sanitize_brief_text(123)  # type: ignore[arg-type]

    def test_preserves_newline_and_tab(self):
        s = "line one\nline two\tcol"
        assert sanitize_brief_text(s) == s


class TestVerifyImage:
    def test_png_accepted(self):
        assert verify_image_bytes(_png_bytes()) == "png"

    def test_jpeg_accepted(self):
        img = Image.new("RGB", (8, 8), "green")
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        assert verify_image_bytes(buf.getvalue()) == "jpeg"

    def test_svg_rejected(self):
        with pytest.raises(ValueError, match="unsupported"):
            verify_image_bytes(b"<svg xmlns='http://www.w3.org/2000/svg'/>")

    def test_gif_rejected(self):
        with pytest.raises(ValueError):
            verify_image_bytes(b"GIF89a" + b"\x00" * 32)

    def test_empty_rejected(self):
        with pytest.raises(ValueError, match="empty"):
            verify_image_bytes(b"")

    def test_text_rejected(self):
        with pytest.raises(ValueError):
            verify_image_bytes(b"plain text not an image")


class TestStripExif:
    def test_removes_exif_metadata(self):
        original = _png_bytes_with_exif()
        cleaned = strip_exif(original)
        cleaned_img = Image.open(io.BytesIO(cleaned))
        assert dict(cleaned_img.getexif()) == {}

    def test_preserves_pixels(self):
        original = _png_bytes((4, 4), "red")
        cleaned = strip_exif(original)
        assert Image.open(io.BytesIO(cleaned)).size == (4, 4)


class TestStripDangerousHTML:
    def test_removes_script(self):
        out = strip_dangerous_html("<p>ok</p><script>alert(1)</script>")
        assert "<script" not in out and "alert" not in out

    def test_removes_event_handlers(self):
        out = strip_dangerous_html('<button onclick="bad()">x</button>')
        assert "onclick" not in out
        assert "bad()" not in out

    def test_neutralizes_javascript_href(self):
        out = strip_dangerous_html('<a href="javascript:alert(1)">x</a>')
        assert "javascript:" not in out.lower()

    def test_removes_iframe(self):
        out = strip_dangerous_html('<p>ok</p><iframe src="evil.html"></iframe>')
        assert "<iframe" not in out

    def test_preserves_safe_content(self):
        out = strip_dangerous_html('<p class="x">ok <a href="https://e.com">e</a></p>')
        assert "ok" in out and "e.com" in out and "https://" in out

    def test_neutralizes_javascript_in_src(self):
        out = strip_dangerous_html('<img src="javascript:alert(1)">')
        assert "javascript:" not in out.lower()
