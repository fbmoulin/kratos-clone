"""Extract design system inventory from downloaded index.html.

Outputs JSON to stdout (or ``--output``) for use in design-system.html generation.

This module is importable: ``build_inventory(capture_dir)`` returns the inventory
dict, and ``main(argv)`` provides the CLI shim. Run as
``python -m scripts.inventory`` or ``python scripts/inventory.py``.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup, Tag
from bs4.element import AttributeValueList


def _as_str(v: str | AttributeValueList | None) -> str:
    """Narrow BS4's ``Tag.get(attr)`` return value to ``str``.

    BS4 types attribute access as ``str | AttributeValueList | None``; for
    URL- and text-bearing attributes we touch (``href``, ``style``,
    ``content``), real-world HTML5 always yields ``str`` (or ``None`` if
    missing). Joins multi-valued attrs with ``" "`` for the unreachable
    case.
    """
    if v is None:
        return ""
    return v if isinstance(v, str) else " ".join(v)


def _classes_of(el: Tag) -> list[str]:
    """Return the element's ``class`` attribute as a list of strings.

    ``el.get("class", [])`` returns ``str | AttributeValueList | None``.
    HTML5 multi-valued attrs come back as ``AttributeValueList`` (already
    list-like); a single class value comes back as ``str``; the default
    ``[]`` we pass is ``list[Any]``. This helper coerces all three to
    ``list[str]`` for downstream iteration / membership / counter ops.
    """
    v = el.get("class")
    if v is None:
        return []
    if isinstance(v, str):
        return v.split()
    return [str(c) for c in v]


# --- Module-level regexes (compile once) ----------------------------------

_FONT_FAMILY_RE = re.compile(r"font-family\s*:\s*([^;}\n]+)", re.I)
_GFONTS_RE = re.compile(r"family=([A-Za-z0-9+_]+)")
_FONT_WEIGHT_RE = re.compile(r"font-weight\s*:\s*([^;}\n]+)", re.I)
_DURATION_DECL_RE = re.compile(
    r"(?:transition-duration|animation-duration|transition|animation)\s*:\s*([^;}\n]+)",
    re.I,
)
_DUR_TOKEN_RE = re.compile(r"(\d+(?:\.\d+)?|\.\d+)(ms|s)\b", re.I)
_SHADOW_RE = re.compile(r"(?:box-shadow|filter)\s*:\s*([^;}\n]+)", re.I)
_DROP_SHADOW_RE = re.compile(r"drop-shadow\(([^)]+)\)", re.I)
_GRADIENT_RE = re.compile(r"(linear-gradient|radial-gradient|conic-gradient)\s*\([^)]*\)", re.I)
_BORDER_RE = re.compile(r"border(?:-(?:top|right|bottom|left))?\s*:\s*([^;}\n]+)", re.I)


# --- New extractors (Phase 5: lifts DTCG scorecard from ~50% to ~85%) -----


def extract_font_families(soup: BeautifulSoup, css_text: str) -> list[str]:
    """Inventory key: 'font_families'. Filters generic fallbacks."""
    fams: list[str] = []
    for link in soup.find_all("link", href=True):
        href = _as_str(link.get("href"))
        if "fonts.googleapis" in href or "fonts.gstatic" in href:
            for m in _GFONTS_RE.finditer(href):
                fams.append(m.group(1).replace("+", " "))
    for m in _FONT_FAMILY_RE.finditer(css_text):
        first = m.group(1).split(",")[0].strip().strip("\"'")
        if first and first.lower() not in {
            "inherit",
            "initial",
            "unset",
            "sans-serif",
            "serif",
            "monospace",
            "system-ui",
            "ui-sans-serif",
            "ui-serif",
            "ui-monospace",
            "cursive",
            "fantasy",
        }:
            fams.append(first)
    seen: set[str] = set()
    out: list[str] = []
    for f in fams:
        key = f.lower()
        if key not in seen:
            seen.add(key)
            out.append(f)
    return out


def extract_font_weights(css_text: str) -> list[int]:
    """Inventory key: 'font_weights'. Numeric values + named keyword normalization."""
    NAMED = {"normal": 400, "bold": 700, "lighter": 300, "bolder": 700}
    seen: set[int] = set()
    out: list[int] = []
    for m in _FONT_WEIGHT_RE.finditer(css_text):
        val = m.group(1).strip().lower()
        if val.isdigit():
            try:
                w = int(val)
            except ValueError:
                continue
        elif val in NAMED:
            w = NAMED[val]
        else:
            continue
        if 100 <= w <= 900 and w not in seen:
            seen.add(w)
            out.append(w)
    return sorted(out)


def extract_durations(css_text: str) -> list[str]:
    """Inventory key: 'durations'. Sorted by ms-equivalent."""
    seen: set[str] = set()
    raw: list[tuple[float, str]] = []
    for m in _DURATION_DECL_RE.finditer(css_text):
        for t in _DUR_TOKEN_RE.finditer(m.group(1)):
            num, unit = t.group(1), t.group(2).lower()
            value = float(num)
            # Normalize: integers stay integral ("200ms"), fractional values
            # render with a leading zero ("0.3s" not ".3s") and no trailing zeros.
            tok = f"{int(value)}{unit}" if value.is_integer() else f"{value:g}{unit}"
            if tok not in seen:
                seen.add(tok)
                ms = value * (1.0 if unit == "ms" else 1000.0)
                raw.append((ms, tok))
    raw.sort(key=lambda x: x[0])
    return [tok for _, tok in raw]


def extract_shadows(css_text: str) -> list[str]:
    """Inventory key: 'shadows'. Captures box-shadow values + filter:drop-shadow(...)."""
    seen: set[str] = set()
    out: list[str] = []
    for m in _SHADOW_RE.finditer(css_text):
        val = m.group(1).strip()
        # filter: drop-shadow(...) — keep only the drop-shadow tokens
        had_ds = False
        for ds in _DROP_SHADOW_RE.finditer(val):
            tok = f"drop-shadow({ds.group(1).strip()})"
            if tok not in seen:
                seen.add(tok)
                out.append(tok)
            had_ds = True
        if (
            not had_ds
            and val.lower() not in {"none", "inherit", "initial", "unset"}
            and val not in seen
        ):
            seen.add(val)
            out.append(val)
    return out


def extract_gradients(css_text: str) -> list[str]:
    """Inventory key: 'gradients'. Linear/radial/conic gradient functions."""
    seen: set[str] = set()
    out: list[str] = []
    for m in _GRADIENT_RE.finditer(css_text):
        val = m.group(0).strip()
        if val not in seen:
            seen.add(val)
            out.append(val)
    return out


def extract_borders(css_text: str) -> list[str]:
    """Inventory key: 'borders'. Whole shorthand values, deduped."""
    seen: set[str] = set()
    out: list[str] = []
    for m in _BORDER_RE.finditer(css_text):
        val = " ".join(m.group(1).split()).strip()  # collapse whitespace
        if (
            val
            and val.lower() not in {"none", "inherit", "initial", "unset", "0"}
            and val not in seen
        ):
            seen.add(val)
            out.append(val)
    return out


# --- Existing 12 inventory sections (refactored to pure helpers) ----------


def extract_sections(soup: BeautifulSoup) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = []
    for s in soup.find_all("section"):
        sid = s.get("id") or ""
        h = s.find(["h1", "h2", "h3"])
        title = h.get_text(strip=True)[:80] if h else ""
        sections.append({"id": sid, "title": title, "classes": _classes_of(s)})
    return sections


def extract_styles(soup: BeautifulSoup) -> list[str]:
    """Original <style> blocks, excluding scroll-fix injections."""
    styles: list[str] = []
    for st in soup.find_all("style"):
        if st.get("data-scroll-fix"):
            continue
        txt = (st.string or "").strip()
        if txt:
            styles.append(txt)
    return styles


def extract_headings(soup: BeautifulSoup) -> dict[str, list[dict[str, str]]]:
    """Heading inventory by tag, deduped by class signature."""
    headings: dict[str, list[dict[str, str]]] = {}
    for tag in ["h1", "h2", "h3", "h4", "h5", "h6"]:
        seen: dict[str, str] = {}
        for el in soup.find_all(tag):
            cls = " ".join(_classes_of(el))
            if cls not in seen:
                seen[cls] = el.get_text(strip=True)[:60]
        headings[tag] = [{"classes": k, "sample": v} for k, v in seen.items()]
    return headings


def extract_paragraphs(soup: BeautifulSoup) -> list[dict[str, Any]]:
    """Paragraph variants grouped by class signature, top 10."""
    p_signatures: Counter[str] = Counter()
    p_samples: dict[str, str] = {}
    for p in soup.find_all("p"):
        cls = " ".join(_classes_of(p))
        if not cls:
            continue
        p_signatures[cls] += 1
        if cls not in p_samples:
            p_samples[cls] = p.get_text(strip=True)[:80]
    return [
        {"classes": c, "count": p_signatures[c], "sample": p_samples[c]}
        for c, _ in p_signatures.most_common(10)
    ]


def extract_buttons(soup: BeautifulSoup) -> list[dict[str, Any]]:
    """Buttons & links-as-buttons, top 8 unique class signatures."""
    buttons: list[dict[str, Any]] = []
    seen_btn_sigs: set[str] = set()
    for b in soup.find_all("button"):
        cls = " ".join(_classes_of(b))
        if cls and cls not in seen_btn_sigs:
            seen_btn_sigs.add(cls)
            buttons.append(
                {
                    "tag": "button",
                    "classes": cls,
                    "label": b.get_text(strip=True)[:40],
                    "html": str(b),
                }
            )
            if len(buttons) >= 8:
                break
    return buttons


def extract_color_tokens(soup: BeautifulSoup) -> tuple[Counter[str], Counter[str]]:
    """Tailwind arbitrary + named color class tokens."""
    arbitrary_colors: Counter[str] = Counter()
    for el in soup.find_all(True):
        for c in _classes_of(el):
            m = re.match(r"^(?:bg|text|border|from|to|via)-\[#([0-9a-fA-F]{3,8})\]$", c)
            if m:
                arbitrary_colors[c] += 1
    named_color_tokens: Counter[str] = Counter()
    for el in soup.find_all(True):
        for c in _classes_of(el):
            if re.match(
                r"^(?:bg|text|border)-(?:orange|neutral|white|black|gray|zinc|slate)-?[\w/]*$",
                c,
            ):
                named_color_tokens[c] += 1
    return arbitrary_colors, named_color_tokens


def extract_motion_classes(soup: BeautifulSoup) -> Counter[str]:
    """Animation/motion classes by pattern."""
    motion_classes: Counter[str] = Counter()
    motion_patterns = [
        "hero-fade",
        "gs-reveal",
        "word-wrapper",
        "word-inner",
        "perspective-container",
        "dashboard-plane",
        "scene-container",
        "border-gradient",
        "animate-",
    ]
    for el in soup.find_all(True):
        for c in _classes_of(el):
            for p in motion_patterns:
                if p in c:
                    motion_classes[c] += 1
    return motion_classes


def extract_icons(soup: BeautifulSoup) -> Counter[str]:
    icons: Counter[str] = Counter()
    for el in soup.find_all("iconify-icon"):
        icons[_as_str(el.get("icon"))] += 1
    return icons


def extract_glass_classes(soup: BeautifulSoup) -> Counter[str]:
    """Backdrop & glass utility classes."""
    glass_classes: Counter[str] = Counter()
    for el in soup.find_all(True):
        for c in _classes_of(el):
            if "backdrop-" in c or c.startswith("blur") or ("/" in c and "neutral" in c):
                glass_classes[c] += 1
    return glass_classes


def extract_containers(soup: BeautifulSoup) -> Counter[str]:
    """Container max-width tokens."""
    containers: Counter[str] = Counter()
    for el in soup.find_all(True):
        for c in _classes_of(el):
            if c.startswith("max-w-"):
                containers[c] += 1
    return containers


def extract_v_rhythm(soup: BeautifulSoup) -> Counter[str]:
    """Section vertical rhythm utility classes (py/pt/pb-N)."""
    v_rhythm: Counter[str] = Counter()
    for s in soup.find_all("section"):
        for c in _classes_of(s):
            if re.match(r"^(?:py|pt|pb)-\d+$", c):
                v_rhythm[c] += 1
    return v_rhythm


def extract_hero_html(soup: BeautifulSoup) -> str:
    first_section = soup.find("section")
    return str(first_section) if first_section else ""


# --- CSS gathering --------------------------------------------------------


def gather_css_text(capture_dir: Path) -> str:
    """Concatenate every inline ``<style>`` block from index.html and every
    ``*.css`` file under ``<capture_dir>/assets/`` into one string for the
    regex-based extractors.
    """
    capture_dir = Path(capture_dir)
    parts: list[str] = []
    html_path = capture_dir / "index.html"
    if html_path.exists():
        soup = BeautifulSoup(html_path.read_text(encoding="utf-8"), "html.parser")
        for st in soup.find_all("style"):
            txt = st.string or ""
            if txt:
                parts.append(txt)
    assets_dir = capture_dir / "assets"
    if assets_dir.is_dir():
        for css_path in sorted(assets_dir.glob("*.css")):
            try:
                parts.append(css_path.read_text(encoding="utf-8"))
            except OSError:
                continue
    return "\n".join(parts)


# --- Orchestrator ---------------------------------------------------------


def build_inventory(capture_dir: Path) -> dict[str, Any]:
    """Build the full inventory dict for a capture directory.

    Reads ``<capture_dir>/index.html`` plus any ``assets/*.css`` files; emits the
    same 12 historical sections plus the 6 new DTCG-scorecard extractors.
    """
    capture_dir = Path(capture_dir)
    html_path = capture_dir / "index.html"
    html = html_path.read_text(encoding="utf-8")
    soup = BeautifulSoup(html, "html.parser")
    css_text = gather_css_text(capture_dir)

    sections = extract_sections(soup)
    styles = extract_styles(soup)
    headings = extract_headings(soup)
    paragraphs = extract_paragraphs(soup)
    buttons = extract_buttons(soup)
    arbitrary_colors, named_color_tokens = extract_color_tokens(soup)
    motion_classes = extract_motion_classes(soup)
    icons = extract_icons(soup)
    glass_classes = extract_glass_classes(soup)
    containers = extract_containers(soup)
    v_rhythm = extract_v_rhythm(soup)
    hero_html = extract_hero_html(soup)

    out: dict[str, Any] = {
        "sections": sections,
        "styles_count": len(styles),
        "styles_total_kb": round(sum(len(s) for s in styles) / 1024, 1),
        "headings": headings,
        "paragraphs": paragraphs,
        "buttons": buttons,
        "arbitrary_colors": dict(arbitrary_colors.most_common(20)),
        "named_color_tokens": dict(named_color_tokens.most_common(30)),
        "motion_classes": dict(motion_classes.most_common(20)),
        "icons": dict(icons.most_common(40)),
        "icons_total": sum(icons.values()),
        "glass_classes": dict(glass_classes.most_common(15)),
        "containers": dict(containers.most_common(10)),
        "v_rhythm": dict(v_rhythm.most_common(10)),
        "hero_html_kb": round(len(hero_html) / 1024, 1),
        "total_html_kb": round(len(html) / 1024, 1),
    }

    # New DTCG-scorecard extractors (Phase 5).
    out["font_families"] = extract_font_families(soup, css_text)
    out["font_weights"] = extract_font_weights(css_text)
    out["durations"] = extract_durations(css_text)
    out["shadows"] = extract_shadows(css_text)
    out["gradients"] = extract_gradients(css_text)
    out["borders"] = extract_borders(css_text)

    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m scripts.inventory")
    parser.add_argument(
        "--capture-dir",
        type=Path,
        default=Path("."),
        help="capture directory containing index.html (default: .)",
    )
    parser.add_argument(
        "--output",
        default="-",
        help="path to write JSON inventory (default: stdout)",
    )
    args = parser.parse_args(argv)
    inventory = build_inventory(args.capture_dir)
    payload = json.dumps(inventory, indent=2, ensure_ascii=False)
    if args.output == "-":
        print(payload)
    else:
        Path(args.output).write_text(payload, encoding="utf-8")
        print(f"wrote {args.output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
