"""Coverage for kratos_clone/capture.py helpers + WCAG contrast algorithm.

Phase 1 of ROADMAP. Locks down the deterministic helpers (asset_filename,
hash_url) so future refactors don't break filesystem layout, and validates
the WCAG contrast formula used in the design-system Accessibility section.
"""

from __future__ import annotations

from kratos_clone.capture import asset_filename, hash_url

# ── hash_url ─────────────────────────────────────────────────────────────────


def test_hash_url_stable_across_calls():
    """Same input → same hash."""
    assert hash_url("https://x.com/a.png") == hash_url("https://x.com/a.png")


def test_hash_url_distinguishes_inputs():
    """Different inputs → different hashes."""
    assert hash_url("a") != hash_url("b")


def test_hash_url_length_is_12():
    """Always emits exactly 12 hex chars (md5 prefix)."""
    h = hash_url("anything")
    assert len(h) == 12
    assert all(c in "0123456789abcdef" for c in h)


# ── asset_filename ──────────────────────────────────────────────────────────


def test_asset_filename_basic_path():
    fname = asset_filename("https://x.com/img/logo.png")
    assert fname.startswith("logo_") and fname.endswith(".png")


def test_asset_filename_query_string_stripped():
    fname = asset_filename("https://x.com/img/logo.png?v=42")
    # Query string is part of URL but not of fname (we slice the path)
    assert fname.endswith(".png?v_42") is False  # query NOT in extension
    assert "logo" in fname


def test_asset_filename_fragment_stripped():
    fname = asset_filename("https://x.com/img/logo.png#fragment")
    assert "fragment" not in fname


def test_asset_filename_unicode_in_path_sanitized():
    """Unicode chars in path → replaced by underscore."""
    fname = asset_filename("https://x.com/résumé.png")
    # Non-ASCII letters replaced
    assert "é" not in fname
    assert fname.endswith(".png")


def test_asset_filename_no_extension():
    """Asset URL with no `.` in last segment still produces a filename."""
    fname = asset_filename("https://x.com/some/asset")
    # Should produce a fname without trailing dot
    assert "/" not in fname
    assert ".." not in fname
    assert len(fname) > 0


def test_asset_filename_path_traversal_neutralized():
    """`..` in path segments cannot escape `assets/` because we take only the last segment."""
    fname = asset_filename("https://x.com/foo/../../etc/passwd")
    assert "/" not in fname
    assert ".." not in fname
    assert "passwd" in fname or "asset" in fname


def test_asset_filename_trailing_slash():
    """URL ending in `/` should not crash; fname is generic."""
    fname = asset_filename("https://x.com/")
    assert "/" not in fname
    assert len(fname) > 0


def test_asset_filename_length_cap():
    """30-char cap on the name part keeps filenames manageable."""
    long = "a" * 200
    fname = asset_filename(f"https://x.com/{long}.png")
    # Name portion sanitized to <= 30 chars + hash + ext
    name_part = fname.rsplit("_", 1)[0]
    assert len(name_part) <= 30


def test_asset_filename_collision_resistance():
    """Different URLs with same path-tail → different fnames (via hash)."""
    a = asset_filename("https://x.com/img.png")
    b = asset_filename("https://y.com/img.png")
    assert a != b  # different host → different hash → different fname


# ── WCAG 2.2 contrast ratio (referenced in scripts/generate_design_system_v2.py) ──
# Implemented inline here to avoid importing the module-level-execution script.
# Algorithm per https://www.w3.org/WAI/GL/wiki/Contrast_ratio


def _hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)  # expand #fff → ffffff
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def _contrast_ratio(c1: str, c2: str) -> float:
    def rel_lum(rgb):
        r, g, b = (c / 255 for c in rgb)

        def chan(c):
            return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

        return 0.2126 * chan(r) + 0.7152 * chan(g) + 0.0722 * chan(b)

    l1 = rel_lum(_hex_to_rgb(c1))
    l2 = rel_lum(_hex_to_rgb(c2))
    if l1 < l2:
        l1, l2 = l2, l1
    return (l1 + 0.05) / (l2 + 0.05)


def test_contrast_ratio_white_on_black_is_21():
    """Maximum contrast: white (#fff) on black (#000) = 21:1 per WCAG."""
    assert abs(_contrast_ratio("#ffffff", "#000000") - 21.0) < 0.01


def test_contrast_ratio_symmetric():
    """contrast(a, b) == contrast(b, a) — order shouldn't matter."""
    assert abs(_contrast_ratio("#fff", "#000") - _contrast_ratio("#000", "#fff")) < 0.001


def test_contrast_ratio_self_is_1():
    """A color against itself = 1:1 (zero contrast)."""
    assert abs(_contrast_ratio("#abcdef", "#abcdef") - 1.0) < 0.001


def test_contrast_ratio_passes_aa_for_body_text():
    """WCAG 2.2 AA: body text on background needs >= 4.5:1.

    Test a known passing pair: neutral-300 (#d4d4d4) on near-black (#0a0a0a).
    """
    ratio = _contrast_ratio("#d4d4d4", "#0a0a0a")
    assert ratio >= 4.5  # passes AA body text
