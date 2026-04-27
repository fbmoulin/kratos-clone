"""Tests for scripts.validate — Stage 6 capture quality gate."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.validate import (
    ValidationReport,
    check_asset_refs,
    check_placeholders,
    check_wcag_contrast,
    coverage_scorecard,
    contrast_ratio,
    hex_to_rgb,
    run_validate,
)


# --- coverage_scorecard ---------------------------------------------------


class TestCoverageScorecard:
    def test_full_when_color_evidence_present(self):
        inv = {"arbitrary_colors": ["#fff", "#000"], "named_color_tokens": ["red"]}
        score = coverage_scorecard(inv)
        color = next(s for s in score if s["category"] == "color")
        assert color["status"] == "full"
        assert "2 hex" in color["evidence"] or "2" in color["evidence"]

    def test_missing_when_no_evidence(self):
        score = coverage_scorecard({})
        for cat in ("color", "dimension", "typography"):
            row = next(s for s in score if s["category"] == cat)
            assert row["status"] == "missing"

    def test_returns_one_row_per_dtcg_category(self):
        score = coverage_scorecard({})
        cats = {s["category"] for s in score}
        # All 13 W3C DTCG categories should be represented.
        expected = {
            "color",
            "dimension",
            "fontFamily",
            "fontWeight",
            "duration",
            "cubicBezier",
            "number",
            "typography",
            "shadow",
            "gradient",
            "transition",
            "strokeStyle",
            "border",
        }
        assert cats == expected

    def test_partial_typography(self):
        # Only h1 + paragraphs present → partial
        inv = {
            "headings": {"h1": ["Hello"], "h2": [], "h3": [], "h4": []},
            "paragraphs": ["a", "b"],
        }
        score = coverage_scorecard(inv)
        typ = next(s for s in score if s["category"] == "typography")
        assert typ["status"] in ("partial", "full")

    def test_full_typography_with_all_levels(self):
        inv = {
            "headings": {
                "h1": ["a"],
                "h2": ["b"],
                "h3": ["c"],
                "h4": ["d"],
            },
            "paragraphs": ["p1", "p2"],
        }
        score = coverage_scorecard(inv)
        typ = next(s for s in score if s["category"] == "typography")
        assert typ["status"] == "full"


# --- check_asset_refs -----------------------------------------------------


class TestCheckAssetRefs:
    def test_resolved_when_all_files_exist(self, tmp_path: Path):
        (tmp_path / "assets").mkdir()
        (tmp_path / "assets" / "a.png").write_bytes(b"x")
        (tmp_path / "index.html").write_text(
            '<img src="assets/a.png"><a href="https://x.com">e</a>'
        )
        missing = check_asset_refs(tmp_path)
        assert missing == []

    def test_reports_missing_files(self, tmp_path: Path):
        (tmp_path / "index.html").write_text(
            '<img src="assets/missing.png"><link href="assets/style.css">'
        )
        missing = check_asset_refs(tmp_path)
        assert set(missing) == {"assets/missing.png", "assets/style.css"}

    def test_ignores_external_urls(self, tmp_path: Path):
        (tmp_path / "index.html").write_text(
            '<img src="https://cdn.example/x.png"><link href="//other.example/y.css">'
        )
        assert check_asset_refs(tmp_path) == []


# --- check_placeholders ---------------------------------------------------


class TestCheckPlaceholders:
    def test_finds_lorem_ipsum(self, tmp_path: Path):
        (tmp_path / "index.html").write_text("<p>Lorem ipsum dolor sit amet</p>")
        hits = check_placeholders(tmp_path)
        assert any("lorem" in h.lower() for h in hits)

    def test_finds_placeholder_text(self, tmp_path: Path):
        (tmp_path / "index.html").write_text("<h1>Your headline here</h1>")
        hits = check_placeholders(tmp_path)
        assert hits  # at least one match

    def test_clean_html_no_hits(self, tmp_path: Path):
        (tmp_path / "index.html").write_text("<h1>Real product</h1>")
        assert check_placeholders(tmp_path) == []


# --- WCAG contrast --------------------------------------------------------


class TestContrast:
    def test_hex_to_rgb_basic(self):
        assert hex_to_rgb("#000000") == (0, 0, 0)
        assert hex_to_rgb("#ffffff") == (255, 255, 255)
        assert hex_to_rgb("ff0000") == (255, 0, 0)

    def test_hex_to_rgb_invalid_raises(self):
        with pytest.raises(ValueError):
            hex_to_rgb("xyz")

    def test_contrast_black_on_white_is_21(self):
        ratio = contrast_ratio("#000000", "#ffffff")
        assert 20.99 < ratio < 21.01

    def test_contrast_same_color_is_1(self):
        assert contrast_ratio("#888888", "#888888") == pytest.approx(1.0, abs=0.001)

    def test_check_wcag_contrast_returns_failures(self, tmp_path: Path):
        # White text on white background — clearly fails.
        (tmp_path / "index.html").write_text(
            '<p style="color:#ffffff;background:#ffffff">invisible</p>'
        )
        fails = check_wcag_contrast(tmp_path)
        assert fails  # at least one failure

    def test_check_wcag_contrast_pass_high_contrast(self, tmp_path: Path):
        (tmp_path / "index.html").write_text(
            '<p style="color:#000000;background:#ffffff">readable</p>'
        )
        fails = check_wcag_contrast(tmp_path)
        assert fails == []


# --- run_validate end-to-end ----------------------------------------------


class TestRunValidate:
    @pytest.fixture
    def good_capture(self, tmp_path: Path) -> Path:
        (tmp_path / "assets").mkdir()
        (tmp_path / "assets" / "a.png").write_bytes(b"\x89PNG\r\n\x1a\n")
        (tmp_path / "index.html").write_text(
            "<html><body>"
            '<img src="assets/a.png">'
            '<p style="color:#000;background:#fff">Real product copy</p>'
            "</body></html>"
        )
        (tmp_path / "_inventory.json").write_text(
            json.dumps(
                {
                    "arbitrary_colors": ["#fff", "#000"],
                    "named_color_tokens": ["primary"],
                    "headings": {"h1": ["a"], "h2": [], "h3": [], "h4": []},
                    "paragraphs": ["p"],
                }
            )
        )
        return tmp_path

    def test_returns_report(self, good_capture):
        report = run_validate(good_capture)
        assert isinstance(report, ValidationReport)
        assert report.passed is True
        assert report.missing_assets == []
        assert report.placeholder_hits == []
        assert report.contrast_failures == []
        assert any(
            s["status"] in ("full", "partial", "missing") for s in report.coverage
        )

    def test_failed_when_assets_missing(self, good_capture):
        good_capture.joinpath("assets/a.png").unlink()
        report = run_validate(good_capture)
        assert report.passed is False
        assert "assets/a.png" in report.missing_assets

    def test_failed_when_placeholders_present(self, good_capture):
        good_capture.joinpath("index.html").write_text(
            "<p>Lorem ipsum dolor sit amet</p>"
        )
        report = run_validate(good_capture)
        assert report.passed is False
        assert report.placeholder_hits

    def test_to_json_roundtrip(self, good_capture):
        report = run_validate(good_capture)
        as_json = report.to_json()
        parsed = json.loads(as_json)
        assert "passed" in parsed
        assert "coverage" in parsed
