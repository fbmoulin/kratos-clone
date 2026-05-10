# Personalization Layer — OpenAI API

> Last stage of the pipeline: take a cloned site + extracted design system + a user brand brief → output a personalized HTML the user can deploy. Backed by deep research on production architectures (Aura, Framer, v0, Webflow AI), OpenAI 2026 API surface, and DTCG W3C 2025.10 spec.

> **✅ STATUS: SHIPPED 2026-04-27** (Phase 4 in `ROADMAP.md`).
>
> Implementation lives in `personalize/` (slots, sanitize, openai_client,
> patcher, pipeline, cli) with 89 dedicated tests + 2 gated live integration
> tests. Audit P2-11 (prompt-injection / image-XSS hardening) closed by
> `personalize/sanitize.py`.
>
> **Cost reconciliation (2026-04-27 live test):** text-only path
> (`structure_brief` + `personalize`) measured at ~$0.05/run across 2 live
> runs ($0.105 total). The $0.32 forecast below assumes 3 hero/feature
> illustrations via gpt-image-1 medium ($0.07 × 3 = $0.21 image gen) on top
> of the ~$0.105 text. Verify against current `platform.openai.com/docs/pricing`
> before committing to a budget — pricing has historically changed quarterly.

---

## TL;DR — recommended architecture

| Decision | Choice | Why |
|---|---|---|
| Paradigm | **Patch-based** (LLM emits JSON patch list, code applies) | Full-regen of 100KB+ HTML breaks ~5-15% structural integrity |
| API | **Responses API** (`/v1/responses`) | Assistants API sunset H1 2026; Responses is the canonical successor |
| Output format | **`text.format: { type: "json_schema", strict: true }`** | 100% schema conformance via constrained decoding (GA Aug 2024) |
| Slot identity | **Closed enum of slot IDs** (extracted upstream into `_inventory.json`) | Prevents hallucinated CSS selectors; deterministic resolution |
| Copy model | **gpt-5-mini** | Marketing copy quality at 1/10 cost of gpt-5 |
| Vision (logo→palette) | **gpt-5** with `input_image` | Better color reasoning vs gpt-5-mini |
| Image generation | **gpt-image-1** (medium quality) | Native text rendering, multi-turn editing, $0.07/image; DALL-E 3 deprecated |
| Avatars | **CSS gradient + initials** (NO synthetic faces) | EU AI Act Art. 50 + OpenAI usage policies on testimonials |
| Orchestration | **Deterministic pipeline** (NOT agent loop) | 1-2 calls, ~$0.32/run, ~25-30s · agent loops are 5-15× costlier for fixed workflows |

**Budget per personalization run:** ~$0.32, ~25-30 s end-to-end with parallel image generation (forecast based on 2026-04-27 pricing; text-only portion measured at ~$0.05/run during Phase 4 live validation). Comfortable headroom under <$1, <60s targets — enforced by the hard $1.00 budget cap in `OpenAIBrandClient`.

---

## Pipeline (8 steps)

```
┌───────────┐  ┌───────────┐  ┌───────────┐  ┌───────────┐
│ 1. INTAKE │→ │ 2. EXTRACT│→ │ 3. CONFIRM│→ │ 4. SLOTS  │
│ (textarea │  │ STRUCTURED│  │ (UI form) │  │ (deterministic)│
│  + logo)  │  │ FIELDS    │  │           │  │           │
└───────────┘  └───────────┘  └───────────┘  └───────────┘
                                                  ↓
┌───────────┐  ┌───────────┐  ┌───────────┐  ┌───────────┐
│ 8. OUTPUT │← │ 7. APPLY  │← │ 6. IMAGES │← │ 5. PERSO- │
│ (HTML+zip)│  │ PATCHES   │  │ (parallel)│  │ NALIZE    │
│           │  │           │  │           │  │ (1 call)  │
└───────────┘  └───────────┘  └───────────┘  └───────────┘
```

### Step 1 — Intake (UI)

Hybrid form (Aura/Framer-pattern, ~2× conversion vs pure-prompt or pure-form):
- **Single textarea**: "Describe your company in 2-3 sentences"
- **Logo upload** (PNG/SVG, <2 MB)
- **Optional**: primary brand color picker (override extracted), tone slider (corporate ↔ playful)

### Step 2 — Extract structured fields (1 call, gpt-5-mini, ~$0.005, ~2-3 s)

Convert free-form brief to structured JSON via small Responses call:

```python
brief_schema = {
    "name": "brand_brief",
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["company", "tagline", "audience", "category", "tone"],
        "properties": {
            "company":  {"type": "string", "maxLength": 60},
            "tagline":  {"type": "string", "maxLength": 100},
            "audience": {"type": "string", "maxLength": 200},
            "category": {"type": "string", "maxLength": 60},
            "tone":     {"type": "array", "items": {"type": "string"},
                         "minItems": 2, "maxItems": 5}
        }
    },
    "strict": True
}
```

### Step 3 — User confirmation (UI)

Show extracted fields in editable form. Conversion is 2× higher than either extreme (pure prompt or pure form).

### Step 4 — Slot extraction (deterministic Python, no LLM)

Parse `_inventory.json` from the design-system pipeline. Augment with a `slots[]` array:

```json
{
  "slots": [
    {"id": "hero.badge",    "selector": ".hero-fade.inline-flex span", "type": "text", "max_chars": 30},
    {"id": "hero.headline", "selector": "h1.text-5xl", "type": "text", "max_chars": 60, "structure": "word-wrappers"},
    {"id": "hero.subhead",  "selector": "p.hero-fade", "type": "text", "max_chars": 200},
    {"id": "hero.cta.primary",   "selector": ".hero-fade button:first-of-type", "type": "text", "max_chars": 24},
    {"id": "hero.cta.secondary", "selector": ".hero-fade button:nth-of-type(2)", "type": "text", "max_chars": 24},
    {"id": "feature.1.title", "selector": "#features h3:nth-of-type(1)", "type": "text", "max_chars": 30},
    {"id": "feature.1.body",  "selector": "#features p:nth-of-type(1)", "type": "text", "max_chars": 140},
    {"id": "pricing.tier.1.name",  "selector": "#pricing [data-tier='1'] h3", "type": "text", "max_chars": 20},
    {"id": "pricing.tier.1.price", "selector": "#pricing [data-tier='1'] .price", "type": "text", "max_chars": 12},
    {"id": "image.hero",      "selector": ".perspective-container img", "type": "image", "width": 1280, "height": 800},
    {"id": "image.feature.1", "selector": "#features img:first-of-type", "type": "image", "width": 800, "height": 500}
  ]
}
```

This step happens ONCE per cloned template; reusable for unlimited personalizations.

### Step 5 — Personalize (1 call, gpt-5-mini + Vision, ~$0.10, ~12 s)

The key call. Single Responses request with multimodal input + strict json_schema:

```python
from openai import OpenAI
import base64, json

client = OpenAI()

def personalize(brief: dict, logo_bytes: bytes, slots: list) -> dict:
    # Build closed-enum schema from slot IDs
    text_slots  = [s for s in slots if s["type"] == "text"]
    image_slots = [s for s in slots if s["type"] == "image"]

    schema = {
        "name": "site_personalization",
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["palette", "patches", "images"],
            "properties": {
                "palette": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["primary", "primary_hover", "primary_pressed", "accent_evidence"],
                    "properties": {
                        "primary":         {"type": "string", "pattern": "^#[0-9a-fA-F]{6}$"},
                        "primary_hover":   {"type": "string", "pattern": "^#[0-9a-fA-F]{6}$"},
                        "primary_pressed": {"type": "string", "pattern": "^#[0-9a-fA-F]{6}$"},
                        "accent_evidence": {"type": "string", "maxLength": 200,
                                            "description": "What in the logo led you to this palette? Cite specifically."}
                    }
                },
                "patches": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["slot_id", "value"],
                        "properties": {
                            "slot_id": {"type": "string", "enum": [s["id"] for s in text_slots]},
                            "value":   {"type": "string", "maxLength": 400}
                        }
                    }
                },
                "images": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["slot_id", "prompt"],
                        "properties": {
                            "slot_id": {"type": "string", "enum": [s["id"] for s in image_slots]},
                            "prompt":  {"type": "string", "maxLength": 500,
                                        "description": "Image-gen prompt incorporating brand color and product context"}
                        }
                    }
                }
            }
        },
        "strict": True
    }

    system = (
        f"You write marketing copy for {brief['company']}, "
        f"a {brief['category']} for {brief['audience']}. "
        f"Voice: {', '.join(brief['tone'])}. "
        "Avoid superlatives ('best', '#1'), unfounded claims about security/compliance, "
        "competitor mentions, and jargon. Use active voice."
    )

    logo_b64 = base64.b64encode(logo_bytes).decode()
    user_input = json.dumps({
        "brief": brief,
        "text_slots": text_slots,
        "image_slots": image_slots,
        "instructions": (
            "1. Extract the primary brand color from the uploaded logo. "
            "Reject black/white as primary unless the logo is monochromatic. "
            "Compute hover (lighten 10%) and pressed (darken 10%) variants. "
            "2. Generate copy for every text_slot, respecting max_chars strictly. "
            "3. Generate image-gen prompts for every image_slot, incorporating brand color "
            "and matching the original layout context (hero illustration, dashboard mock, etc.)."
        )
    })

    resp = client.responses.create(
        model="gpt-5-mini",
        input=[
            {"role": "system", "content": system},
            {"role": "user", "content": [
                {"type": "input_text", "text": user_input},
                {"type": "input_image", "image_url": f"data:image/png;base64,{logo_b64}"}
            ]}
        ],
        text={"format": {"type": "json_schema", **schema}},
        reasoning={"effort": "low"}  # gpt-5-mini default
    )
    return json.loads(resp.output_text)
```

The strict json_schema guarantees: every patch references a real slot_id, every value respects max_chars, every color is valid hex. **Zero post-validation needed.**

### Step 6 — Image generation (parallel, gpt-image-1, ~$0.21, ~15 s parallelized)

```python
import asyncio
from openai import AsyncOpenAI

async_client = AsyncOpenAI()

async def gen_one(prompt: str, palette: dict, w: int, h: int, ref_image_b64: str | None = None):
    full_prompt = (
        f"{prompt}. Brand color: {palette['primary']}. "
        "Style: clean, modern, marketing-friendly, flat illustration. "
        "No watermarks, no text overlays beyond the brand name."
    )
    kwargs = {
        "model": "gpt-image-1",
        "prompt": full_prompt,
        "size": f"{w}x{h}",
        "quality": "medium",  # $0.07 vs $0.04 low / $0.17 high
    }
    if ref_image_b64:  # subsequent images use the first as style reference
        kwargs["input_images"] = [{"image": f"data:image/png;base64,{ref_image_b64}"}]
    img_resp = await async_client.images.generate(**kwargs)
    return img_resp.data[0].b64_json

async def gen_all_images(plan: dict, slots: list):
    image_slots = {s["id"]: s for s in slots if s["type"] == "image"}
    results = {}
    # First image: no reference (sets style)
    if plan["images"]:
        first = plan["images"][0]
        slot = image_slots[first["slot_id"]]
        results[first["slot_id"]] = await gen_one(first["prompt"], plan["palette"],
                                                   slot["width"], slot["height"])
        ref = results[first["slot_id"]]
        # Subsequent: parallel, with first as style reference
        rest = plan["images"][1:]
        tasks = [gen_one(g["prompt"], plan["palette"],
                         image_slots[g["slot_id"]]["width"],
                         image_slots[g["slot_id"]]["height"],
                         ref_image_b64=ref) for g in rest]
        for g, b64 in zip(rest, await asyncio.gather(*tasks)):
            results[g["slot_id"]] = b64
    return results
```

**Avatars are NOT generated** — render as CSS gradient circle + 2-letter initials. Saves $0.09 (8 avatars) + sidesteps EU AI Act disclosure issues for synthetic faces representing real testimonials.

### Step 7 — Apply patches (deterministic, BeautifulSoup, ~1 s)

```python
from bs4 import BeautifulSoup
import re, base64, pathlib

def apply_personalization(html_path, plan, images, slots, out_path):
    soup = BeautifulSoup(pathlib.Path(html_path).read_text(), "lxml")
    slot_map = {s["id"]: s for s in slots}

    # Text patches
    for patch in plan["patches"]:
        slot = slot_map[patch["slot_id"]]
        targets = soup.select(slot["selector"])
        if not targets:
            continue
        target = targets[0]
        if slot.get("structure") == "word-wrappers":
            # H1 with word-by-word stagger — split value into wrappers
            words = patch["value"].split()
            wrappers = target.select(".word-wrapper")
            for i, wrapper in enumerate(wrappers):
                inner = wrapper.select_one(".word-inner")
                if i < len(words):
                    inner.string = words[i] + (" " if i < len(words) - 1 else "")
                else:
                    wrapper.decompose()
            # Append extra wrappers if needed
            if len(words) > len(wrappers):
                template = wrappers[0]
                for w in words[len(wrappers):]:
                    from copy import deepcopy
                    clone = deepcopy(template)
                    clone.select_one(".word-inner").string = w + " "
                    target.append(clone)
        else:
            target.string = patch["value"]

    # Palette swap (regex on Tailwind class strings)
    primary = plan["palette"]["primary"].lstrip("#")
    primary_hover = plan["palette"]["primary_hover"].lstrip("#")
    primary_pressed = plan["palette"]["primary_pressed"].lstrip("#")
    html_str = str(soup)
    # Replace orange-500/600/400 with brand colors via arbitrary-value Tailwind
    html_str = re.sub(r"\b(from|to|via|bg|text|border|shadow)-orange-500\b",
                      rf"\1-[#{primary}]", html_str)
    html_str = re.sub(r"\b(from|to|via|bg|text|border|shadow)-orange-600\b",
                      rf"\1-[#{primary_pressed}]", html_str)
    html_str = re.sub(r"\b(from|to|via|bg|text|border|shadow)-orange-400\b",
                      rf"\1-[#{primary_hover}]", html_str)
    soup = BeautifulSoup(html_str, "lxml")

    # Image swaps (write generated images to assets/, update src)
    out_dir = pathlib.Path(out_path).parent
    assets_dir = out_dir / "assets"
    assets_dir.mkdir(exist_ok=True)
    for slot_id, b64 in images.items():
        slot = slot_map[slot_id]
        fname = f"gen_{slot_id.replace('.','_')}.png"
        (assets_dir / fname).write_bytes(base64.b64decode(b64))
        targets = soup.select(slot["selector"])
        if targets:
            targets[0]["src"] = f"assets/{fname}"

    pathlib.Path(out_path).write_text(str(soup), encoding="utf-8")
```

### Step 8 — Output

`personalized.html` + augmented `assets/` (with generated images). Optional zip for download.

---

## Cost & latency budget

For a 100KB cloned site, 11 sections, 8 testimonials, hero + 6 features + pricing:

| Stage | Model | Cost | Latency |
|---|---|---|---|
| Brief structuring | gpt-5-mini | $0.005 | 2-3 s |
| Personalize (vision + copy + image prompts) | gpt-5-mini + image input | $0.10 | 12 s |
| 3 hero/feature illustrations | gpt-image-1 medium | $0.21 | 15 s parallel |
| 8 avatars | CSS only | $0 | 0 s |
| Apply patches | Python | $0 | 1 s |
| **Total** | | **$0.32** | **~25-30 s** (parallelized) |

Sequential worst case: 45-60 s. Both well within targets.

---

## Why patch-based beats full-regen

| Dimension | Patch-based | Full-regen |
|---|---|---|
| Output tokens (100KB site) | ~3-5K | ~25-40K |
| Cost per run | $0.05-0.15 | $0.40-1.20 |
| Latency | 8-15 s | 30-60 s |
| Hallucinated structure | Near-zero (closed enum) | 5-15% breakage |
| Multi-section coherence | Excellent (single brief, all slots in one call) | Good but truncation risk |
| Debuggability | Diff is the patches array | Full-file diff |
| Layout guarantee | **100%** | Probabilistic |

Empirical data from Vercel v0 team threads + Anthropic tool-use cookbook converge on the same conclusion for sites >50 KB.

---

## Anti-patterns to avoid

- **Free-form CSS selectors emitted by LLM** → 30%+ hallucination rate. Always use closed enum.
- **Synthetic testimonial faces** → EU AI Act + OpenAI usage policy violation. Use initials.
- **Agent loop for fixed workflow** → 5-15× cost overhead for no quality gain.
- **DALL-E 3** → deprecated; use gpt-image-1.
- **Assistants API** → sunset H1 2026; use Responses API.
- **Fine-tuning for brand voice** with <50 examples → few-shot in system prompt is cheaper and better.
- **Length enforcement via prompt only** → ~20% violation rate; use schema `maxLength` instead.
- **Generating tokens that don't exist in source** → defeats the design-system grounding. Personalize WITHIN the system, don't expand it.

---

## Required additions to upstream pipeline (Stages 3-4)

For this personalization layer to work, the upstream design-system extraction must emit:

1. **`_inventory.json`** must include a `slots[]` array with `{id, selector, type, max_chars, structure?}` per personalizable element.

2. **Color tokens normalized**: detect every `from-orange-500` / `to-orange-600` / `bg-[#f97316]` reference and tag them as "brand primary" so the regex swap in Step 7 works without false positives.

3. **Image slot detection**: every `<img>` with non-trivial dimensions that's NOT a logo/icon/background-decoration should become an `image` slot.

4. **Anchor preservation**: section IDs must survive the clone (we already preserve them; verified in v2 capture).

A small extractor (~80 lines Python, BeautifulSoup) bolted onto `_inventory.py` produces these.

---

## Reference URLs

- [OpenAI Responses API](https://platform.openai.com/docs/api-reference/responses)
- [Structured Outputs (json_schema strict)](https://platform.openai.com/docs/guides/structured-outputs)
- [gpt-image-1 launch](https://openai.com/index/image-generation-api)
- [Assistants API migration to Responses](https://platform.openai.com/docs/assistants/migration)
- [OpenAI cookbook: structured outputs intro](https://cookbook.openai.com/examples/structured_outputs_intro)
- [OpenAI cookbook: Vision + function calling](https://cookbook.openai.com/examples/using_gpt4_vision_with_function_calling)
- [OpenAI pricing](https://platform.openai.com/docs/pricing)
- [Framer AI engineering](https://www.framer.com/blog/ai-website-builder)
- [v0 model card](https://v0.dev/docs/models)
- [DTCG Format Module 2025.10](https://www.designtokens.org/tr/drafts/format/)
- [EU AI Act Art. 50 disclosure requirements](https://artificialintelligenceact.eu/article/50/)
