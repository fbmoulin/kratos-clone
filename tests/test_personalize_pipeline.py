"""Tests for personalize.pipeline — Step 8 orchestrator."""

from __future__ import annotations

import io
import shutil
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from PIL import Image

from personalize.openai_client import BudgetExceededError
from personalize.pipeline import arun_pipeline, run_pipeline

FIXTURE_DIR = Path(__file__).parent / "fixtures"


def _png_bytes() -> bytes:
    img = Image.new("RGB", (16, 16), "blue")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """Layout: <tmp>/index.html + <tmp>/_inventory.json."""
    shutil.copy(FIXTURE_DIR / "sample_captured.html", tmp_path / "index.html")
    shutil.copy(FIXTURE_DIR / "sample_inventory.json", tmp_path / "_inventory.json")
    return tmp_path


def _mk_client(*, structure_ok: bool = True, personalize_ok: bool = True) -> MagicMock:
    client = MagicMock()
    client.spent_usd = 0.0
    client.remaining_usd = 1.0
    if structure_ok:
        client.structure_brief.return_value = {
            "company": "Acme",
            "tagline": "Move fast",
            "audience": "indie devs",
            "category": "developer tools",
            "tone": ["friendly", "direct"],
        }
    else:
        client.structure_brief.side_effect = RuntimeError("boom")
    if personalize_ok:
        client.personalize.return_value = {
            "palette": {
                "primary": "#3b82f6",
                "primary_hover": "#60a5fa",
                "primary_pressed": "#2563eb",
                "accent_evidence": "blue dominant",
            },
            "patches": [{"slot_id": "hero.headline", "value": "New One Two"}],
            "images": [],
        }
    else:
        client.personalize.side_effect = BudgetExceededError("cap")
    client.generate_images_parallel = AsyncMock(return_value={})
    return client


def test_happy_path_writes_personalized_html(workspace):
    client = _mk_client()
    out = run_pipeline(
        workspace,
        "We make tools for indie devs.",
        _png_bytes(),
        client=client,
    )
    assert out == workspace / "personalized.html"
    assert out.exists()
    html = out.read_text()
    assert "Acme" not in html  # no leakage of brief into output by default
    assert "New" in html  # patch applied to headline


def test_logo_validation_fails_fast(workspace):
    client = _mk_client()
    with pytest.raises(ValueError):
        run_pipeline(workspace, "brief", b"<svg/>", client=client)
    client.structure_brief.assert_not_called()


def test_step2_failure_surfaces(workspace):
    client = _mk_client(structure_ok=False)
    with pytest.raises(RuntimeError, match="boom"):
        run_pipeline(workspace, "brief", _png_bytes(), client=client)
    client.personalize.assert_not_called()


def test_budget_exceeded_mid_pipeline_surfaces(workspace):
    client = _mk_client(personalize_ok=False)
    with pytest.raises(BudgetExceededError):
        run_pipeline(workspace, "brief", _png_bytes(), client=client)


def test_inventory_loaded_from_html_dir(workspace):
    client = _mk_client()
    run_pipeline(workspace, "brief", _png_bytes(), client=client)
    # personalize was called with slots derived from _inventory.json fixture.
    args = client.personalize.call_args
    slots = args[0][2] if args[0] else args.kwargs["slots"]
    slot_ids = {s["id"] for s in slots}
    assert "hero.headline" in slot_ids
    assert "image.hero" in slot_ids


def test_missing_inventory_raises(tmp_path):
    shutil.copy(FIXTURE_DIR / "sample_captured.html", tmp_path / "index.html")
    client = _mk_client()
    with pytest.raises(FileNotFoundError):
        run_pipeline(tmp_path, "brief", _png_bytes(), client=client)


def test_dry_run_skips_api_calls(workspace):
    client = _mk_client()
    out = run_pipeline(
        workspace,
        "brief",
        _png_bytes(),
        client=client,
        dry_run=True,
    )
    assert out is None
    client.structure_brief.assert_not_called()
    client.personalize.assert_not_called()


@pytest.mark.asyncio
async def test_arun_pipeline_works_inside_event_loop(workspace):
    """arun_pipeline composes inside an existing event loop (FastAPI etc.)."""
    client = _mk_client()
    out = await arun_pipeline(
        workspace,
        "brief",
        _png_bytes(),
        client=client,
    )
    assert out is not None
    assert out.exists()


@pytest.mark.asyncio
async def test_run_pipeline_refuses_inside_event_loop(workspace):
    """Sync run_pipeline must raise a clear error when called from async ctx
    instead of dying inside ``asyncio.run`` with a confusing trace.
    Regression for Gemini medium finding from PR #7 review.
    """
    client = _mk_client()
    with pytest.raises(RuntimeError, match="running event loop"):
        run_pipeline(workspace, "brief", _png_bytes(), client=client)
