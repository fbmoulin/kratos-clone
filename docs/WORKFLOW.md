# Site Replica → Design System Workflow

> End-to-end pipeline for reliably cloning modern SPA marketing sites and extracting a living design system.
> Backed by webrecorder/browsertrix patterns, Apify scraping playbook, Anthropic prompt-engineering docs, and DTCG W3C spec.

> **Implementation status (2026-04-27).** Stages 2 and 4 (Track A) are implemented.
> Stages 1 (`scripts/probe.py`), 3 (`scripts/post_process.py`), 6 (`scripts/validate.py`)
> are **aspirational** — referenced in this doc as the target architecture but not yet
> coded. See `ROADMAP.md` for the phased plan and `docs/AUDIT.md` for current findings.

---

## Why the v1 clone missed content

The v1 download of `nexusflow-saas.aura.build/` correctly captured **all 11 sections** in `index.html`, but only **9 images** out of an estimated 30-50 the site has. Root causes (ranked):

1. **IntersectionObserver-gated lazy-loads never fired.** Aura sites use GSAP ScrollTrigger + `<img loading="lazy">`. Sections below fold mounted but their hero images never swapped from placeholder to real `src`.
2. **Spline 3D scenes** are CORS-isolated iframes (`https://*.spline.design`) — never inlineable.
3. **Naive scroll** (20 viewport jumps × 600 ms) doesn't allow IO observers with `rootMargin: '0px 0px -100px 0px'` to fire reliably; many libraries ALSO use `requestIdleCallback`-deferred work that needs settle time.
4. **`wait_until=domcontentloaded`** returns before code-split chunks finish loading.
5. **Lenis smooth-scroll** intercepts programmatic `window.scrollTo` and queues — observers never tick.

(Sources: Browserless lazy-load blog, Apify infinite-scroll patterns, Playwright issue #14087.)

---

## Pipeline architecture (5 stages)

```
┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐
│ 1. PROBE │ → │ 2. CAPTURE│ → │ 3. POST- │ → │ 4. EXTRACT│ → │ 5. RENDER│
│  (URL)   │   │ (Playwright│   │ PROCESS  │   │ (DTCG +   │   │ (LLM v2  │
│          │   │  hardened) │   │ (rewrite,│   │  inventory│   │  prompt) │
│          │   │           │   │  audit)  │   │  Python)  │   │          │
└──────────┘   └──────────┘   └──────────┘   └──────────┘   └──────────┘
                                                  ↓
                                            ┌──────────┐
                                            │ 6. VALIDATE│
                                            │ (visual    │
                                            │  diff +    │
                                            │  coverage) │
                                            └──────────┘
```

### Stage 1 — Probe (5 s)

`scripts/probe.py` — light HEAD + GET to:
- Confirm 200 OK, no auth/captcha
- Detect SPA framework via `<meta>` and bundle filename (Vite `index-*.js`, Next.js `_next/static`, Webflow `webflow.js`, Aura `aura.build/runtime`)
- Estimate scroll depth from `<section>` count in pre-render shell (if any)
- Check CSP `frame-ancestors` (blocks our static-server iframe testing)
- Check `prefers-color-scheme` media queries in initial CSS

Output: `probe.json` with `{framework, has_spline, has_iframe_content, estimated_sections, csp_summary}`. Drives Stage 2 config.

### Stage 2 — Capture (60-180 s) — **HARDENED**

Apply 5 patches to current `downloader.py`:

#### Patch A — IntersectionObserver pre-fire polyfill (HIGH IMPACT)

Inject via `page.add_init_script()` BEFORE `page.goto()`. Replaces native IO with a polyfill that immediately fires the callback for every observed element with `isIntersecting: true`.

```js
// inject in WebsiteDownloader before goto()
const _IO = window.IntersectionObserver;
window.IntersectionObserver = class {
  constructor(cb, opts) { this._cb = cb; this._opts = opts; }
  observe(el) {
    queueMicrotask(() => this._cb([{
      target: el, isIntersecting: true, intersectionRatio: 1,
      time: 0, boundingClientRect: el.getBoundingClientRect(),
      intersectionRect: el.getBoundingClientRect(), rootBounds: null
    }], this));
  }
  unobserve(){} disconnect(){} takeRecords(){return [];}
};
```

Effort: S (10 lines).

> **Caveat — qualitative claim, no A/B isolation.** This patch was shipped together
> with B/C/D/E. We have not run a controlled experiment with only Patch A enabled to
> measure its independent contribution. Earlier drafts of this doc claimed "+70%
> lazy-load capture"; that figure is a design rationale, not a measurement. See
> `docs/AUDIT.md` § P2-9.
>
> **Caveat — animation side effect.** Forcing every observer to fire `isIntersecting:true`
> at page load triggers all GSAP/AOS/Framer Motion entrance animations simultaneously.
> For `from` tweens (start invisible → animate to visible) this is correct. For `to`
> tweens that animate elements TO a different state on scroll, elements may end up in
> their scrolled-state position at page load — captured DOM is structurally complete
> but element positions may be semantically wrong.

#### Patch B — `wait_until="networkidle"` + 5s buffer + DOM-stable predicate

Replace `domcontentloaded`. After `goto`, wait for:

```js
() => new Promise(res => {
  let t = setTimeout(() => res(true), 1500);
  new MutationObserver(() => { clearTimeout(t); t = setTimeout(() => res(true), 1500); })
    .observe(document.body, {childList:true, subtree:true, attributes:true});
})
```

(Resolves only after DOM stops mutating for 1500 ms.) Effort: S.

#### Patch C — Three-pass scroll with Lenis detection

```python
async def hardened_scroll(page):
    # Detect & disable Lenis if present
    await page.evaluate("""
        if (window.lenis && typeof window.lenis.destroy === 'function') {
            window.lenis.destroy();
            window.lenis = null;
        }
    """)
    h = await page.evaluate("() => document.body.scrollHeight")
    vh = await page.evaluate("() => window.innerHeight")

    # Pass 1: forward fast (warm-up)
    for y in range(0, h, int(vh * 0.8)):
        await page.evaluate(f"window.scrollTo(0, {y})")
        await page.wait_for_timeout(400)

    # Pass 2: forward slow (settle observers)
    for y in range(0, h, int(vh * 0.6)):
        await page.evaluate(f"window.scrollTo(0, {y})")
        await page.wait_for_timeout(900)

    # Pass 3: backward slow (catch sticky/parallax)
    for y in range(h, 0, -int(vh * 0.6)):
        await page.evaluate(f"window.scrollTo(0, {y})")
        await page.wait_for_timeout(900)

    await page.evaluate("window.scrollTo(0, 0)")
    await page.wait_for_timeout(500)
```

Effort: M (50 lines).

#### Patch D — Recursive shadow DOM + iframe serializer

> ✅ **Fixed in Phase 2 (2026-04-27).** Earlier implementation used
> `cloneNode(true)` which per HTML spec does NOT copy shadow roots. The walker
> now operates on the **live** `document.documentElement` and serializes the tree
> manually, emitting Declarative Shadow DOM (`<template shadowrootmode="open">`)
> for each open shadow root. Closed shadow roots are inaccessible by spec — count
> surfaced in `manifest.json` as `shadow_skipped_closed`.

Replaces `await page.content()` with a custom serializer that walks shadow roots and
same-origin iframes. Modern browsers re-render Declarative Shadow DOM identically.

Cross-origin iframes (Spline, Calendly) cannot be serialized — capture URL +
dimensions + a reference screenshot instead.

Effort: shipped (~100 lines walker in `kratos_clone/capture.py:81-157`).

#### Patch E — Computed-style snapshot for design-system extraction

After full settle, run:

```js
const snap = {};
document.querySelectorAll('*').forEach((el, i) => {
  const cs = getComputedStyle(el);
  snap[el.tagName + '#' + i] = {
    fontSize: cs.fontSize, fontWeight: cs.fontWeight,
    color: cs.color, background: cs.backgroundColor,
    boxShadow: cs.boxShadow, borderRadius: cs.borderRadius,
    transitionDuration: cs.transitionDuration,
    transitionTimingFunction: cs.transitionTimingFunction,
    classes: el.className,
    selector: cssPath(el),
  };
});
```

Save as `styles.json` next to `index.html`. **Critical:** lets Stage 4 extraction work without re-running the page, and captures runtime-injected styles (CSS-in-JS, GSAP keyframes).

Effort: M (40 lines).

#### Other knobs to expose (env vars or constructor params):

```bash
KCD_VIEWPORT_WIDTH=1920          # default 1920
KCD_VIEWPORT_HEIGHT=1080         # default 1080
KCD_NAV_TIMEOUT=90000            # default 60000
KCD_SCROLL_PASSES=3              # default 1
KCD_DOM_STABLE_MS=1500           # new
KCD_PRESERVE_ANIMATIONS=true     # NEW — skips destructive scroll-fix CSS injection
KCD_USER_AGENT=...               # default Chrome 120 macOS
KCD_HEADED=false                 # for WebGL/Spline rendering
KCD_CAPTURE_COMPUTED_STYLES=true # new — emits styles.json
```

### Stage 3 — Post-process (5-15 s)

`scripts/post_process.py`:

1. **Strip destructive CSS** — remove `<style data-scroll-fix="true">` and similar overlays IF `KCD_PRESERVE_ANIMATIONS=true` (default true going forward).
2. **Asset audit** — diff captured assets vs `<img>` / `url()` references in HTML; report broken refs.
3. **Image fallback handler** — if source page has a fallback handler script (Aura's `data-img-fallback-handler`), keep it; ensures CDN images that 404 cycle through replicas.
4. **Inline base-64 small images** (<10 KB, opt-in) so the file is portable.
5. **Run `_inventory.py`** to emit `_inventory.json` (the same script we used for v1; reusable).

### Stage 4 — Extract (10-30 s)

Two complementary tracks:

#### Track A — Programmatic (current Python script, deterministic)

`_generate_ds.py` — runs the v1 generator. Fast, reproducible, no LLM cost. Output: `design-system.html` with sections rendered directly from the inventory + verbatim source markup.

Pros: zero hallucination, sub-second, free.
Cons: hardcoded section structure, can't reason about subtle design tokens or motion semantics.

#### Track B — LLM with prompt v2 (the optimized prompt)

Feed `index.html` + `_inventory.json` + `styles.json` to Claude Opus / Sonnet via `docs/PROMPT_v2.md`. Output: design-system.html with embedded DTCG JSON.

Pros: rich coverage (Accessibility, Dark Mode, States, Coverage Scorecard), DTCG-compliant, machine-readable token bundle.
Cons: $0.50-2.00 per run, 2-5 min.

**Recommended:** run both. Track A is the bulletproof baseline; Track B is the polished deliverable. Diff them as a quality gate.

### Stage 5 — Render (already happens in Stage 4)

Open in browser via static server:
```bash
cd extracted && python -m http.server 8765
# Visit http://localhost:8765/design-system.html
```

### Stage 6 — Validate (15-60 s)

`scripts/validate.py` runs:

1. **Coverage scorecard** — count DTCG categories present in extracted output. Target: ≥10/13.
2. **Visual diff** — Playwright screenshot of source vs `design-system.html` Hero (should be visually identical except for swapped text).
3. **Asset reference check** — every `<link>`, `<script src>`, `<img src>` in design-system.html resolves to a 200-OK file.
4. **No-placeholder check** — grep for "Lorem", "TODO", "[content]", "...".
5. **Verbatim class check** — sample 10 buttons/cards from output; each class string must appear byte-for-byte in source.
6. **WCAG contrast pass** — for each declared color pair, compute contrast ratio; fail if any text/bg pair is below 3:1 (large) or 4.5:1 (body).

Output: `validate-report.md` with pass/fail per check + actionable fixes.

If coverage <80% OR visual diff fails Hero check → return to Stage 2 with adjusted params (higher `KCD_SCROLL_PASSES`, `KCD_DOM_STABLE_MS`, etc.).

---

## Suggested file layout going forward

```
Website-Downloader/
├── app.py                  # Flask UI — keep existing
├── downloader.py           # Apply patches A-E
├── docs/
│   ├── PROMPT_v2.md        # ← optimized LLM prompt
│   └── WORKFLOW.md         # ← this file
├── scripts/
│   ├── probe.py            # Stage 1
│   ├── post_process.py     # Stage 3
│   ├── _inventory.py       # Stage 3 (reusable inventory builder)
│   ├── _generate_ds.py     # Stage 4 Track A (programmatic)
│   └── validate.py         # Stage 6
└── extracted/
    └── <session_id>/
        ├── index.html
        ├── styles.json     # NEW — computed-style snapshot
        ├── _inventory.json # NEW — design system inventory
        ├── design-system.html  # final deliverable
        └── assets/...
```

---

## Comparison with industry alternatives

| Stack | Strengths | Why not chosen |
|---|---|---|
| **Browsertrix Crawler** (webrecorder) | Best-in-class fidelity, WARC + behaviors, Kubernetes-ready | WARC binary blobs not LLM-friendly; multi-page focus; no design-system awareness |
| **SingleFile CLI** | Excellent shadow DOM + iframe inlining, 15K stars, weekly releases | No scroll/lazy-load handling, no asset rewrite to relative paths, no inventory |
| **Dembrandt** | Purpose-built design extractor, DTCG output, AI-agent-friendly DESIGN.md | URL-only (would need our static server first), opinionated bucketing, no Hero-clone showcase |
| **designlang/design-extract** | Tailwind v4 emitter, Claude Code MCP server, multi-platform | Same — no showcase HTML output, design-system focus only |
| **monolith** (Rust) | Best for static sites, zero deps, single binary | Doesn't execute JS — useless for SPAs |
| **wget --mirror / HTTrack** | Universal | Doesn't execute JS — useless for SPAs |

**Verdict:** combine SingleFile-like serialization (Patch D) + Dembrandt-like extraction (Stage 4 Track B with v2 prompt) inside our Python+Playwright pipeline. Best of both worlds in one repo.

---

## Quick wins (in implementation priority order)

| # | Item | Stage | Effort | Expected gain |
|---|------|-------|--------|---------------|
| 1 | Add `KCD_PRESERVE_ANIMATIONS=true` flag (skip scroll-fix CSS injection) | 2/3 | XS | Restores GSAP/AOS animations |
| 2 | Patch A: IntersectionObserver pre-fire polyfill | 2 | S | +70% lazy-load capture |
| 3 | Patch B: networkidle + DOM-stable predicate | 2 | S | Catches code-split chunks |
| 4 | Patch C: Three-pass scroll + Lenis detect | 2 | M | +30% scroll-triggered content |
| 5 | Patch E: computed-style snapshot → `styles.json` | 2 | M | Enables true DTCG extraction |
| 6 | Apply prompt v2 (Stage 4 Track B) | 4 | XS (just paste) | Adds Coverage Scorecard, Accessibility, Dark Mode, Tokens JSON |
| 7 | Patch D: shadow DOM + iframe walker | 2 | M | Web Components support (~5% of sites) |
| 8 | `validate.py` script | 6 | M | Quality gate, regression detection |

Items 1+2+3+6 ship in <1 day and likely solve the "captured half" problem entirely.

---

## Reference URLs

- Anthropic — [Long context tips](https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/long-context-tips)
- Anthropic — [Reduce hallucinations](https://platform.claude.com/docs/en/test-and-evaluate/strengthen-guardrails/reduce-hallucinations)
- Webrecorder — [Browsertrix Crawler](https://github.com/webrecorder/browsertrix-crawler)
- gildas-lormeau — [SingleFile](https://github.com/gildas-lormeau/SingleFile)
- ArchiveBox — [github.com/ArchiveBox/ArchiveBox](https://github.com/ArchiveBox/ArchiveBox)
- Dembrandt — [github.com/dembrandt/dembrandt](https://github.com/dembrandt/dembrandt)
- design-extract — [github.com/Manavarya09/design-extract](https://github.com/Manavarya09/design-extract)
- Project Wallace tokens — [css-design-tokens](https://github.com/projectwallace/css-design-tokens)
- DTCG Format Module 2025.10 — [designtokens.org/tr/drafts/format](https://www.designtokens.org/tr/drafts/format/)
- Tailwind v4 theme docs — [tailwindcss.com/docs/theme](https://tailwindcss.com/docs/theme)
- Dhuliawala et al. — [Chain-of-Verification arXiv:2309.11495](https://arxiv.org/abs/2309.11495)
- Liu et al. — [Lost in the Middle arXiv:2307.03172](https://arxiv.org/abs/2307.03172)
- Vercel Geist · GitHub Primer · Polaris · Material 3 · Atlassian · Carbon · Stripe — best-in-class living systems
