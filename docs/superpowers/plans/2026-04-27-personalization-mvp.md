# Personalization MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement Phase 4 of the kratos-clone roadmap — first real OpenAI integration that takes a captured site + design system + user brand brief and produces a personalized HTML the user can deploy.

**Architecture:** Patch-based pipeline (LLM emits a closed-enum JSON patch list, deterministic Python applies patches to the captured HTML). Two LLM calls (brief structuring + personalize-with-vision), parallel image generation via `gpt-image-1`, BeautifulSoup-based HTML mutation. Every architectural decision and security control is fixed by the existing spec at `docs/PERSONALIZATION.md` (read it first) and audit finding `P2-11`.

**Tech Stack:** Python 3.12, `openai` SDK 2.x (Responses API + AsyncOpenAI for parallel image generation), `beautifulsoup4` + `lxml` (already deps), `Pillow` (logo EXIF strip + magic-byte verify), `python-dotenv` (load `OPENAI_API_KEY` from gitignored `.env`), Flask routes/templates already in repo. Tests with `pytest` + `unittest.mock` for OpenAI client (no real API calls in CI; live smoke is opt-in via `RUN_OPENAI_LIVE=1` env gate).

---

## File Structure

### New files (all under `personalize/` package — sibling of `kratos_clone/`)
- `personalize/__init__.py` — exports `extract_slots`, `apply_personalization`, `OpenAIBrandClient`, `run_pipeline`
- `personalize/slots.py` — Step 4 deterministic slot extractor over `_inventory.json` (~120 lines)
- `personalize/sanitize.py` — security helpers (`sanitize_brief_text`, `strip_dangerous_html`, `verify_image_bytes`, `strip_exif`) — addresses audit P2-11 (~80 lines)
- `personalize/openai_client.py` — thin wrapper around Responses + Images API (`structure_brief`, `personalize`, `generate_images_parallel`) (~180 lines)
- `personalize/patcher.py` — Step 7 BS4 + regex patch applier (~150 lines)
- `personalize/pipeline.py` — orchestrates Steps 2–8 end-to-end with budget cap and structured logging (~120 lines)
- `personalize/cli.py` — `python -m personalize <html_dir> --brief <file> --logo <file>` (~60 lines)
- `templates/personalize.html` — Step 1+3 hybrid intake form (textarea + logo + extracted-fields edit) (~200 lines)

### Modified files
- `pyproject.toml` — add `openai>=2.0`, `Pillow>=11`, `python-dotenv>=1.0` to `dependencies`
- `app.py` — add 3 routes: `POST /api/personalize/structure` (Step 2), `POST /api/personalize/run` (Steps 4–8), `GET /personalize` (renders form). Reuse Flask-Limiter, content-type guards, `MAX_CONTENT_LENGTH` (already 1 MiB).
- `tests/conftest.py` — add `mock_openai_client` fixture (no live calls)
- `docs/AUDIT.md` — mark P2-11 RESOLVED with this PR's commit SHA
- `TODO.md` — check off Phase 4 row
- `ROADMAP.md` — mark Phase 4 status

### Test files
- `tests/test_personalize_slots.py` — 8+ cases (well-formed inventory → expected slots; missing keys; unicode; empty image set; large inventory)
- `tests/test_personalize_sanitize.py` — 12+ cases (SVG rejected; PNG/JPEG accepted; EXIF stripped; null-byte rejected; control char rejected; `<script>` and `on*=` removed; `javascript:` href stripped; brief size cap)
- `tests/test_personalize_patcher.py` — 6+ cases (text patch applied; word-wrapper structure; palette regex swap; image src updated; missing selector skipped silently; unicode preserved)
- `tests/test_personalize_openai_client.py` — 5+ cases with mocked `OpenAI` (structure_brief returns dict; personalize returns shape; image generate returns bytes; budget cap raises before call when projected > $1; retries on transient 429)
- `tests/test_personalize_pipeline.py` — 4+ cases with mocked client (full happy path; mock failure on Step 5 surfaces error; budget cap stops Step 6; logo magic-byte rejection halts pipeline)
- `tests/test_personalize_app.py` — 4+ cases for Flask routes (POST happy path; oversized payload 413; missing content-type 415; rate limit honored)

### Live smoke (opt-in, NOT in CI)
- `tests/integration/test_personalize_live.py` — gated by `RUN_OPENAI_LIVE=1`; uses an embedded fixture brief + tiny PNG logo + 1-section HTML; asserts `personalized.html` exists and palette regex applied. Capped at $0.10 via budget guard (Step 5 only, no images).

---

## Pre-flight (one-time, before any task)

- [ ] Verify `OPENAI_API_KEY` is loadable

```bash
cd /home/fbmoulin/Website-Downloader
python -c "from dotenv import load_dotenv; load_dotenv(); import os; assert os.getenv('OPENAI_API_KEY','').startswith('sk-'), 'key not loaded'; print('OK')"
```

Expected: `OK`

If FAIL: confirm `.env` exists with `OPENAI_API_KEY=sk-...` line and is `chmod 600`.

- [ ] Branch off main

```bash
git checkout -b feat/personalize-mvp
```

---

### Task 1: Add dependencies and `personalize/` package skeleton

**Files:**
- Modify: `pyproject.toml`
- Create: `personalize/__init__.py`
- Create: `tests/test_personalize_smoke.py`

- [ ] **Step 1: Write the failing import smoke test**

```python
# tests/test_personalize_smoke.py
def test_package_importable():
    import personalize
    assert hasattr(personalize, "__version__")
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_personalize_smoke.py -v
```

Expected: FAIL `ModuleNotFoundError: No module named 'personalize'`

- [ ] **Step 3: Add dependencies**

```bash
uv add 'openai>=2.0' 'Pillow>=11' 'python-dotenv>=1.0'
```

- [ ] **Step 4: Create package skeleton**

```python
# personalize/__init__.py
"""Personalization pipeline (Phase 4) — see docs/PERSONALIZATION.md."""
__version__ = "0.1.0"
```

- [ ] **Step 5: Run test to verify it passes**

```bash
uv run pytest tests/test_personalize_smoke.py -v
```

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock personalize/__init__.py tests/test_personalize_smoke.py
git commit -m "feat(personalize): scaffold package + deps (openai/Pillow/python-dotenv)"
```

---

### Task 2: Slot extractor (Step 4 of spec)

**Files:**
- Create: `personalize/slots.py`
- Create: `tests/test_personalize_slots.py`
- Create: `tests/fixtures/sample_inventory.json` (minimal but realistic; 1 hero + 2 features + 1 pricing tier + 1 hero image)

The function `extract_slots(inventory: dict) -> list[dict]` reads the existing `_inventory.json` schema and emits the `slots[]` array shaped exactly as the spec's Step 4 example. Selectors come from existing `find_button_by_classes` semantic lookup style (see `scripts/inventory.py` for reference); `max_chars` comes from a category lookup table (`HERO_HEADLINE=60`, `BADGE=30`, `SUBHEAD=200`, `CTA=24`, `FEATURE_TITLE=30`, `FEATURE_BODY=140`, `PRICING_TIER_NAME=20`, `PRICING_PRICE=12`).

- [ ] **Step 1: Write the first failing test**

```python
# tests/test_personalize_slots.py
import json
from pathlib import Path
import pytest
from personalize.slots import extract_slots

FIXTURE = Path(__file__).parent / "fixtures" / "sample_inventory.json"

@pytest.fixture
def inventory():
    return json.loads(FIXTURE.read_text())

def test_returns_list(inventory):
    slots = extract_slots(inventory)
    assert isinstance(slots, list)
    assert all("id" in s and "selector" in s and "type" in s for s in slots)

def test_hero_headline_present(inventory):
    slots = extract_slots(inventory)
    headline = next(s for s in slots if s["id"] == "hero.headline")
    assert headline["max_chars"] == 60
    assert headline["type"] == "text"

def test_image_slots_have_dimensions(inventory):
    slots = extract_slots(inventory)
    images = [s for s in slots if s["type"] == "image"]
    assert images, "expected at least one image slot"
    for img in images:
        assert img["width"] > 0 and img["height"] > 0

def test_unique_slot_ids(inventory):
    slots = extract_slots(inventory)
    ids = [s["id"] for s in slots]
    assert len(ids) == len(set(ids))

def test_empty_inventory_returns_empty_list():
    assert extract_slots({"sections": [], "images": []}) == []
```

- [ ] **Step 2: Build the fixture file**

```bash
mkdir -p tests/fixtures
```

Write a minimal `sample_inventory.json` with: 1 hero block (badge, headline, subhead, 2 CTAs), 2 feature blocks (title+body), 1 pricing tier (name, price), 1 hero image (1280×800).

- [ ] **Step 3: Run tests, verify they fail**

```bash
uv run pytest tests/test_personalize_slots.py -v
```

Expected: FAIL `ImportError: cannot import name 'extract_slots'`

- [ ] **Step 4: Implement `extract_slots`**

```python
# personalize/slots.py
"""Step 4 — deterministic slot extractor.

Maps the design-system inventory (output of scripts/inventory.py) to a
flat list of personalizable slots. Each slot has a stable id, CSS selector,
type (text|image), and optional max_chars / dimensions.
"""
from __future__ import annotations
import structlog

log = structlog.get_logger()

MAX_CHARS = {
    "BADGE": 30, "HERO_HEADLINE": 60, "HERO_SUBHEAD": 200,
    "CTA": 24, "FEATURE_TITLE": 30, "FEATURE_BODY": 140,
    "PRICING_TIER_NAME": 20, "PRICING_PRICE": 12,
}

def extract_slots(inventory: dict) -> list[dict]:
    slots: list[dict] = []
    sections = inventory.get("sections", [])
    for sec in sections:
        kind = sec.get("kind")
        if kind == "hero":
            _emit_hero(sec, slots)
        elif kind == "features":
            _emit_features(sec, slots)
        elif kind == "pricing":
            _emit_pricing(sec, slots)
    for img in inventory.get("images", []):
        slots.append({
            "id": f"image.{img['id']}",
            "selector": img["selector"],
            "type": "image",
            "width": int(img.get("width", 1280)),
            "height": int(img.get("height", 800)),
        })
    log.info("slots_extracted", count=len(slots))
    return slots

def _emit_hero(sec: dict, slots: list[dict]) -> None:
    base = sec.get("selector_root", ".hero")
    slots.append({"id": "hero.badge", "selector": f"{base} .badge",
                  "type": "text", "max_chars": MAX_CHARS["BADGE"]})
    slots.append({"id": "hero.headline", "selector": f"{base} h1",
                  "type": "text", "max_chars": MAX_CHARS["HERO_HEADLINE"],
                  "structure": sec.get("headline_structure")})
    slots.append({"id": "hero.subhead", "selector": f"{base} p.subhead",
                  "type": "text", "max_chars": MAX_CHARS["HERO_SUBHEAD"]})
    for i, cta in enumerate(sec.get("ctas", [])[:2]):
        slots.append({"id": f"hero.cta.{['primary','secondary'][i]}",
                      "selector": cta["selector"],
                      "type": "text", "max_chars": MAX_CHARS["CTA"]})

def _emit_features(sec: dict, slots: list[dict]) -> None:
    for i, feat in enumerate(sec.get("items", []), start=1):
        slots.append({"id": f"feature.{i}.title", "selector": feat["title_selector"],
                      "type": "text", "max_chars": MAX_CHARS["FEATURE_TITLE"]})
        slots.append({"id": f"feature.{i}.body", "selector": feat["body_selector"],
                      "type": "text", "max_chars": MAX_CHARS["FEATURE_BODY"]})

def _emit_pricing(sec: dict, slots: list[dict]) -> None:
    for i, tier in enumerate(sec.get("tiers", []), start=1):
        slots.append({"id": f"pricing.tier.{i}.name", "selector": tier["name_selector"],
                      "type": "text", "max_chars": MAX_CHARS["PRICING_TIER_NAME"]})
        slots.append({"id": f"pricing.tier.{i}.price", "selector": tier["price_selector"],
                      "type": "text", "max_chars": MAX_CHARS["PRICING_PRICE"]})
```

- [ ] **Step 5: Run tests, verify they pass**

```bash
uv run pytest tests/test_personalize_slots.py -v
```

Expected: 5 PASS

- [ ] **Step 6: Lint + commit**

```bash
uv run ruff check personalize/ tests/test_personalize_slots.py
uv run ruff format personalize/ tests/test_personalize_slots.py
git add personalize/slots.py tests/test_personalize_slots.py tests/fixtures/sample_inventory.json
git commit -m "feat(personalize): slot extractor with structured logging (Step 4)"
```

---

### Task 3: Sanitization utilities (P2-11)

**Files:**
- Create: `personalize/sanitize.py`
- Create: `tests/test_personalize_sanitize.py`

This module addresses every audit finding under P2-11 and the spec's "Security must-have" list. Functions:

- `sanitize_brief_text(s: str, max_len: int = 2000) -> str` — strips control chars, null bytes, HTML, enforces length, returns clean string for f-string-free interpolation into prompts.
- `verify_image_bytes(b: bytes) -> str` — checks magic bytes; returns `"png"` or `"jpeg"`; raises `ValueError` for SVG, GIF, anything else.
- `strip_exif(b: bytes) -> bytes` — opens with Pillow, re-saves without EXIF.
- `strip_dangerous_html(html: str) -> str` — uses BeautifulSoup to remove `<script>`, `<style>` (defense-in-depth), strip `on*=` event handlers, neutralize `javascript:` URLs in `href`/`src`. Used on any HTML string the LLM might contribute.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_personalize_sanitize.py
import pytest
from personalize.sanitize import (
    sanitize_brief_text, verify_image_bytes, strip_exif, strip_dangerous_html,
)

PNG_MAGIC = b"\x89PNG\r\n\x1a\n" + b"\x00" * 10
JPEG_MAGIC = b"\xff\xd8\xff" + b"\x00" * 10
SVG_BYTES = b"<svg xmlns='http://www.w3.org/2000/svg'></svg>"
GIF_MAGIC = b"GIF89a" + b"\x00" * 10

class TestSanitizeBrief:
    def test_strips_null_bytes(self):
        assert "\x00" not in sanitize_brief_text("hello\x00world")
    def test_strips_control_chars(self):
        assert "\x07" not in sanitize_brief_text("hello\x07world")
    def test_preserves_unicode(self):
        s = "Olá, mundo — café 🇧🇷"
        assert sanitize_brief_text(s) == s
    def test_truncates_to_max_len(self):
        assert len(sanitize_brief_text("x" * 5000, max_len=100)) == 100
    def test_empty_string_ok(self):
        assert sanitize_brief_text("") == ""

class TestVerifyImage:
    def test_png_accepted(self):
        assert verify_image_bytes(PNG_MAGIC) == "png"
    def test_jpeg_accepted(self):
        assert verify_image_bytes(JPEG_MAGIC) == "jpeg"
    def test_svg_rejected(self):
        with pytest.raises(ValueError, match="svg"):
            verify_image_bytes(SVG_BYTES)
    def test_gif_rejected(self):
        with pytest.raises(ValueError):
            verify_image_bytes(GIF_MAGIC)
    def test_empty_rejected(self):
        with pytest.raises(ValueError):
            verify_image_bytes(b"")

class TestStripDangerousHTML:
    def test_removes_script(self):
        out = strip_dangerous_html("<p>ok</p><script>alert(1)</script>")
        assert "<script" not in out and "alert" not in out
    def test_removes_event_handlers(self):
        out = strip_dangerous_html('<button onclick="bad()">x</button>')
        assert "onclick" not in out
    def test_neutralizes_javascript_href(self):
        out = strip_dangerous_html('<a href="javascript:alert(1)">x</a>')
        assert "javascript:" not in out
    def test_preserves_safe_content(self):
        out = strip_dangerous_html('<p class="x">ok <a href="https://e.com">e</a></p>')
        assert "ok" in out and "e.com" in out
```

(EXIF strip test uses a real Pillow-generated PNG with EXIF — write helper in test.)

- [ ] **Step 2: Run tests, verify they fail**

```bash
uv run pytest tests/test_personalize_sanitize.py -v
```

Expected: ImportError

- [ ] **Step 3: Implement `personalize/sanitize.py`**

```python
"""Security helpers — addresses audit P2-11 (LLM input/output hardening)."""
from __future__ import annotations
import io
import re
from bs4 import BeautifulSoup
from PIL import Image

_CTRL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

def sanitize_brief_text(s: str, max_len: int = 2000) -> str:
    if not isinstance(s, str):
        raise TypeError("brief text must be str")
    s = _CTRL_CHARS.sub("", s)
    return s[:max_len]

PNG = b"\x89PNG\r\n\x1a\n"
JPEG = b"\xff\xd8\xff"

def verify_image_bytes(b: bytes) -> str:
    if not b:
        raise ValueError("empty image bytes")
    if b.startswith(PNG):
        return "png"
    if b.startswith(JPEG):
        return "jpeg"
    raise ValueError(f"unsupported image type (svg/other rejected): leading={b[:8]!r}")

def strip_exif(b: bytes) -> bytes:
    img = Image.open(io.BytesIO(b))
    data = list(img.getdata())
    clean = Image.new(img.mode, img.size)
    clean.putdata(data)
    out = io.BytesIO()
    fmt = "PNG" if b.startswith(PNG) else "JPEG"
    clean.save(out, format=fmt)
    return out.getvalue()

_DANGEROUS_TAGS = ("script", "style", "iframe", "object", "embed")

def strip_dangerous_html(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup.find_all(_DANGEROUS_TAGS):
        tag.decompose()
    for tag in soup.find_all(True):
        for attr in list(tag.attrs):
            if attr.lower().startswith("on"):
                del tag.attrs[attr]
        for url_attr in ("href", "src", "action", "formaction"):
            v = tag.attrs.get(url_attr, "")
            if isinstance(v, str) and v.strip().lower().startswith("javascript:"):
                tag.attrs[url_attr] = "#"
    return str(soup)
```

- [ ] **Step 4: Run tests, verify they pass**

```bash
uv run pytest tests/test_personalize_sanitize.py -v
```

Expected: 14 PASS

- [ ] **Step 5: Lint + commit**

```bash
uv run ruff check personalize/ tests/test_personalize_sanitize.py
git add personalize/sanitize.py tests/test_personalize_sanitize.py
git commit -m "feat(personalize): sanitization (LLM input + output + image bytes) — closes P2-11"
```

---

### Task 4: BS4 patcher (Step 7 of spec)

**Files:**
- Create: `personalize/patcher.py`
- Create: `tests/test_personalize_patcher.py`
- Create: `tests/fixtures/sample_captured.html` (~30 lines: hero with `h1.text-5xl`, badge span, subhead p, 2 CTAs, palette using `from-orange-500` / `bg-orange-500`)

`apply_personalization(html_path: Path, plan: dict, images: dict[str, bytes], slots: list[dict], out_path: Path) -> None` does:

1. Parse HTML with `BeautifulSoup(..., "lxml")`.
2. For each `patch` in `plan["patches"]`: select target by slot's `selector`, set `.string` to value (or word-wrapper-aware split if `slot["structure"] == "word-wrappers"`). Skip silently if selector matches nothing.
3. Palette swap via regex on Tailwind classes (`from-orange-500` → `from-[#hex]`, etc.).
4. For each image in `images`: write bytes to `<out_path_parent>/assets/gen_<slot_id>.png`, update target `<img>` `src`.
5. Write final HTML to `out_path`.

The patcher MUST call `strip_dangerous_html` on each LLM-derived value before writing into the DOM (defense-in-depth; structured outputs already exclude HTML, but P2-11 says verify-don't-trust).

- [ ] **Step 1: Write failing tests** (text patch / word-wrapper / palette swap / image swap / missing-selector / unicode)

(Code abbreviated — follow Task 2/3 pattern.)

- [ ] **Step 2: Implement `personalize/patcher.py`** using the spec's Step 7 reference code, with these adjustments:
  - import `strip_dangerous_html` from `.sanitize` and apply to `patch["value"]` before assignment
  - use `pathlib.Path` not raw strings
  - log each step via structlog
  - write images as PNG (already PNG-bytes from gpt-image-1)

- [ ] **Step 3: Run tests, verify all pass**

- [ ] **Step 4: Commit**

```bash
git commit -m "feat(personalize): BS4 patcher with palette swap + image embed (Step 7)"
```

---

### Task 5: OpenAI client wrapper — brief structuring (Step 2)

**Files:**
- Create: `personalize/openai_client.py`
- Create: `tests/test_personalize_openai_client.py`

Class `OpenAIBrandClient`:

```python
class OpenAIBrandClient:
    def __init__(self, *, max_budget_usd: float = 1.00, openai_client=None):
        self._client = openai_client or OpenAI()  # lazy default
        self._budget = max_budget_usd
        self._spent = 0.0

    def structure_brief(self, raw_brief: str) -> dict: ...
    def personalize(self, brief: dict, logo_bytes: bytes, slots: list[dict]) -> dict: ...
    async def generate_images_parallel(self, plan: dict, slots: list[dict]) -> dict[str, bytes]: ...

    def _check_budget(self, projected_cost: float) -> None:
        if self._spent + projected_cost > self._budget:
            raise BudgetExceededError(...)
```

`structure_brief` calls Responses API with the spec's `brand_brief` schema and `gpt-5-mini`. Strict JSON. Sanitize input via `sanitize_brief_text` before passing.

Tests use `unittest.mock.MagicMock` for the OpenAI client; assert `responses.create` called with the exact schema name + model + sanitized input.

- [ ] **Step 1–4: TDD cycle for `structure_brief` only**

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(personalize): OpenAI client + structure_brief (Step 2) + budget guard"
```

---

### Task 6: OpenAI client — `personalize` (Step 5)

Adds the multimodal Responses call with `input_image` (logo b64) and the `site_personalization` strict schema. Schema construction is dynamic (closed enum from slot IDs). Cost projection: ~$0.10 fixed. Test with mocked `responses.create` returning sample personalization JSON.

- [ ] TDD cycle (5 tests minimum: happy path, budget cap, schema correctness, sanitized inputs, sanitized outputs).

- [ ] **Commit**

```bash
git commit -m "feat(personalize): personalize call with vision + closed-enum schema (Step 5)"
```

---

### Task 7: OpenAI client — async image generation (Step 6)

`async def generate_images_parallel(plan, slots) -> dict[str, bytes]`. First image with no reference (sets style), rest with first as `input_images`. Uses `AsyncOpenAI`. Each image: $0.07 medium quality. Budget check before each call. Returns `{slot_id: png_bytes}`.

- [ ] TDD with mocked `AsyncOpenAI`. Verify parallel dispatch via `asyncio.gather` mock.

- [ ] **Commit**

```bash
git commit -m "feat(personalize): parallel image gen with style reference (Step 6)"
```

---

### Task 8: Pipeline orchestrator

**Files:**
- Create: `personalize/pipeline.py`
- Create: `tests/test_personalize_pipeline.py`

`run_pipeline(html_dir: Path, brief: str, logo_bytes: bytes, *, dry_run: bool = False) -> Path`:

1. Load `_inventory.json` from `html_dir`.
2. `verify_image_bytes(logo_bytes)` + `strip_exif(logo_bytes)`.
3. `slots = extract_slots(inventory)`.
4. `client = OpenAIBrandClient(max_budget_usd=1.00)`.
5. `structured = client.structure_brief(brief)` (Step 2).
6. `plan = client.personalize(structured, logo_bytes, slots)` (Step 5).
7. `images = asyncio.run(client.generate_images_parallel(plan, slots))` (Step 6).
8. `apply_personalization(html_dir/'index.html', plan, images, slots, html_dir/'personalized.html')`.
9. Return path.

Structured logging at each step. Total budget cap honored across all calls. Each LLM/image-call wrapped in try/except logging the failure with the step name before re-raising.

- [ ] TDD with mocked `OpenAIBrandClient` (4+ tests: happy path / Step-2 fail / budget cap mid-pipeline / SVG logo rejected upfront).

- [ ] **Commit**

```bash
git commit -m "feat(personalize): pipeline orchestrator with budget cap + structured logging"
```

---

### Task 9: Flask routes

**Files:**
- Modify: `app.py` (add `/personalize` GET + `/api/personalize/structure` POST + `/api/personalize/run` POST)
- Create: `tests/test_personalize_app.py`

Route specs:
- `GET /personalize` — renders `templates/personalize.html`. No auth (matches existing UX).
- `POST /api/personalize/structure` — body `{brief: str}` (max 4 KB). Returns structured fields. Rate-limited 5/min/IP via existing `limiter`. Content-Type `application/json` enforced (existing `_require_json_content_type` helper if present, else inline check returning 415).
- `POST /api/personalize/run` — multipart: `brief` (json), `logo` (file ≤2 MB), `html_dir` (path under `downloads/`). Rate-limited 2/min/IP. Returns `{output_path: str, log: list[str]}`.

All input goes through `sanitize.*`. Errors logged via structlog. Body size cap 5 MiB on `/run` only (overrides 1 MiB).

- [ ] TDD: 6 tests minimum — happy path mock, oversized payload 413, missing content-type 415, rate limit 429, malformed JSON 400, SVG logo 400.

- [ ] **Commit**

```bash
git commit -m "feat(personalize): Flask routes (intake form + structure + run)"
```

---

### Task 10: Hybrid intake form

**Files:**
- Create: `templates/personalize.html`

Single-file Flask template (no separate JS — same rule as `index.html`). Layout:
- Step 1: textarea (placeholder "Describe your company in 2-3 sentences"), logo file input, optional brand color picker.
- "Extract" button → POSTs to `/api/personalize/structure` → renders Step 3 editable form (`company`, `tagline`, `audience`, `category`, `tone[]`).
- "Personalize" button → POSTs to `/api/personalize/run` → polls/streams progress (sse optional; for MVP, simple long-poll with disabled button + spinner).
- Output panel: link to `personalized.html` + zip download.
- Browser logger from `index.html` reused (extract to shared snippet OR inline-copy with comment).

Inline `<script>` follows existing rules: capture `_rawFetch` BEFORE wrapping fetch (PR #1 lesson).

- [ ] **Step 1: Manual smoke test** — start dev server, render `/personalize`, verify form layout in browser screenshot.

```bash
uv run python app.py &
sleep 2
curl -s http://localhost:5001/personalize | head -50
kill %1
```

- [ ] **Step 2: Commit**

```bash
git commit -m "feat(personalize): hybrid intake template (textarea + logo + editable fields)"
```

---

### Task 11: CLI entry point

**Files:**
- Create: `personalize/__main__.py`
- Create: `personalize/cli.py`

`python -m personalize <html_dir> --brief brief.txt --logo logo.png [--dry-run] [--budget 1.00]`. Loads `.env` via `python-dotenv`, calls `run_pipeline`, prints output path.

- [ ] **Step 1: Smoke test**

```bash
echo "Test brand for indie devs, casual tone" > /tmp/brief.txt
uv run python -m personalize ./capture --brief /tmp/brief.txt --logo /tmp/logo.png --dry-run
```

Expected: prints "DRY RUN: would call structure_brief, personalize, gen 3 images" — no API calls.

- [ ] **Step 2: Commit**

```bash
git commit -m "feat(personalize): CLI entry point (python -m personalize)"
```

---

### Task 12: Live smoke test (gated, runs against real OpenAI)

**Files:**
- Create: `tests/integration/__init__.py`
- Create: `tests/integration/test_personalize_live.py`
- Create: `tests/integration/fixtures/tiny.html` (1 hero, 5-line HTML)
- Create: `tests/integration/fixtures/tiny_inventory.json`
- Create: `tests/integration/fixtures/tiny_logo.png` (programmatically — solid 64×64 PNG)

```python
# tests/integration/test_personalize_live.py
import os, pytest
pytestmark = pytest.mark.skipif(
    os.getenv("RUN_OPENAI_LIVE") != "1",
    reason="live OpenAI calls; set RUN_OPENAI_LIVE=1 to enable",
)
# ... actual test calls run_pipeline(...) end-to-end with budget=$0.20 cap
```

- [ ] **Step 1: Run with key**

```bash
RUN_OPENAI_LIVE=1 uv run pytest tests/integration/test_personalize_live.py -v -s
```

Expected: passes in <60 s, ≤$0.50 spent, `personalized.html` produced. Manual visual check.

- [ ] **Step 2: Commit (test always present, gated; CI never runs it)**

```bash
git commit -m "test(personalize): live OpenAI E2E smoke (RUN_OPENAI_LIVE=1 gated)"
```

---

### Task 13: Documentation + audit closure

**Files:**
- Modify: `docs/AUDIT.md` — mark P2-11 RESOLVED with commit SHA
- Modify: `TODO.md` — check off Phase 4 + add P2-1, P2-8, P2-9, P2-10, P2-12 to next-sprint
- Modify: `ROADMAP.md` — Phase 4 status → SHIPPED
- Modify: `README.md` — add `/personalize` to "Endpoints" + `personalize/` to module table
- Modify: `CLAUDE.md` — add personalize-specific guidance section (mirror kratos_clone style)
- Modify: `docs/HANDOFF.md` — bump session date, update Phase 4 → done, add Phase 5 as next

- [ ] **Step 1: Cross-link spec + plan + handoff. Run lint + tests.**

```bash
uv run ruff check personalize/ scripts/ app.py tests/
uv run ruff format --check personalize/ scripts/ app.py tests/
uv run pytest -q
```

Expected: 100+ tests pass (74 existing + ~30 new).

- [ ] **Step 2: Push + open PR**

```bash
git push -u origin feat/personalize-mvp
gh pr create -t "feat: Phase 4 — Personalization MVP" -b "$(cat <<'EOF'
Closes Phase 4 of ROADMAP. Implements docs/PERSONALIZATION.md spec.

## Summary
- New `personalize/` package: slots, sanitize, openai_client, patcher, pipeline, cli
- 3 Flask routes + intake template
- ~30 new tests (mocked OpenAI; live E2E gated)
- Closes audit P2-11

## Test plan
- [ ] `uv run pytest -q` (~100 cases) green
- [ ] `RUN_OPENAI_LIVE=1 uv run pytest tests/integration -v` (~$0.50 spent)
- [ ] Manual UX walk-through at `/personalize`
EOF
)"
```

- [ ] **Step 3: Watch checks + merge**

```bash
gh pr checks --watch
gh pr merge --squash --delete-branch
```

- [ ] **Step 4: Final commit on main if any docs missed; tag v0.2.0 (optional, decision left to user)**

---

## Risk register & open questions

| Risk | Mitigation |
|------|------------|
| `gpt-5-mini` model name not yet GA in 2026-04 | Use the actual model id from the user's account (verify via `/v1/models` at start of Task 5). If unavailable, fall back to `gpt-4.1-mini` and document. |
| `gpt-image-1` quotas / rate limits | Budget cap + retry-with-backoff on 429. Live smoke (Task 12) flushes one cold call. |
| Captured HTML doesn't have the slots the spec assumes | Slot extractor returns empty list for that section; pipeline still produces output (just no patches for missing sections). Log warning. |
| OpenAI usage policy changes | Pipeline writes a `policy_check.txt` snapshot of current usage policy URLs at run-time for audit trail (Task 8). |
| EXIF strip changes image hash → CDN cache miss | Acceptable; logos are user-uploaded and rarely cached. |

## What is explicitly NOT in this MVP

- Streaming UI (SSE) — long-poll is fine for MVP
- User auth on `/personalize`
- Multi-language brief input (English only for first cut; PT-BR is a fast-follow once the schema is proved)
- Style reference upload (only logo for first cut)
- A/B harness for the `+70%` claim (P2-9 stays open)
- Custom font swap (palette only for color personalization)

## Reference

- Spec: `docs/PERSONALIZATION.md` (412 lines, every architectural decision)
- Audit: `docs/AUDIT.md` § P2-11
- Roadmap: `ROADMAP.md` Phase 4
- Handoff: `docs/HANDOFF.md` (current state pre-Phase-4)
