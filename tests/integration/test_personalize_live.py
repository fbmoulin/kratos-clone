"""Live OpenAI smoke test — gated by RUN_OPENAI_LIVE=1.

Never runs in CI. Use locally to validate the OpenAI integration end-to-end.

To run:
    RUN_OPENAI_LIVE=1 uv run pytest tests/integration -v -s

Cost cap: $0.50 hard cap on the client; structure_brief alone is ~$0.005.
"""

from __future__ import annotations

import io
import os

import pytest
from dotenv import load_dotenv
from PIL import Image

from personalize.openai_client import OpenAIBrandClient

load_dotenv()

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_OPENAI_LIVE") != "1",
    reason="live OpenAI calls; set RUN_OPENAI_LIVE=1 to enable",
)


def test_structure_brief_live():
    """Smallest possible live call: ~$0.005, 2-3 s.

    Asserts the client.responses.create + brand_brief schema work against
    the real API. If the model id is wrong this fails with a clear error
    that names the missing model.
    """
    assert os.getenv("OPENAI_API_KEY", "").startswith("sk-"), (
        "OPENAI_API_KEY not loaded — check .env"
    )
    client = OpenAIBrandClient(max_budget_usd=0.50)
    out = client.structure_brief(
        "We make collaboration tools for indie developer teams of 2-10 people. "
        "Voice: direct, friendly, no fluff."
    )
    assert isinstance(out, dict)
    assert {"company", "tagline", "audience", "category", "tone"} <= out.keys()
    assert isinstance(out["tone"], list) and len(out["tone"]) >= 2
    assert client.spent_usd <= 0.50


def test_personalize_live_with_vision_no_image_gen():
    """Run structure_brief + personalize end-to-end with a real logo.

    Skips ``generate_images_parallel`` (each gpt-image-1 call is $0.07) so the
    total is ~$0.105 = $0.005 (brief) + $0.10 (personalize w/ vision).
    Asserts the closed-enum schema is honored — every patch.slot_id and
    image.slot_id must come from the slot list we passed in.
    """
    img = Image.new("RGB", (256, 256), "#3b82f6")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    logo = buf.getvalue()

    slots = [
        {"id": "hero.headline", "selector": "h1", "type": "text", "max_chars": 60},
        {"id": "hero.subhead", "selector": "p.subhead", "type": "text", "max_chars": 200},
        {"id": "hero.cta.primary", "selector": "button.primary", "type": "text", "max_chars": 24},
        {
            "id": "image.hero",
            "selector": "img.hero",
            "type": "image",
            "width": 1280,
            "height": 800,
        },
    ]
    client = OpenAIBrandClient(max_budget_usd=0.50)
    structured = client.structure_brief(
        "Collaboration tools for indie developer teams. Voice: direct, friendly."
    )
    plan = client.personalize(structured, logo, slots)

    text_ids = {"hero.headline", "hero.subhead", "hero.cta.primary"}
    image_ids = {"image.hero"}
    for patch in plan["patches"]:
        assert patch["slot_id"] in text_ids, f"hallucinated patch slot: {patch}"
    for image_spec in plan["images"]:
        assert image_spec["slot_id"] in image_ids
    palette = plan["palette"]
    for key in ("primary", "primary_hover", "primary_pressed"):
        assert palette[key].startswith("#") and len(palette[key]) == 7
    assert client.spent_usd <= 0.50
    print(f"\nspent: ${client.spent_usd:.4f}; remaining: ${client.remaining_usd:.4f}")
