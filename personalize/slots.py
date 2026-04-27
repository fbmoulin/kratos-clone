"""Step 4 — deterministic slot extractor.

Maps the design-system inventory (output of ``scripts/inventory.py``) to a
flat list of personalizable slots. Each slot has a stable id, CSS selector,
type (``text`` | ``image``), and optional ``max_chars`` / dimensions.

The slot list is consumed by:
- :mod:`personalize.openai_client` to build a closed-enum strict JSON schema
- :mod:`personalize.patcher` to resolve patches back to DOM elements
"""

from __future__ import annotations

from typing import Any

import structlog

log = structlog.get_logger()

MAX_CHARS = {
    "BADGE": 30,
    "HERO_HEADLINE": 60,
    "HERO_SUBHEAD": 200,
    "CTA": 24,
    "FEATURE_TITLE": 30,
    "FEATURE_BODY": 140,
    "PRICING_TIER_NAME": 20,
    "PRICING_PRICE": 12,
}

_CTA_NAMES = ("primary", "secondary")


def extract_slots(inventory: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten an inventory dict into a slot list.

    Unknown section ``kind`` values are silently skipped — the design-system
    extractor may emit categories the personalization layer does not yet
    support, and that is not an error.
    """
    slots: list[dict[str, Any]] = []
    for section in inventory.get("sections", []):
        kind = section.get("kind")
        if kind == "hero":
            _emit_hero(section, slots)
        elif kind == "features":
            _emit_features(section, slots)
        elif kind == "pricing":
            _emit_pricing(section, slots)
        # else: skipped intentionally
    for image in inventory.get("images", []):
        slots.append(
            {
                "id": f"image.{image['id']}",
                "selector": image["selector"],
                "type": "image",
                "width": int(image.get("width", 1280)),
                "height": int(image.get("height", 800)),
            }
        )
    log.info("slots_extracted", count=len(slots))
    return slots


def _emit_hero(section: dict[str, Any], slots: list[dict[str, Any]]) -> None:
    base = section.get("selector_root", ".hero")
    slots.append(
        {
            "id": "hero.badge",
            "selector": f"{base} .badge",
            "type": "text",
            "max_chars": MAX_CHARS["BADGE"],
        }
    )
    headline_slot: dict[str, Any] = {
        "id": "hero.headline",
        "selector": f"{base} h1",
        "type": "text",
        "max_chars": MAX_CHARS["HERO_HEADLINE"],
    }
    if section.get("headline_structure"):
        headline_slot["structure"] = section["headline_structure"]
    slots.append(headline_slot)
    slots.append(
        {
            "id": "hero.subhead",
            "selector": f"{base} p.subhead",
            "type": "text",
            "max_chars": MAX_CHARS["HERO_SUBHEAD"],
        }
    )
    for index, cta in enumerate(section.get("ctas", [])[: len(_CTA_NAMES)]):
        slots.append(
            {
                "id": f"hero.cta.{_CTA_NAMES[index]}",
                "selector": cta["selector"],
                "type": "text",
                "max_chars": MAX_CHARS["CTA"],
            }
        )


def _emit_features(section: dict[str, Any], slots: list[dict[str, Any]]) -> None:
    for index, feature in enumerate(section.get("items", []), start=1):
        slots.append(
            {
                "id": f"feature.{index}.title",
                "selector": feature["title_selector"],
                "type": "text",
                "max_chars": MAX_CHARS["FEATURE_TITLE"],
            }
        )
        slots.append(
            {
                "id": f"feature.{index}.body",
                "selector": feature["body_selector"],
                "type": "text",
                "max_chars": MAX_CHARS["FEATURE_BODY"],
            }
        )


def _emit_pricing(section: dict[str, Any], slots: list[dict[str, Any]]) -> None:
    for index, tier in enumerate(section.get("tiers", []), start=1):
        slots.append(
            {
                "id": f"pricing.tier.{index}.name",
                "selector": tier["name_selector"],
                "type": "text",
                "max_chars": MAX_CHARS["PRICING_TIER_NAME"],
            }
        )
        slots.append(
            {
                "id": f"pricing.tier.{index}.price",
                "selector": tier["price_selector"],
                "type": "text",
                "max_chars": MAX_CHARS["PRICING_PRICE"],
            }
        )
