"""Tests for personalize.openai_client — Steps 2/5/6 of the spec.

All tests use mocked OpenAI clients; no network calls. Live E2E lives at
``tests/integration/test_personalize_live.py`` and is gated by
``RUN_OPENAI_LIVE=1``.
"""

from __future__ import annotations

import io
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from PIL import Image

from personalize.openai_client import (
    BudgetExceededError,
    OpenAIBrandClient,
)


def _png_bytes() -> bytes:
    img = Image.new("RGB", (16, 16), "blue")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _mk_response(payload: dict) -> SimpleNamespace:
    return SimpleNamespace(output_text=json.dumps(payload))


# --- structure_brief -------------------------------------------------------


class TestStructureBrief:
    def test_returns_dict(self):
        mock = MagicMock()
        mock.responses.create.return_value = _mk_response(
            {
                "company": "Acme",
                "tagline": "Move fast",
                "audience": "indie devs",
                "category": "developer tools",
                "tone": ["friendly", "direct"],
            }
        )
        client = OpenAIBrandClient(openai_client=mock)
        out = client.structure_brief("We make tools for indie devs.")
        assert out["company"] == "Acme"
        assert out["tone"] == ["friendly", "direct"]

    def test_input_is_sanitized(self):
        mock = MagicMock()
        mock.responses.create.return_value = _mk_response(
            {
                "company": "x",
                "tagline": "y",
                "audience": "z",
                "category": "w",
                "tone": ["a", "b"],
            }
        )
        client = OpenAIBrandClient(openai_client=mock)
        client.structure_brief("hello\x00\x07world")
        kwargs = mock.responses.create.call_args.kwargs
        # The sanitized brief must appear inside the input string somewhere,
        # but null bytes / control chars must NOT.
        flat = json.dumps(kwargs["input"])
        assert "\\u0000" not in flat
        assert "\\u0007" not in flat
        assert "helloworld" in flat

    def test_uses_strict_json_schema(self):
        mock = MagicMock()
        mock.responses.create.return_value = _mk_response(
            {
                "company": "x",
                "tagline": "y",
                "audience": "z",
                "category": "w",
                "tone": ["a", "b"],
            }
        )
        client = OpenAIBrandClient(openai_client=mock)
        client.structure_brief("brief")
        kwargs = mock.responses.create.call_args.kwargs
        text = kwargs["text"]
        assert text["format"]["type"] == "json_schema"
        assert text["format"]["strict"] is True
        assert text["format"]["name"] == "brand_brief"

    def test_budget_guard_blocks_when_exhausted(self):
        mock = MagicMock()
        client = OpenAIBrandClient(openai_client=mock, max_budget_usd=0.001)
        with pytest.raises(BudgetExceededError):
            client.structure_brief("brief")
        mock.responses.create.assert_not_called()

    def test_spent_is_tracked(self):
        mock = MagicMock()
        mock.responses.create.return_value = _mk_response(
            {
                "company": "x",
                "tagline": "y",
                "audience": "z",
                "category": "w",
                "tone": ["a", "b"],
            }
        )
        client = OpenAIBrandClient(openai_client=mock)
        before = client.spent_usd
        client.structure_brief("brief")
        assert client.spent_usd > before


# --- personalize -----------------------------------------------------------


_BASIC_SLOTS = [
    {"id": "hero.headline", "selector": "h1", "type": "text", "max_chars": 60},
    {
        "id": "image.hero",
        "selector": "img",
        "type": "image",
        "width": 1280,
        "height": 800,
    },
]


class TestPersonalize:
    def test_returns_plan(self):
        mock = MagicMock()
        mock.responses.create.return_value = _mk_response(
            {
                "palette": {
                    "primary": "#3b82f6",
                    "primary_hover": "#60a5fa",
                    "primary_pressed": "#2563eb",
                    "accent_evidence": "blue dominant",
                },
                "patches": [{"slot_id": "hero.headline", "value": "New headline"}],
                "images": [{"slot_id": "image.hero", "prompt": "abstract"}],
            }
        )
        client = OpenAIBrandClient(openai_client=mock)
        out = client.personalize(
            {
                "company": "Acme",
                "tagline": "x",
                "audience": "y",
                "category": "z",
                "tone": ["a"],
            },
            _png_bytes(),
            _BASIC_SLOTS,
        )
        assert out["palette"]["primary"] == "#3b82f6"
        assert out["patches"][0]["slot_id"] == "hero.headline"

    def test_schema_uses_closed_enum_of_slot_ids(self):
        mock = MagicMock()
        mock.responses.create.return_value = _mk_response(
            {
                "palette": {
                    "primary": "#000000",
                    "primary_hover": "#111111",
                    "primary_pressed": "#222222",
                    "accent_evidence": "x",
                },
                "patches": [],
                "images": [],
            }
        )
        client = OpenAIBrandClient(openai_client=mock)
        client.personalize(
            {
                "company": "Acme",
                "tagline": "x",
                "audience": "y",
                "category": "z",
                "tone": ["a"],
            },
            _png_bytes(),
            _BASIC_SLOTS,
        )
        kwargs = mock.responses.create.call_args.kwargs
        schema = kwargs["text"]["format"]["schema"]
        text_enum = schema["properties"]["patches"]["items"]["properties"]["slot_id"]["enum"]
        image_enum = schema["properties"]["images"]["items"]["properties"]["slot_id"]["enum"]
        assert text_enum == ["hero.headline"]
        assert image_enum == ["image.hero"]

    def test_logo_must_be_png_or_jpeg(self):
        client = OpenAIBrandClient(openai_client=MagicMock())
        with pytest.raises(ValueError):
            client.personalize(
                {
                    "company": "Acme",
                    "tagline": "x",
                    "audience": "y",
                    "category": "z",
                    "tone": ["a"],
                },
                b"<svg/>",
                _BASIC_SLOTS,
            )

    def test_budget_guard_blocks_when_exhausted(self):
        mock = MagicMock()
        client = OpenAIBrandClient(openai_client=mock, max_budget_usd=0.001)
        with pytest.raises(BudgetExceededError):
            client.personalize(
                {
                    "company": "x",
                    "tagline": "x",
                    "audience": "x",
                    "category": "x",
                    "tone": ["a"],
                },
                _png_bytes(),
                _BASIC_SLOTS,
            )
        mock.responses.create.assert_not_called()


# --- generate_images_parallel ---------------------------------------------


class TestGenerateImages:
    @pytest.mark.asyncio
    async def test_returns_bytes_per_slot(self):
        async_mock = MagicMock()
        async_mock.images.generate = AsyncMock(
            return_value=SimpleNamespace(data=[SimpleNamespace(b64_json="iVBORw0KGgo=")])
        )
        client = OpenAIBrandClient(openai_client=MagicMock(), async_openai_client=async_mock)
        plan = {
            "palette": {
                "primary": "#000000",
                "primary_hover": "#000000",
                "primary_pressed": "#000000",
                "accent_evidence": "x",
            },
            "patches": [],
            "images": [{"slot_id": "image.hero", "prompt": "abstract"}],
        }
        out = await client.generate_images_parallel(plan, _BASIC_SLOTS)
        assert "image.hero" in out
        assert isinstance(out["image.hero"], bytes)

    @pytest.mark.asyncio
    async def test_first_image_no_reference_rest_with_reference(self):
        async_mock = MagicMock()
        async_mock.images.generate = AsyncMock(
            return_value=SimpleNamespace(data=[SimpleNamespace(b64_json="iVBORw0KGgo=")])
        )
        slots = _BASIC_SLOTS + [
            {
                "id": "image.feature.1",
                "selector": "img.f1",
                "type": "image",
                "width": 800,
                "height": 500,
            }
        ]
        client = OpenAIBrandClient(openai_client=MagicMock(), async_openai_client=async_mock)
        plan = {
            "palette": {
                "primary": "#000000",
                "primary_hover": "#000000",
                "primary_pressed": "#000000",
                "accent_evidence": "x",
            },
            "patches": [],
            "images": [
                {"slot_id": "image.hero", "prompt": "first"},
                {"slot_id": "image.feature.1", "prompt": "second"},
            ],
        }
        await client.generate_images_parallel(plan, slots)
        calls = async_mock.images.generate.await_args_list
        assert len(calls) == 2
        # First call: no input_images
        assert "input_images" not in calls[0].kwargs
        # Second call: input_images present (style ref)
        assert "input_images" in calls[1].kwargs

    @pytest.mark.asyncio
    async def test_budget_guard_stops_before_overspend(self):
        async_mock = MagicMock()
        async_mock.images.generate = AsyncMock(
            return_value=SimpleNamespace(data=[SimpleNamespace(b64_json="iVBORw0KGgo=")])
        )
        client = OpenAIBrandClient(
            openai_client=MagicMock(),
            async_openai_client=async_mock,
            max_budget_usd=0.05,
        )
        plan = {
            "palette": {
                "primary": "#000000",
                "primary_hover": "#000000",
                "primary_pressed": "#000000",
                "accent_evidence": "x",
            },
            "patches": [],
            "images": [{"slot_id": "image.hero", "prompt": "x"}],
        }
        with pytest.raises(BudgetExceededError):
            await client.generate_images_parallel(plan, _BASIC_SLOTS)
        async_mock.images.generate.assert_not_called()
