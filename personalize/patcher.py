"""Step 7 — apply patches to captured HTML.

Mutates a captured ``index.html`` with the personalize plan output:
1. Text patches (with optional ``word-wrappers`` structure-aware split)
2. Tailwind palette regex swap (``orange-{400,500,600}`` → brand hex)
3. Image swaps (write generated PNG bytes, update ``<img src>``)

Every text value gets ``strip_dangerous_html`` applied as defense-in-depth
even though the strict JSON schema for the personalize call does not
allow HTML in text fields.
"""

from __future__ import annotations

import base64
import re
from collections.abc import Mapping
from copy import copy
from pathlib import Path
from typing import Any

import structlog
from bs4 import BeautifulSoup, Tag

from .sanitize import strip_dangerous_html

log = structlog.get_logger()

_TAILWIND_PREFIXES = ("from", "to", "via", "bg", "text", "border", "shadow", "ring")
_PREFIX_GROUP = "|".join(_TAILWIND_PREFIXES)


def apply_personalization(
    html_path: Path,
    plan: dict[str, Any],
    images: Mapping[str, bytes | str],
    slots: list[dict[str, Any]],
    out_path: Path,
) -> None:
    """Apply ``plan`` to the HTML at ``html_path`` and write to ``out_path``.

    ``plan`` shape: ``{palette: {...}, patches: [{slot_id, value}], images: [...]}``
    ``images``: ``{slot_id: png_bytes}`` (already base64-decoded if returned from API)
    ``slots``: full slot list from ``extract_slots``; used to resolve selectors.
    """
    html_path = Path(html_path)
    out_path = Path(out_path)
    soup = BeautifulSoup(html_path.read_text(encoding="utf-8"), "html.parser")
    slot_map = {s["id"]: s for s in slots}

    _apply_text_patches(soup, plan.get("patches", []), slot_map)

    palette = plan.get("palette", {})
    if palette:
        soup = _apply_palette(soup, palette)

    _apply_image_patches(soup, images, slot_map, out_path.parent)

    out_path.write_text(str(soup), encoding="utf-8")
    log.info(
        "personalization_applied",
        out_path=str(out_path),
        text_patches=len(plan.get("patches", [])),
        images=len(images),
    )


def _apply_text_patches(
    soup: BeautifulSoup,
    patches: list[dict[str, Any]],
    slot_map: dict[str, dict[str, Any]],
) -> None:
    for patch in patches:
        slot_id = patch.get("slot_id")
        if slot_id not in slot_map:
            log.warning("unknown_slot_id", slot_id=slot_id)
            continue
        slot = slot_map[slot_id]
        target = soup.select_one(slot["selector"])
        if target is None:
            log.info("selector_no_match", slot_id=slot_id, selector=slot["selector"])
            continue
        value = strip_dangerous_html(str(patch.get("value", "")))
        # strip_dangerous_html returns a serialized fragment; for plain text we
        # want only visible text content (no leftover tags from sanitization).
        clean_text = BeautifulSoup(value, "html.parser").get_text()
        if slot.get("structure") == "word-wrappers":
            _apply_word_wrappers(target, clean_text)
        else:
            target.clear()
            target.append(clean_text)


def _apply_word_wrappers(target: Tag, value: str) -> None:
    words = value.split()
    if not words:
        return
    wrappers = target.select(".word-wrapper")
    if not wrappers:
        # Fallback: just replace text content.
        target.clear()
        target.append(value)
        return
    template = copy(wrappers[0])
    template_inner = template.select_one(".word-inner")
    if template_inner is None:
        target.clear()
        target.append(value)
        return
    # Reuse existing wrappers for the first N words; append clones for extras.
    for index, wrapper in enumerate(wrappers):
        inner = wrapper.select_one(".word-inner")
        if inner is None:
            continue
        if index < len(words):
            inner.clear()
            inner.append(words[index] + (" " if index < len(words) - 1 else ""))
        else:
            wrapper.decompose()
    if len(words) > len(wrappers):
        for word in words[len(wrappers) :]:
            clone = copy(template)
            inner = clone.select_one(".word-inner")
            if inner is None:
                continue
            inner.clear()
            inner.append(word + " ")
            target.append(clone)


def _apply_palette(soup: BeautifulSoup, palette: dict[str, str]) -> BeautifulSoup:
    """Swap Tailwind orange-{400,500,600} classes for brand-color arbitrary values.

    Iterates every element's ``class`` attribute and rewrites class tokens
    individually. Originally implemented as a regex on the serialized HTML +
    re-parse, which Gemini bot review flagged as a correctness risk: text
    content or IDs containing the literal string ``from-orange-500`` would
    have been rewritten too. Iterating the DOM scopes the swap to actual
    class attributes.
    """
    primary = palette["primary"].lstrip("#")
    primary_hover = palette["primary_hover"].lstrip("#")
    primary_pressed = palette["primary_pressed"].lstrip("#")
    swap_map = {
        "500": f"[#{primary}]",
        "600": f"[#{primary_pressed}]",
        "400": f"[#{primary_hover}]",
    }
    token_re = re.compile(rf"^({_PREFIX_GROUP})-orange-(400|500|600)$")

    for tag in soup.find_all(class_=True):
        raw = tag.get("class")
        # ``class`` may be a single string (when parsed by html.parser) or a
        # list (BeautifulSoup multi-valued attribute with lxml). Normalize.
        tokens: list[str]
        if isinstance(raw, str):
            tokens = raw.split()
        elif raw is None:
            tokens = []
        else:
            tokens = list(raw)
        new_classes: list[str] = []
        for token in tokens:
            match = token_re.match(token)
            if match:
                prefix, shade = match.groups()
                new_classes.append(f"{prefix}-{swap_map[shade]}")
            else:
                new_classes.append(token)
        # bs4 accepts list[str] as a multi-valued attr; serialization joins on space.
        tag["class"] = " ".join(new_classes)
    return soup


def _apply_image_patches(
    soup: BeautifulSoup,
    images: Mapping[str, bytes | str],
    slot_map: dict[str, dict[str, Any]],
    out_dir: Path,
) -> None:
    if not images:
        return
    assets_dir = out_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    for slot_id, payload in images.items():
        slot = slot_map.get(slot_id)
        if slot is None:
            log.warning("unknown_image_slot", slot_id=slot_id)
            continue
        # Accept either raw bytes (from gpt-image-1 result) or a base64 string
        # (from older callers / serialized plans).
        raw: bytes = base64.b64decode(payload) if isinstance(payload, str) else payload
        fname = f"gen_{slot_id.replace('.', '_')}.png"
        (assets_dir / fname).write_bytes(raw)
        target = soup.select_one(slot["selector"])
        if target is None:
            log.info("image_selector_no_match", slot_id=slot_id)
            continue
        target["src"] = f"assets/{fname}"
