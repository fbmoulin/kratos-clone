"""End-to-end orchestrator for the personalization pipeline.

Steps (mapped to ``docs/PERSONALIZATION.md``):

1. **(skipped here, lives in UI)** intake textarea + logo upload
2. ``OpenAIBrandClient.structure_brief`` — turn free-form brief into fields
3. **(skipped here, lives in UI)** user confirms/edits the structured brief
4. ``personalize.slots.extract_slots`` — deterministic slot list from inventory
5. ``OpenAIBrandClient.personalize`` — multimodal copy + palette + image prompts
6. ``OpenAIBrandClient.generate_images_parallel`` — async gpt-image-1 calls
7. ``personalize.patcher.apply_personalization`` — write personalized.html
8. (caller) zip / serve / preview

The orchestrator's job is to fail fast on bad input (logo, inventory) and
to surface the first failure with an unambiguous step name in the log.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import structlog

from .openai_client import OpenAIBrandClient
from .patcher import apply_personalization
from .sanitize import strip_exif, verify_image_bytes
from .slots import extract_slots

log = structlog.get_logger()

INVENTORY_FILENAME = "_inventory.json"
SOURCE_HTML_FILENAME = "index.html"
OUTPUT_HTML_FILENAME = "personalized.html"


async def arun_pipeline(
    html_dir: Path,
    raw_brief: str,
    logo_bytes: bytes,
    *,
    client: OpenAIBrandClient | None = None,
    dry_run: bool = False,
    structured_brief_override: dict[str, Any] | None = None,
) -> Path | None:
    """Async pipeline core. Use this from FastAPI / Starlette / any async caller.

    Identical contract to ``run_pipeline`` but never calls ``asyncio.run``,
    so it composes cleanly inside an existing event loop.
    """
    html_dir = Path(html_dir)
    src_html = html_dir / SOURCE_HTML_FILENAME
    inventory_path = html_dir / INVENTORY_FILENAME
    if not src_html.exists():
        raise FileNotFoundError(src_html)
    if not inventory_path.exists():
        raise FileNotFoundError(inventory_path)

    # Step 0a — validate logo before doing anything paid.
    verify_image_bytes(logo_bytes)
    clean_logo = strip_exif(logo_bytes)

    # Step 4 — extract slots (no LLM).
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    slots = extract_slots(inventory)

    if dry_run:
        text_count = sum(1 for s in slots if s["type"] == "text")
        image_count = sum(1 for s in slots if s["type"] == "image")
        log.info(
            "dry_run_summary",
            text_slots=text_count,
            image_slots=image_count,
            html_dir=str(html_dir),
            brief_chars=len(raw_brief),
            logo_bytes=len(clean_logo),
        )
        return None

    if client is None:
        client = OpenAIBrandClient()

    # Step 2 — structure the brief.
    if structured_brief_override is not None:
        structured = structured_brief_override
        log.info("structure_brief_skipped", reason="override_provided")
    else:
        try:
            structured = client.structure_brief(raw_brief)
        except Exception as exc:
            log.error("step_failed", step="structure_brief", error=str(exc))
            raise

    # Step 5 — personalize call (LLM with vision).
    try:
        plan = client.personalize(structured, clean_logo, slots)
    except Exception as exc:
        log.error("step_failed", step="personalize", error=str(exc))
        raise

    # Step 6 — async image generation (already async; just await).
    try:
        images = await client.generate_images_parallel(plan, slots)
    except Exception as exc:
        log.error("step_failed", step="generate_images", error=str(exc))
        raise

    # Step 7 — apply patches.
    out_path = html_dir / OUTPUT_HTML_FILENAME
    apply_personalization(src_html, plan, images, slots, out_path)

    log.info(
        "pipeline_complete",
        out_path=str(out_path),
        spent_usd=client.spent_usd,
        remaining_usd=client.remaining_usd,
    )
    return out_path


def run_pipeline(
    html_dir: Path,
    raw_brief: str,
    logo_bytes: bytes,
    *,
    client: OpenAIBrandClient | None = None,
    dry_run: bool = False,
    structured_brief_override: dict[str, Any] | None = None,
) -> Path | None:
    """Sync wrapper around :func:`arun_pipeline`.

    Use this from synchronous Flask routes / CLI / anywhere there is no
    running event loop. If called from inside one (e.g. an async test runner
    or a FastAPI handler) it raises a clear error pointing at the async
    variant — closes Gemini's medium finding from PR #7 review.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        # No running loop — safe to use asyncio.run.
        pass
    else:
        raise RuntimeError(
            "run_pipeline called from inside a running event loop; "
            "use `await arun_pipeline(...)` instead."
        )
    return asyncio.run(
        arun_pipeline(
            html_dir,
            raw_brief,
            logo_bytes,
            client=client,
            dry_run=dry_run,
            structured_brief_override=structured_brief_override,
        )
    )
