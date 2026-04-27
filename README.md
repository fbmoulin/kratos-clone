# 🌐 kratos-clone

Hardened SPA site cloner + DTCG design system extractor + OpenAI personalization spec.
Fork of [`asimov-academy/Website-Downloader`](https://github.com/asimov-academy/Website-Downloader)
with substantial additions on top of the original Flask UI.

> **Status:** MVP operational. Three implementation flaws identified in `docs/AUDIT.md` are
> tracked in `ROADMAP.md` (Phase 2). Two upstream-overlapping modules co-exist (`downloader.py`
> = original, `kratos_clone/` = new hardened module). Tests are the largest gap (see Phase 1).

---

## ✨ What this fork adds

| Layer | Module | Purpose |
|-------|--------|---------|
| **Hardened capture** | `kratos_clone/` | Playwright module with 5 patches (IO pre-fire, DOM-stable, 3-pass scroll, shadow walker, computed-style snapshot) for SPA-heavy sites where the original downloader missed content. CLI: `python -m kratos_clone <url>`. |
| **Design-system extraction** | `scripts/inventory.py` + `scripts/generate_design_system_v{1,2}.py` | Parse a captured HTML + emit a self-contained `design-system.html` showcase (typography, colors, components, motion, icons) with embedded DTCG token JSON. |
| **Observability** | `app.py` + `templates/index.html` | `structlog` backend + inline browser logger (`window.onerror`, `unhandledrejection`, `console.error`, slow fetch, SSE close) → `POST /api/client-errors` → same log stream. |
| **Architecture specs** | `docs/PROMPT_v2.md`, `docs/WORKFLOW.md`, `docs/PERSONALIZATION.md` | Optimized LLM prompt for design-system extraction, 6-stage workflow plan, and OpenAI Responses-API personalization architecture (spec only — not yet implemented). |
| **Original tool** | `app.py` (UI) + `downloader.py` (legacy capture) | Preserved from upstream. The Flask UI at `http://localhost:5001` still uses `downloader.py`; `kratos_clone/` is invoked via CLI today. |

---

## 🚀 Quick start

### Install
```bash
uv sync
uv run playwright install chromium
```

### Capture a site (new hardened CLI)
```bash
uv run python -m kratos_clone https://nexusflow-saas.aura.build/ \
    --output-dir ./capture
```

Knobs (all overridable via `KCD_*` env vars):
```bash
--passes {1,2,3}            # scroll passes (default 3)
--viewport WxH              # default 1920x1080
--headed                    # visible browser (for WebGL/Spline)
--no-styles                 # skip computed-style snapshot
--no-shadow                 # skip shadow-DOM walker
--no-io-polyfill            # disable IntersectionObserver pre-fire (debug)
```

Output: `<dir>/index.html`, `<dir>/styles.json`, `<dir>/manifest.json`, `<dir>/assets/*`.

### Generate a design system from a capture
```bash
cd ./capture
cp ../scripts/inventory.py .
cp ../scripts/generate_design_system_v2.py .
python inventory.py > _inventory.json
python generate_design_system_v2.py
# Open design-system.html in a browser
```

> Generators currently have hardcoded indices into the inventory — they work end-to-end
> on the NexusFlow template but `IndexError` on arbitrary sites. Tracked as P1-C in
> `docs/AUDIT.md` and Phase 2 in `ROADMAP.md`.

### Run the legacy Flask UI
```bash
uv run python app.py
# http://localhost:5001
```

The UI uses `downloader.py` (original, unchanged). New `structlog` observability
captures backend events + receives browser errors at `/api/client-errors`.

---

## 📁 Repo structure

```
kratos-clone/
├── app.py                     # Flask UI (upstream) + structlog + /api/client-errors
├── downloader.py              # Upstream capture (used by Flask UI)
├── templates/
│   └── index.html             # UI + inline browser logger
├── kratos_clone/              # NEW — hardened Playwright capture module
│   ├── __init__.py
│   ├── __main__.py            # CLI entry
│   ├── capture.py             # 5 patches A-E
│   └── post.py                # HTML rewrite + orphan CSS injection
├── scripts/                   # NEW — design-system extractors
│   ├── inventory.py
│   ├── generate_design_system_v1.py
│   └── generate_design_system_v2.py
├── docs/                      # NEW — architecture + audit
│   ├── AUDIT.md               # Multi-agent audit findings
│   ├── PROMPT_v2.md           # Optimized LLM extraction prompt
│   ├── WORKFLOW.md            # 6-stage pipeline plan
│   └── PERSONALIZATION.md     # OpenAI personalization spec (NOT YET IMPLEMENTED)
├── ROADMAP.md                 # Phased plan, derived from audit
├── TODO.md                    # Short-term actionable items
├── CLAUDE.md                  # Guidance for Claude Code on this repo
├── LICENSE                    # MIT (our additions)
├── NOTICE                     # Upstream attribution
├── pyproject.toml
└── .github/workflows/ci.yml   # Ruff + smoke (extends to E2E in Phase 1)
```

---

## 🛡️ Capture patches (kratos_clone/capture.py)

| Patch | What | Status | File:line |
|-------|------|--------|-----------|
| **A** — IntersectionObserver pre-fire polyfill | Forces every observer to fire `isIntersecting:true` immediately. Solves lazy-load capture on Aura/Webflow/Framer-style sites. | ✅ Working | `capture.py:38-77` |
| **B** — `networkidle` + DOM-stable predicate | MutationObserver-based: resolves only after DOM hasn't mutated for `KCD_DOM_STABLE_MS` (default 1500). | ✅ Working | `capture.py:107-117` |
| **C** — Three-pass scroll | Forward fast → forward slow → backward slow. Detects + disables Lenis. No wall-clock budget yet (P2-2). | 🟡 Working, missing time guard | `capture.py:444-481` |
| **D** — Shadow DOM walker | Recursive walk emitting Declarative Shadow DOM `<template shadowrootmode="open">`. | 🔴 **Broken** — `cloneNode` doesn't copy shadow roots; walker visits a clone with all `shadowRoot=null`. P1-A in audit. | `capture.py:78-101` |
| **E** — Computed-style snapshot | Per-element `getComputedStyle` capture → `styles.json` for downstream design-system extraction. | ✅ Working | `capture.py:_capture_computed_styles` |

Plus: `post.py` orphan-CSS injection (recovered the 440 KB Tailwind bundle from
the iframe-srcdoc wrapper page on Aura sites — likely the highest-impact line of
the entire fork).

---

## 🧪 Testing

CI (`.github/workflows/ci.yml`) runs ruff lint + format + a smoke test that imports
modules and round-trips the `/api/client-errors` endpoint. **No `tests/` directory
exists yet.** Highest-priority Phase 1 item — see `ROADMAP.md`.

---

## 📚 Reading order

1. **`docs/AUDIT.md`** — current state of the codebase, prioritized findings
2. **`ROADMAP.md`** — phased plan to address audit + extend functionality
3. **`TODO.md`** — actionable next-sprint items
4. **`docs/WORKFLOW.md`** — 6-stage pipeline architecture (Stages 1, 6 are aspirational)
5. **`docs/PROMPT_v2.md`** — LLM prompt template if extracting via Claude/Opus
6. **`docs/PERSONALIZATION.md`** — proposed OpenAI personalization layer (spec only)
7. **`CLAUDE.md`** — guidance for Claude Code agents working on this repo

---

## 📜 License & attribution

- **Our additions** (`kratos_clone/`, `scripts/`, `docs/`, observability patches to `app.py`,
  `templates/index.html`, CI, etc.): MIT — see `LICENSE`.
- **Upstream code** (`downloader.py`, original `app.py` skeleton, `templates/index.html`
  base, `Dockerfile`, deploy configs): retains original "personal and educational use" terms
  per upstream README. See `NOTICE`.

For commercial use of upstream-derived code, contact Asimov Academy directly.

---

## 🤝 Contributing

`main` is protected (squash/rebase merges only, requires CI green). Open a PR; CodeRabbit
+ Gemini + Code Review Doctor auto-review on every PR.
