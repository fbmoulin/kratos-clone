"""Tests for personalize.patcher — Step 7 of the spec."""

from __future__ import annotations

import io
import shutil
from pathlib import Path

import pytest
from PIL import Image

from personalize.patcher import apply_personalization

FIXTURE_HTML = Path(__file__).parent / "fixtures" / "sample_captured.html"

SLOTS = [
    {
        "id": "hero.badge",
        "selector": ".hero .badge",
        "type": "text",
        "max_chars": 30,
    },
    {
        "id": "hero.headline",
        "selector": ".hero h1",
        "type": "text",
        "max_chars": 60,
        "structure": "word-wrappers",
    },
    {
        "id": "hero.subhead",
        "selector": ".hero p.subhead",
        "type": "text",
        "max_chars": 200,
    },
    {
        "id": "hero.cta.primary",
        "selector": ".hero button.primary",
        "type": "text",
        "max_chars": 24,
    },
    {
        "id": "hero.missing",
        "selector": ".does-not-exist",
        "type": "text",
        "max_chars": 50,
    },
    {
        "id": "image.hero",
        "selector": ".perspective-container img",
        "type": "image",
        "width": 64,
        "height": 64,
    },
]


def _png_bytes() -> bytes:
    img = Image.new("RGB", (64, 64), "purple")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    html_dst = tmp_path / "index.html"
    shutil.copy(FIXTURE_HTML, html_dst)
    return tmp_path


def _full_plan() -> dict:
    return {
        "palette": {
            "primary": "#3b82f6",
            "primary_hover": "#60a5fa",
            "primary_pressed": "#2563eb",
            "accent_evidence": "Logo dominant blue",
        },
        "patches": [
            {"slot_id": "hero.badge", "value": "New badge"},
            {"slot_id": "hero.headline", "value": "Brand new headline goes here"},
            {"slot_id": "hero.subhead", "value": "Updated subhead copy."},
            {"slot_id": "hero.cta.primary", "value": "Get started"},
            {"slot_id": "hero.missing", "value": "ignored"},
        ],
        "images": [
            {
                "slot_id": "image.hero",
                "prompt": "Abstract gradient",
            }
        ],
    }


def test_text_patch_applied(workspace):
    out = workspace / "personalized.html"
    apply_personalization(
        workspace / "index.html",
        _full_plan(),
        {"image.hero": _png_bytes()},
        SLOTS,
        out,
    )
    html = out.read_text()
    assert "New badge" in html
    assert "Original badge" not in html


def test_word_wrapper_split(workspace):
    out = workspace / "personalized.html"
    plan = _full_plan()
    plan["patches"] = [
        {"slot_id": "hero.headline", "value": "One Two Three"},
    ]
    plan["images"] = []
    apply_personalization(workspace / "index.html", plan, {}, SLOTS, out)
    html = out.read_text()
    assert "One" in html and "Two" in html and "Three" in html
    # Headline got replaced, but other sections (badge/subhead/CTA) are untouched.
    assert "Original Headline" not in html
    assert "<h1>" in html  # structure preserved


def test_palette_swap_replaces_orange_classes(workspace):
    out = workspace / "personalized.html"
    plan = _full_plan()
    plan["patches"] = []
    plan["images"] = []
    apply_personalization(workspace / "index.html", plan, {}, SLOTS, out)
    html = out.read_text()
    assert "from-orange-500" not in html
    assert "bg-orange-500" not in html
    assert "border-orange-600" not in html
    assert "text-orange-400" not in html
    primary = plan["palette"]["primary"].lstrip("#")
    assert f"#{primary}" in html or f"[#{primary}]" in html


def test_image_swap_writes_asset_and_updates_src(workspace):
    out = workspace / "personalized.html"
    apply_personalization(
        workspace / "index.html",
        _full_plan(),
        {"image.hero": _png_bytes()},
        SLOTS,
        out,
    )
    asset_path = workspace / "assets" / "gen_image_hero.png"
    assert asset_path.exists()
    assert asset_path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    html = out.read_text()
    assert "assets/gen_image_hero.png" in html
    assert "orig-hero.png" not in html


def test_missing_selector_skipped_silently(workspace):
    out = workspace / "personalized.html"
    plan = _full_plan()
    plan["images"] = []
    apply_personalization(workspace / "index.html", plan, {}, SLOTS, out)
    assert out.exists()
    assert "ignored" not in out.read_text()


def test_palette_swap_does_not_touch_text_content(tmp_path: Path):
    """Regression for Gemini medium finding: regex on serialized HTML used to
    rewrite class strings appearing inside text content / IDs / aria labels.
    The DOM-walking implementation must scope the swap to actual class attrs.
    """
    src = tmp_path / "index.html"
    src.write_text(
        "<html><body>"
        '<section class="hero from-orange-500">'
        "<p>Docs sample: use <code>from-orange-500</code> on your hero.</p>"
        '<a id="from-orange-500-anchor" aria-label="from-orange-500">link</a>'
        "</section></body></html>",
        encoding="utf-8",
    )
    out = tmp_path / "personalized.html"
    plan = _full_plan()
    plan["patches"] = []
    plan["images"] = []
    apply_personalization(src, plan, {}, SLOTS, out)
    html = out.read_text()
    # The class on the <section> must be rewritten — orange shade gone.
    assert "from-orange-500" not in html.split("<code>")[0]
    # But the literal inside <code>, the id, and the aria-label are plain
    # text / non-class attrs — must survive untouched.
    assert "<code>from-orange-500</code>" in html
    assert 'id="from-orange-500-anchor"' in html
    assert 'aria-label="from-orange-500"' in html


def test_unicode_preserved(workspace):
    out = workspace / "personalized.html"
    plan = _full_plan()
    plan["patches"] = [{"slot_id": "hero.subhead", "value": "Olá — café 🇧🇷"}]
    plan["images"] = []
    apply_personalization(workspace / "index.html", plan, {}, SLOTS, out)
    assert "Olá — café 🇧🇷" in out.read_text(encoding="utf-8")


def test_dangerous_html_in_value_neutralized(workspace):
    out = workspace / "personalized.html"
    plan = _full_plan()
    plan["patches"] = [{"slot_id": "hero.badge", "value": "<script>alert(1)</script>safe"}]
    plan["images"] = []
    apply_personalization(workspace / "index.html", plan, {}, SLOTS, out)
    html = out.read_text()
    assert "<script" not in html
    assert "alert(1)" not in html
