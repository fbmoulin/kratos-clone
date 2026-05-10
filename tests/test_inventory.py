"""Tests for scripts.inventory — DTCG extractors + module orchestrator."""

from __future__ import annotations

from pathlib import Path

from bs4 import BeautifulSoup

from scripts.inventory import (
    build_inventory,
    extract_borders,
    extract_durations,
    extract_font_families,
    extract_font_weights,
    extract_gradients,
    extract_shadows,
)


def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


# --- extract_font_families ------------------------------------------------


def test_extract_font_families_from_google_link():
    html = (
        '<head><link rel="stylesheet" '
        'href="https://fonts.googleapis.com/css2?family=Inter&family=Roboto+Mono">'
        "</head>"
    )
    fams = extract_font_families(_soup(html), css_text="")
    assert "Inter" in fams
    assert "Roboto Mono" in fams


def test_extract_font_families_filters_generics_and_dedupes():
    css = (
        "body { font-family: 'Inter', sans-serif; }\n"
        'h1 { font-family: "INTER", system-ui; }\n'
        "code { font-family: monospace; }"
    )
    fams = extract_font_families(_soup(""), css)
    # 'Inter' appears once (case-insensitive dedupe); 'monospace'/'system-ui' filtered.
    assert [f.lower() for f in fams] == ["inter"]


# --- extract_font_weights -------------------------------------------------


def test_extract_font_weights_numeric_and_named():
    css = "h1{font-weight:600}p{font-weight:bold}span{font-weight: lighter}"
    weights = extract_font_weights(css)
    assert weights == [300, 600, 700]


def test_extract_font_weights_ignores_out_of_range():
    css = "x{font-weight:999}y{font-weight:50}z{font-weight:400}"
    weights = extract_font_weights(css)
    assert weights == [400]


# --- extract_durations ----------------------------------------------------


def test_extract_durations_parses_and_sorts():
    css = "a{transition: opacity 200ms, transform .3s}"
    durs = extract_durations(css)
    assert durs == ["200ms", "0.3s"]


def test_extract_durations_dedupes_across_decls():
    css = "a{transition-duration:150ms}b{animation-duration:150ms}c{transition:all 1s}"
    durs = extract_durations(css)
    assert durs == ["150ms", "1s"]


# --- extract_shadows ------------------------------------------------------


def test_extract_shadows_box_and_drop_shadow():
    css = "a{box-shadow: 0 1px 2px rgba(0,0,0,.1)}\nb{filter: drop-shadow(0 0 6px red)}\n"
    shadows = extract_shadows(css)
    assert "0 1px 2px rgba(0,0,0,.1)" in shadows
    assert "drop-shadow(0 0 6px red)" in shadows


def test_extract_shadows_skips_none():
    css = "a{box-shadow: none}b{box-shadow: inherit}c{box-shadow: 0 0 1px #000}"
    shadows = extract_shadows(css)
    assert shadows == ["0 0 1px #000"]


# --- extract_gradients ----------------------------------------------------


def test_extract_gradients_linear_and_radial():
    css = (
        "a{background: linear-gradient(90deg, #000, #fff)}\n"
        "b{background-image: radial-gradient(circle, red, blue)}"
    )
    grads = extract_gradients(css)
    assert any(g.startswith("linear-gradient(") for g in grads)
    assert any(g.startswith("radial-gradient(") for g in grads)


def test_extract_gradients_skips_plain_colors():
    css = "a{background: #fff}b{color: rgb(0,0,0)}"
    assert extract_gradients(css) == []


# --- extract_borders ------------------------------------------------------


def test_extract_borders_captures_shorthand_skips_none():
    css = "a{border: 1px solid #fff}b{border: none}c{border-top: 2px dashed #abc}"
    borders = extract_borders(css)
    assert "1px solid #fff" in borders
    assert "2px dashed #abc" in borders
    assert "none" not in borders


# --- build_inventory integration -----------------------------------------


def test_build_inventory_emits_all_six_new_keys(tmp_path: Path):
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "main.css").write_text(
        "body{font-family:'Inter',sans-serif;font-weight:600;"
        "transition:opacity 200ms;"
        "box-shadow:0 1px 2px rgba(0,0,0,.1);"
        "background:linear-gradient(90deg,#000,#fff);"
        "border:1px solid #ccc}"
    )
    (tmp_path / "index.html").write_text(
        '<html><head><link href="https://fonts.googleapis.com/css2?family=Roboto"></head>'
        '<body><section id="hero"><h1>Hi</h1></section></body></html>'
    )

    inv = build_inventory(tmp_path)

    # Key names must match scripts.validate.coverage_scorecard expectations.
    for key in ("font_families", "font_weights", "durations", "shadows", "gradients", "borders"):
        assert key in inv, f"missing key: {key}"
        assert inv[key], f"empty value for: {key}"

    assert "Roboto" in inv["font_families"]
    assert 600 in inv["font_weights"]
    assert "200ms" in inv["durations"]
    assert any("rgba(0,0,0,.1)" in s for s in inv["shadows"])
    assert any("linear-gradient" in g for g in inv["gradients"])
    assert any("solid" in b for b in inv["borders"])
