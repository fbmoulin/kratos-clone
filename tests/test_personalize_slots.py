"""Tests for personalize.slots — Step 4 of the spec."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from personalize.slots import extract_slots

FIXTURE = Path(__file__).parent / "fixtures" / "sample_inventory.json"


@pytest.fixture
def inventory() -> dict:
    return json.loads(FIXTURE.read_text())


def test_returns_list_of_dicts(inventory):
    slots = extract_slots(inventory)
    assert isinstance(slots, list)
    assert slots, "expected non-empty slot list"
    for s in slots:
        assert {"id", "selector", "type"} <= set(s)


def test_hero_headline_present_with_max_chars(inventory):
    slots = extract_slots(inventory)
    headline = next(s for s in slots if s["id"] == "hero.headline")
    assert headline["type"] == "text"
    assert headline["max_chars"] == 60
    assert headline.get("structure") == "word-wrappers"


def test_hero_ctas_distinct(inventory):
    slots = extract_slots(inventory)
    cta_ids = {s["id"] for s in slots if s["id"].startswith("hero.cta.")}
    assert cta_ids == {"hero.cta.primary", "hero.cta.secondary"}


def test_feature_slots_indexed_from_one(inventory):
    slots = extract_slots(inventory)
    feature_ids = sorted(s["id"] for s in slots if s["id"].startswith("feature."))
    assert feature_ids == [
        "feature.1.body",
        "feature.1.title",
        "feature.2.body",
        "feature.2.title",
    ]


def test_pricing_slots_present(inventory):
    slots = extract_slots(inventory)
    tier_slots = [s for s in slots if s["id"].startswith("pricing.tier.")]
    assert {s["id"] for s in tier_slots} == {
        "pricing.tier.1.name",
        "pricing.tier.1.price",
    }


def test_image_slot_has_dimensions(inventory):
    slots = extract_slots(inventory)
    images = [s for s in slots if s["type"] == "image"]
    assert len(images) == 1
    assert images[0]["id"] == "image.hero"
    assert images[0]["width"] == 1280
    assert images[0]["height"] == 800


def test_unique_slot_ids(inventory):
    slots = extract_slots(inventory)
    ids = [s["id"] for s in slots]
    assert len(ids) == len(set(ids)), "slot ids must be unique"


def test_empty_inventory_returns_empty_list():
    assert extract_slots({"sections": [], "images": []}) == []


def test_unknown_section_kind_skipped():
    inv = {"sections": [{"kind": "testimonials"}], "images": []}
    assert extract_slots(inv) == []
