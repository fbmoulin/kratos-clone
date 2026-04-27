"""Stage 6 — capture quality validation gate.

Replaces the hardcoded ``DTCG_CATEGORIES`` literal in
``scripts/generate_design_system_v2.py`` (audit P2-8) with an inventory-driven
scorecard. Also performs three orthogonal checks every captured site should
pass before being shipped:

1. **Coverage scorecard** — for each of the 13 W3C DTCG (Design Tokens
   Community Group) categories, mark ``full | partial | missing`` based on
   evidence in ``_inventory.json``. NOT hardcoded.
2. **Asset reference resolution** — every ``src=/href=`` pointing at
   ``assets/<file>`` must resolve to a real file on disk.
3. **Placeholder grep** — flag suspicious filler text (``lorem ipsum``,
   ``placeholder``, ``your headline here``, etc.) that suggests a stub left
   behind during personalization.
4. **WCAG contrast** — for every inline ``style="color:X;background:Y"``,
   check the contrast ratio meets WCAG AA (>= 4.5:1 for body text).

Visual diff via Playwright is intentionally NOT part of this MVP — it's
deferred to a follow-on so the validation gate stays headless and fast
enough for CI.

Usage (CLI):
    python -m scripts.validate <capture_dir> [--output report.json]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import structlog
from bs4 import BeautifulSoup

log = structlog.get_logger()


# --- Coverage scorecard ----------------------------------------------------

DTCG_CATEGORIES = (
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
)


def coverage_scorecard(inventory: dict[str, Any]) -> list[dict[str, Any]]:
    """Compute a 13-row DTCG coverage scorecard from the inventory.

    Status mapping (data-driven, not hardcoded):
    - ``full`` — strong evidence in inventory
    - ``partial`` — some evidence but incomplete
    - ``missing`` — no evidence found

    Returns one dict per category: ``{category, status, evidence}``.
    """
    rows: list[dict[str, Any]] = []
    for cat in DTCG_CATEGORIES:
        status, evidence = _judge_category(cat, inventory)
        rows.append({"category": cat, "status": status, "evidence": evidence})
    return rows


def _judge_category(cat: str, inv: dict[str, Any]) -> tuple[str, str]:
    """Per-category heuristic. Each branch reads the inventory rather than
    hardcoding. Add new categories here as the inventory schema grows."""
    if cat == "color":
        n_arb = len(inv.get("arbitrary_colors", []))
        n_named = len(inv.get("named_color_tokens", []))
        if n_arb + n_named >= 3:
            return "full", f"{n_arb} hex + {n_named} named tokens"
        if n_arb + n_named > 0:
            return "partial", f"{n_arb} hex + {n_named} named tokens"
        return "missing", "no color tokens in inventory"
    if cat == "dimension":
        n = len(inv.get("containers", [])) + len(inv.get("v_rhythm", []))
        return ("full" if n >= 3 else "partial" if n else "missing"), f"{n} tokens"
    if cat == "fontFamily":
        n = len(inv.get("font_families", []))
        return ("full" if n >= 2 else "partial" if n else "missing"), f"{n} families"
    if cat == "fontWeight":
        n = len(inv.get("font_weights", []))
        return ("full" if n >= 3 else "partial" if n else "missing"), f"{n} weights"
    if cat == "duration":
        n = len(inv.get("durations", []))
        return ("full" if n >= 2 else "partial" if n else "missing"), f"{n} values"
    if cat == "cubicBezier":
        n = len(inv.get("cubic_beziers", []))
        return ("full" if n >= 2 else "partial" if n else "missing"), f"{n} curves"
    if cat == "number":
        n = len(inv.get("z_indexes", [])) + len(inv.get("opacities", []))
        return (
            "full" if n >= 2 else "partial" if n else "missing"
        ), f"{n} numeric tokens"
    if cat == "typography":
        headings = inv.get("headings", {})
        levels = sum(1 for k in ("h1", "h2", "h3", "h4") if headings.get(k))
        n_p = len(inv.get("paragraphs", []))
        if levels >= 3 and n_p:
            return "full", f"{levels} heading levels + {n_p} paragraphs"
        if levels or n_p:
            return "partial", f"{levels} heading levels + {n_p} paragraphs"
        return "missing", "no headings or paragraphs"
    if cat == "shadow":
        n = len(inv.get("shadows", []))
        return ("full" if n else "missing"), f"{n} shadows"
    if cat == "gradient":
        n = len(inv.get("gradients", []))
        return ("full" if n else "missing"), f"{n} gradients"
    if cat == "transition":
        n = len(inv.get("transitions", []))
        return ("full" if n else "missing"), f"{n} transitions"
    if cat == "strokeStyle":
        n = len(inv.get("stroke_styles", []))
        return ("full" if n else "missing"), f"{n} stroke styles"
    if cat == "border":
        n = len(inv.get("borders", []))
        return ("full" if n else "missing"), f"{n} border tokens"
    return "missing", "unknown category"


# --- Asset reference resolution -------------------------------------------


def check_asset_refs(capture_dir: Path) -> list[str]:
    """Return relative paths under ``assets/`` referenced by HTML but missing on disk.

    External URLs (``http(s)://`` or ``//host/``) are ignored.
    """
    capture_dir = Path(capture_dir)
    html_path = capture_dir / "index.html"
    if not html_path.exists():
        return []
    soup = BeautifulSoup(html_path.read_text(encoding="utf-8"), "html.parser")
    missing: list[str] = []
    for attr in ("src", "href"):
        for tag in soup.find_all(**{attr: True}):
            value = tag.get(attr)
            if not isinstance(value, str) or not value.startswith("assets/"):
                continue
            if not (capture_dir / value).exists():
                missing.append(value)
    return sorted(set(missing))


# --- Placeholder grep -----------------------------------------------------

_PLACEHOLDER_PATTERNS = (
    re.compile(r"\blorem\s+ipsum\b", re.I),
    re.compile(r"\byour\s+(headline|copy|text|tagline)\s+here\b", re.I),
    re.compile(r"\bplaceholder\b", re.I),
    re.compile(r"\btodo[: ]", re.I),
    re.compile(r"\bfixme\b", re.I),
    re.compile(r"\b(foo|bar|baz)\b", re.I),
)


def check_placeholders(capture_dir: Path) -> list[str]:
    """Return text snippets matching placeholder patterns in ``index.html``."""
    html_path = Path(capture_dir) / "index.html"
    if not html_path.exists():
        return []
    soup = BeautifulSoup(html_path.read_text(encoding="utf-8"), "html.parser")
    text = soup.get_text(separator=" ")
    hits: list[str] = []
    for pattern in _PLACEHOLDER_PATTERNS:
        for match in pattern.finditer(text):
            hits.append(match.group(0))
    return hits


# --- WCAG contrast --------------------------------------------------------


def hex_to_rgb(value: str) -> tuple[int, int, int]:
    """Parse a 3- or 6-digit hex color. Raises ``ValueError`` on invalid input."""
    s = value.lstrip("#").lower()
    if len(s) == 3:
        s = "".join(ch * 2 for ch in s)
    if len(s) != 6 or not all(c in "0123456789abcdef" for c in s):
        raise ValueError(f"invalid hex color: {value!r}")
    return int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)


def _rel_luminance(rgb: tuple[int, int, int]) -> float:
    def chan(c: int) -> float:
        x = c / 255
        return x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4

    r, g, b = rgb
    return 0.2126 * chan(r) + 0.7152 * chan(g) + 0.0722 * chan(b)


def contrast_ratio(fg: str, bg: str) -> float:
    """WCAG 2.1 §1.4.3 contrast ratio. 21:1 black-on-white, 1:1 same color."""
    l1 = _rel_luminance(hex_to_rgb(fg))
    l2 = _rel_luminance(hex_to_rgb(bg))
    bright, dim = (l1, l2) if l1 >= l2 else (l2, l1)
    return (bright + 0.05) / (dim + 0.05)


_INLINE_COLOR_RE = re.compile(r"color\s*:\s*(#[0-9a-fA-F]{3,6})", re.I)
_INLINE_BG_RE = re.compile(r"background(?:-color)?\s*:\s*(#[0-9a-fA-F]{3,6})", re.I)


def check_wcag_contrast(
    capture_dir: Path, *, min_ratio: float = 4.5
) -> list[dict[str, Any]]:
    """Return inline-styled text elements failing AA contrast (default 4.5:1).

    Only inspects elements that declare BOTH ``color:`` AND ``background:``
    (or ``background-color:``) in an inline ``style=`` — broader CSS
    inheritance is out of scope without a real browser.
    """
    html_path = Path(capture_dir) / "index.html"
    if not html_path.exists():
        return []
    soup = BeautifulSoup(html_path.read_text(encoding="utf-8"), "html.parser")
    fails: list[dict[str, Any]] = []
    for tag in soup.find_all(style=True):
        style = tag.get("style") or ""
        fg_match = _INLINE_COLOR_RE.search(style)
        bg_match = _INLINE_BG_RE.search(style)
        if not (fg_match and bg_match):
            continue
        fg, bg = fg_match.group(1), bg_match.group(1)
        try:
            ratio = contrast_ratio(fg, bg)
        except ValueError:
            continue
        if ratio < min_ratio:
            fails.append(
                {
                    "tag": tag.name,
                    "fg": fg,
                    "bg": bg,
                    "ratio": round(ratio, 2),
                    "min_required": min_ratio,
                    "snippet": tag.get_text(strip=True)[:80],
                }
            )
    return fails


# --- run_validate end-to-end ----------------------------------------------


@dataclass
class ValidationReport:
    capture_dir: str
    passed: bool
    missing_assets: list[str] = field(default_factory=list)
    placeholder_hits: list[str] = field(default_factory=list)
    contrast_failures: list[dict[str, Any]] = field(default_factory=list)
    coverage: list[dict[str, Any]] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True)


def run_validate(capture_dir: Path) -> ValidationReport:
    """Run all four checks and return a single report.

    ``passed`` is True iff every check has zero findings.
    """
    capture_dir = Path(capture_dir)
    inventory_path = capture_dir / "_inventory.json"
    inventory: dict[str, Any] = (
        json.loads(inventory_path.read_text(encoding="utf-8"))
        if inventory_path.exists()
        else {}
    )
    coverage = coverage_scorecard(inventory)
    missing = check_asset_refs(capture_dir)
    placeholders = check_placeholders(capture_dir)
    contrast = check_wcag_contrast(capture_dir)
    passed = not (missing or placeholders or contrast)
    log.info(
        "validate_complete",
        capture_dir=str(capture_dir),
        passed=passed,
        missing_assets=len(missing),
        placeholders=len(placeholders),
        contrast_failures=len(contrast),
    )
    return ValidationReport(
        capture_dir=str(capture_dir),
        passed=passed,
        missing_assets=missing,
        placeholder_hits=placeholders,
        contrast_failures=contrast,
        coverage=coverage,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m scripts.validate")
    parser.add_argument("capture_dir", type=Path, help="capture directory")
    parser.add_argument(
        "--output",
        default="-",
        help="path to write JSON report (default: stdout)",
    )
    args = parser.parse_args(argv)
    report = run_validate(args.capture_dir)
    payload = report.to_json()
    if args.output == "-":
        print(payload)
    else:
        Path(args.output).write_text(payload, encoding="utf-8")
        print(f"wrote {args.output}", file=sys.stderr)
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
