"""OpenAI integration — Steps 2, 5, 6 of the pipeline.

Centralizes:
- Sync Responses API calls for brief structuring (Step 2) and personalize (Step 5)
- Async Images API calls for parallel image generation (Step 6)
- Total spend tracking with hard budget cap

The client is dependency-injected so tests can mock without live calls.
A live integration test exists at ``tests/integration/test_personalize_live.py``
and is gated by ``RUN_OPENAI_LIVE=1``.
"""

from __future__ import annotations

import asyncio
import base64
import json
from typing import Any

import structlog
from openai import AsyncOpenAI, OpenAI

from .sanitize import sanitize_brief_text, strip_exif, verify_image_bytes

log = structlog.get_logger()

# Pricing (USD) — verified at platform.openai.com/docs/pricing 2026-04.
# These are projection-only constants used by the budget guard; actual cost is
# whatever OpenAI bills, which can vary slightly with input/output tokens.
COST_STRUCTURE_BRIEF = 0.005  # gpt-5-mini, ~150 input + ~80 output tokens
COST_PERSONALIZE = 0.10  # gpt-5-mini + image input + larger output
COST_IMAGE_MEDIUM = 0.07  # gpt-image-1 medium quality

DEFAULT_TEXT_MODEL = "gpt-5-mini"
DEFAULT_IMAGE_MODEL = "gpt-image-1"


class BudgetExceededError(RuntimeError):
    """Raised when a projected spend would push total over ``max_budget_usd``."""


_BRIEF_SCHEMA: dict[str, Any] = {
    "name": "brand_brief",
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["company", "tagline", "audience", "category", "tone"],
        "properties": {
            "company": {"type": "string", "maxLength": 60},
            "tagline": {"type": "string", "maxLength": 100},
            "audience": {"type": "string", "maxLength": 200},
            "category": {"type": "string", "maxLength": 60},
            "tone": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 2,
                "maxItems": 5,
            },
        },
    },
    "strict": True,
}


class OpenAIBrandClient:
    """Thin wrapper around the OpenAI SDK with budget tracking.

    Inject ``openai_client`` and/or ``async_openai_client`` for tests.
    """

    def __init__(
        self,
        *,
        openai_client: Any | None = None,
        async_openai_client: Any | None = None,
        max_budget_usd: float = 1.0,
        text_model: str = DEFAULT_TEXT_MODEL,
        image_model: str = DEFAULT_IMAGE_MODEL,
    ) -> None:
        self._client = openai_client if openai_client is not None else OpenAI()
        self._async_client = async_openai_client  # constructed lazily
        self._max_budget = float(max_budget_usd)
        self._spent = 0.0
        self._text_model = text_model
        self._image_model = image_model

    @property
    def spent_usd(self) -> float:
        return self._spent

    @property
    def remaining_usd(self) -> float:
        return max(0.0, self._max_budget - self._spent)

    def _check_budget(self, projected: float, *, step: str) -> None:
        if self._spent + projected > self._max_budget:
            raise BudgetExceededError(
                f"step={step} projected={projected:.4f} "
                f"spent={self._spent:.4f} cap={self._max_budget:.4f}"
            )

    def _record_spend(self, projected: float) -> None:
        self._spent += projected

    # ----- Step 2: structure_brief ----------------------------------------

    def structure_brief(self, raw_brief: str) -> dict[str, Any]:
        """Convert free-form brief text into structured fields via gpt-5-mini."""
        self._check_budget(COST_STRUCTURE_BRIEF, step="structure_brief")
        clean = sanitize_brief_text(raw_brief, max_len=2000)

        system = (
            "You convert a short company brief into structured fields. "
            "Be faithful to the brief; do not invent claims."
        )
        user_input = json.dumps({"brief": clean})

        log.info("structure_brief_call", brief_len=len(clean))
        # The openai SDK's responses.create has overloaded literal-only typing
        # for `model` and `input`. Our generic-string + dict-list usage is
        # supported at runtime but doesn't match the literal overload.
        resp = self._client.responses.create(  # type: ignore[call-overload]
            model=self._text_model,
            input=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_input},
            ],
            text={"format": {"type": "json_schema", **_BRIEF_SCHEMA}},
        )
        self._record_spend(COST_STRUCTURE_BRIEF)
        parsed: dict[str, Any] = json.loads(resp.output_text)
        return parsed

    # ----- Step 5: personalize --------------------------------------------

    def personalize(
        self,
        brief: dict[str, Any],
        logo_bytes: bytes,
        slots: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Generate copy + palette + image prompts via multimodal Responses call."""
        self._check_budget(COST_PERSONALIZE, step="personalize")
        verify_image_bytes(logo_bytes)
        clean_logo = strip_exif(logo_bytes)

        text_slots = [s for s in slots if s["type"] == "text"]
        image_slots = [s for s in slots if s["type"] == "image"]
        schema = self._build_personalize_schema(text_slots, image_slots)

        system = (
            f"You write marketing copy for {sanitize_brief_text(brief['company'], 60)}, "
            f"a {sanitize_brief_text(brief['category'], 60)} for "
            f"{sanitize_brief_text(brief['audience'], 200)}. "
            f"Voice: {', '.join(sanitize_brief_text(t, 40) for t in brief['tone'])}. "
            "Avoid superlatives ('best', '#1'), unfounded claims about security or "
            "compliance, competitor mentions, and jargon. Use active voice."
        )
        instructions = (
            "1. Extract the primary brand color from the uploaded logo. "
            "Reject black/white as primary unless the logo is monochromatic. "
            "Compute hover (lighten 10%) and pressed (darken 10%) variants. "
            "2. Generate copy for every text slot, respecting max_chars strictly. "
            "3. Generate image-gen prompts for every image slot, incorporating brand "
            "color and matching the original layout context."
        )
        user_payload = json.dumps(
            {
                "brief": {
                    k: sanitize_brief_text(str(v), 200) if isinstance(v, str) else v
                    for k, v in brief.items()
                },
                "text_slots": text_slots,
                "image_slots": image_slots,
                "instructions": instructions,
            }
        )
        logo_b64 = base64.b64encode(clean_logo).decode("ascii")

        log.info(
            "personalize_call",
            text_slots=len(text_slots),
            image_slots=len(image_slots),
            logo_bytes=len(clean_logo),
        )
        resp = self._client.responses.create(  # type: ignore[call-overload]
            model=self._text_model,
            input=[
                {"role": "system", "content": system},
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": user_payload},
                        {
                            "type": "input_image",
                            "image_url": f"data:image/png;base64,{logo_b64}",
                        },
                    ],
                },
            ],
            text={"format": {"type": "json_schema", **schema}},
        )
        self._record_spend(COST_PERSONALIZE)
        plan: dict[str, Any] = json.loads(resp.output_text)
        return plan

    @staticmethod
    def _build_personalize_schema(
        text_slots: list[dict[str, Any]], image_slots: list[dict[str, Any]]
    ) -> dict[str, Any]:
        text_ids = [s["id"] for s in text_slots]
        image_ids = [s["id"] for s in image_slots]
        return {
            "name": "site_personalization",
            "strict": True,
            "schema": {
                "type": "object",
                "additionalProperties": False,
                "required": ["palette", "patches", "images"],
                "properties": {
                    "palette": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": [
                            "primary",
                            "primary_hover",
                            "primary_pressed",
                            "accent_evidence",
                        ],
                        "properties": {
                            "primary": {
                                "type": "string",
                                "pattern": "^#[0-9a-fA-F]{6}$",
                            },
                            "primary_hover": {
                                "type": "string",
                                "pattern": "^#[0-9a-fA-F]{6}$",
                            },
                            "primary_pressed": {
                                "type": "string",
                                "pattern": "^#[0-9a-fA-F]{6}$",
                            },
                            "accent_evidence": {
                                "type": "string",
                                "maxLength": 200,
                            },
                        },
                    },
                    "patches": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["slot_id", "value"],
                            "properties": {
                                "slot_id": {
                                    "type": "string",
                                    "enum": text_ids or [""],
                                },
                                "value": {"type": "string", "maxLength": 400},
                            },
                        },
                    },
                    "images": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["slot_id", "prompt"],
                            "properties": {
                                "slot_id": {
                                    "type": "string",
                                    "enum": image_ids or [""],
                                },
                                "prompt": {"type": "string", "maxLength": 500},
                            },
                        },
                    },
                },
            },
        }

    # ----- Step 6: generate_images_parallel -------------------------------

    async def generate_images_parallel(
        self, plan: dict[str, Any], slots: list[dict[str, Any]]
    ) -> dict[str, bytes]:
        """Generate every image in ``plan['images']`` with style-reference chaining."""
        image_plans = plan.get("images", [])
        if not image_plans:
            return {}
        slot_map = {s["id"]: s for s in slots if s["type"] == "image"}
        # Project worst-case cost up front and refuse if any single call would
        # push us over the cap.
        total_projected = COST_IMAGE_MEDIUM * len(image_plans)
        self._check_budget(total_projected, step="generate_images_parallel")

        async_client = self._get_async_client()
        palette_primary = plan.get("palette", {}).get("primary", "#000000")

        # First image without style reference (sets the look).
        first = image_plans[0]
        first_slot = slot_map[first["slot_id"]]
        first_b64 = await self._gen_one(
            async_client,
            first["prompt"],
            palette_primary,
            first_slot["width"],
            first_slot["height"],
        )
        self._record_spend(COST_IMAGE_MEDIUM)
        results: dict[str, bytes] = {first["slot_id"]: base64.b64decode(first_b64)}

        rest = image_plans[1:]
        if not rest:
            return results

        tasks = [
            self._gen_one(
                async_client,
                spec["prompt"],
                palette_primary,
                slot_map[spec["slot_id"]]["width"],
                slot_map[spec["slot_id"]]["height"],
                style_reference_b64=first_b64,
            )
            for spec in rest
        ]
        b64_list = await asyncio.gather(*tasks)
        for spec, b64 in zip(rest, b64_list, strict=True):
            results[spec["slot_id"]] = base64.b64decode(b64)
            self._record_spend(COST_IMAGE_MEDIUM)
        log.info("images_generated", count=len(results))
        return results

    async def _gen_one(
        self,
        async_client: Any,
        prompt: str,
        primary_hex: str,
        width: int,
        height: int,
        *,
        style_reference_b64: str | None = None,
    ) -> str:
        full_prompt = (
            f"{prompt}. Brand color: {primary_hex}. "
            "Style: clean, modern, marketing-friendly, flat illustration. "
            "No watermarks; no text overlays beyond the brand name."
        )
        kwargs: dict[str, Any] = {
            "model": self._image_model,
            "prompt": full_prompt,
            "size": f"{width}x{height}",
            "quality": "medium",
        }
        if style_reference_b64 is not None:
            kwargs["input_images"] = [{"image": f"data:image/png;base64,{style_reference_b64}"}]
        resp = await async_client.images.generate(**kwargs)
        b64: str = resp.data[0].b64_json
        return b64

    def _get_async_client(self) -> Any:
        if self._async_client is None:
            self._async_client = AsyncOpenAI()
        return self._async_client
