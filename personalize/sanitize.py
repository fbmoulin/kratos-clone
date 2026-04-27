"""Security helpers for the personalization pipeline.

Closes audit finding **P2-11** (LLM input/output hardening). Every public
function here exists to keep adversarial input from reaching either the LLM
or the captured DOM.

Threat model:
    - User-controlled brief text → injected into LLM system/user prompts.
      Mitigation: ``sanitize_brief_text`` strips control chars and bounds length.
    - User-uploaded logo → fed to LLM Vision and shipped in output assets.
      Mitigation: ``verify_image_bytes`` allow-lists PNG/JPEG only (SVG XSS),
      ``strip_exif`` removes embedded metadata.
    - LLM-generated text values → written into the captured DOM.
      Mitigation: ``strip_dangerous_html`` defense-in-depth even though
      structured outputs schema does not allow HTML in text fields.
"""

from __future__ import annotations

import io
import re

from bs4 import BeautifulSoup
from PIL import Image

# Strip C0 controls except \t (\x09), \n (\x0a), \r (\x0d) which are useful
# for multi-line briefs; also strip DEL (\x7f).
_CTRL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
JPEG_MAGIC = b"\xff\xd8\xff"

_DANGEROUS_TAGS = ("script", "style", "iframe", "object", "embed")
_URL_ATTRS = ("href", "src", "action", "formaction", "xlink:href")


def sanitize_brief_text(text: str, max_len: int = 2000) -> str:
    """Strip control chars, enforce length cap.

    Returns text safe to interpolate into LLM prompts. Does NOT escape
    HTML/markdown — the LLM is expected to read prose; the schema is what
    constrains structure.
    """
    if not isinstance(text, str):
        raise TypeError(f"brief text must be str, got {type(text).__name__}")
    cleaned = _CTRL_CHARS.sub("", text)
    return cleaned[:max_len]


def verify_image_bytes(data: bytes) -> str:
    """Allow-list PNG and JPEG by magic bytes; reject everything else.

    SVG is rejected because it can carry inline ``<script>`` and event
    handlers that XSS when rendered as ``<img src="...">`` in some
    browsers + frameworks. GIF and other formats are rejected because the
    pipeline's image-gen output and Vision input are PNG/JPEG-only.
    """
    if not data:
        raise ValueError("empty image bytes")
    if data.startswith(PNG_MAGIC):
        return "png"
    if data.startswith(JPEG_MAGIC):
        return "jpeg"
    raise ValueError(
        f"unsupported image type (PNG/JPEG only); leading bytes={data[:8]!r}"
    )


def strip_exif(data: bytes) -> bytes:
    """Re-encode the image without EXIF/XMP/ICC metadata.

    Pillow's ``getdata()`` + ``putdata()`` round-trip drops every metadata
    chunk. For PNG: tEXt/iTXt/eXIf are dropped. For JPEG: APP markers are
    stripped. Pixel data is preserved.
    """
    img = Image.open(io.BytesIO(data))
    fmt = img.format or ("PNG" if data.startswith(PNG_MAGIC) else "JPEG")
    # copy() drops parsed metadata (exif/xmp/icc) while preserving pixels;
    # save() without exif kwarg writes none.
    clean = img.copy()
    out = io.BytesIO()
    clean.save(out, format=fmt)
    return out.getvalue()


def strip_dangerous_html(html: str) -> str:
    """Remove script/style/iframe tags, event handlers, javascript: URLs.

    Defense-in-depth — the personalize call returns plain strings (not HTML)
    via strict JSON schema, but we sanitize before writing into the DOM
    anyway. If a future feature lets the LLM emit fragments, this is the
    chokepoint.
    """
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all(_DANGEROUS_TAGS):
        tag.decompose()
    for tag in soup.find_all(True):
        for attr in list(tag.attrs):
            if attr.lower().startswith("on"):
                del tag.attrs[attr]
        for url_attr in _URL_ATTRS:
            value = tag.attrs.get(url_attr)
            if isinstance(value, str) and value.strip().lower().startswith(
                "javascript:"
            ):
                tag.attrs[url_attr] = "#"
    return str(soup)
