# Spec — UI Rebrand: Kratos Clone (orange radial on dark)

**Date:** 2026-05-16
**Status:** approved (dev-workflow Alta complexity, single-iteration)
**Closes:** user rebrand request 2026-05-16 + U6 connector fill direction bug
(discovered via Playwright smoke test 2026-05-16)

## Objective

Visual + functional rebrand of the two-page Flask app:

1. **New brand identity** — name "Kratos Clone — Website Downloader", dark
   base with vivid-orange radial gradient elements, distinctive typography.
2. **Highlight box on `/`** — visible, hover-active card linking to
   `/personalize` (today a small footer link — promote it to a hero CTA).
3. **`/personalize` expansion** — more options (sample brief button, recent
   captures hint), tips section (how it works, what to expect), icebreakers
   (preset brief examples to populate the form).
4. **Motion + shadows** — multi-layer shadow system, page-load stagger,
   hover-lift, pulse on primary CTA.
5. **Drive-by fix**: U6 step-indicator connector fill direction
   (currently fills incoming-to-completed; should fill outgoing-from-completed).

## Scope

### In
- Full visual rebrand of both templates (`index.html`, `personalize.html`)
- CSS design tokens system (custom properties), single source of truth in each template
- New tips + sample-brief section on `/personalize`
- Highlight box on `/`
- U6 connector fill logic fix (3-line JS change)
- Regression tests for: brand name presence, highlight box, tips section, connector fix

### Out (deferred)
- Web fonts via CDN: keep system stack augmented with Google Fonts via
  `<link rel=stylesheet>` only if performance budget allows (no FOIT)
- Logo SVG: text-based wordmark only; SVG mark deferred
- Light-mode toggle: dark-only this PR
- I18n: PT-BR only (current default)

## Architecture

### Color tokens (consolidate to `:root` custom properties)

```css
:root {
    /* base */
    --ink-base: #0a0a14;          /* deepest dark */
    --ink-elevated: #14141f;      /* card surface */
    --ink-overlay: #1c1c2a;       /* hover/focus surface */
    /* accent */
    --orange-core: #ff6b35;       /* primary brand */
    --orange-bright: #ff8c42;     /* hover/highlight */
    --orange-deep: #e64a19;       /* pressed */
    --orange-glow: rgba(255, 107, 53, 0.4);
    /* text */
    --text-primary: #f5f5fa;
    --text-secondary: #a0a0b8;
    --text-muted: #6b6b80;
    /* semantic */
    --success: #4ade80;
    --error: #fb7185;
    --warning: #fbbf24;
    /* effects */
    --shadow-ambient: 0 1px 3px rgba(0, 0, 0, 0.4);
    --shadow-key: 0 8px 24px rgba(0, 0, 0, 0.5);
    --shadow-glow: 0 0 32px var(--orange-glow);
}
```

### Typography
- Display (h1, brand): **Space Grotesk** via Google Fonts (geometric sans, has character without being trendy)
- Body: system stack (preserved — no FOIT risk)
- Weights: 400 body, 500 emphasized, 600 buttons, 700 brand

### Background — radial atmosphere

```css
body {
    background:
        radial-gradient(circle at 30% 10%, rgba(255, 107, 53, 0.18), transparent 55%),
        radial-gradient(circle at 85% 90%, rgba(255, 107, 53, 0.10), transparent 50%),
        var(--ink-base);
}
```

Two radial hotspots — one bright (top-left ~30/10), one dim (bottom-right ~85/90). Creates depth without being noisy. CSS-only, no canvas/SVG.

### Motion grammar
- Page-load stagger: hero (0ms), tagline (80ms), card (160ms), footer link (240ms) — opacity 0→1 + translateY 8→0
- Hover-lift on highlight box: translateY(-2px) + shadow grows from key to key+glow, 200ms ease
- Pulse on primary CTA: subtle scale 1↔1.015, 2s ease-in-out infinite (paused on hover)
- All animations respect `prefers-reduced-motion: reduce`

### Highlight box on `/`

Big card below the download form, before the footer. Visual structure:

```
┌─────────────────────────────────────────┐
│ ✦ NOVO                                  │  ← orange chip badge
│                                         │
│ Personalize um capture                  │  ← display font
│ com sua marca via IA                    │
│                                         │
│ Transforme qualquer site clonado em uma │  ← descriptor
│ versão com seu logo, cores e copy.      │
│                                         │
│ ┌─────────────────────────────────┐    │
│ │  Abrir personalizador  →        │    │  ← CTA, hover-lift, glow
│ └─────────────────────────────────┘    │
└─────────────────────────────────────────┘
```

Hover state: lifts -2px, shadow grows ambient+key+glow, orange border subtly brightens.

### `/personalize` expansion

Inserted between `<h1>` and the step indicator:
1. **Tips banner** (collapsible, default-open on first visit, localStorage persist)
   - "Como funciona" — 3 short steps
   - "Dicas pra um bom brief" — 3 bullets
   - "Tempo esperado" — ~30s extract + ~70s personalize
2. **Sample brief button** — appears next to brief textarea, populates with curated example
3. **Three icebreaker examples** — chips below sample-brief: "SaaS de produtividade", "App de fitness", "Plataforma educacional" — click populates brief with the corresponding ready-to-use text

### U6 connector fix

Current (buggy):
```js
if (state === 'completed' && n > 1) {
    var conn = document.getElementById('step-connector-' + (n - 1) + '-' + n);
}
```

Fixed:
```js
if (state === 'completed' && n < 3) {
    var conn = document.getElementById('step-connector-' + n + '-' + (n + 1));
}
```

Semantics: "when step N completes, fill the trail from N to N+1" (forward direction, matches operator's mental model of progress).

## Task decomposition

| # | Task | Files | ~Time |
|---|------|-------|-------|
| T1 | Dispatch ui-ux-designer agent for complete spec (color tokens, typography, components, motion grammar, copy for tips/icebreakers) | brief only | 5m |
| T2 | Integrate token system + body radial bg + brand title in index.html | `templates/index.html` | 15m |
| T3 | Integrate highlight box + motion in index.html | `templates/index.html` | 15m |
| T4 | Apply rebrand to personalize.html (colors, brand, step indicator polish) | `templates/personalize.html` | 15m |
| T5 | Add tips banner + sample-brief + icebreakers to personalize.html | `templates/personalize.html` | 25m |
| T6 | Fix U6 connector direction (n+1 instead of n-1) | `templates/personalize.html` | 5m |
| T7 | Extend regression tests | `tests/test_template_a11y.py` | 15m |
| T8 | Gate sweep, smoke test re-run, commit, PR | — | 15m |

Total: ~110m.

## Risks + plan B

| Risk | Plan B |
|------|--------|
| Google Fonts FOIT delays render | `font-display: swap` + fallback to system stack |
| Radial gradient performance on low-end | Single radial instead of two if FPS issue |
| Too many changes break a11y test contract | Run tests after each phase; adjust assertions to remain semantic (not literal) |
| Tips section adds 100+ LOC | Acceptable — within scope creep limits per Alta |
| Icebreaker examples feel templated | ui-ux-designer agent produces real domain copy |

## Acceptance criteria

- [ ] Both templates declare `:root` CSS custom properties for the new token system
- [ ] Body uses two-layer radial gradient on `--ink-base`
- [ ] Brand title "Kratos Clone" rendered in display font + descriptor "Website Downloader" / "Personalizador"
- [ ] `/` has a highlight box linking to `/personalize` (visible, above-fold-on-1080p)
- [ ] `/personalize` has: tips banner (collapsible) + sample-brief button + 3 icebreaker chips
- [ ] U6 connector fix: completing step N fills connector N → N+1
- [ ] Motion respects `prefers-reduced-motion: reduce`
- [ ] All gates green: pytest, ruff, mypy, bandit MEDIUM
- [ ] Tests ≥ 264 (257 baseline + ~7 new for brand/highlight/tips/connector-fix)
- [ ] No regression in existing a11y contracts
- [ ] Playwright smoke screenshots show: new dark+orange aesthetic, highlight box on `/`, tips section + icebreakers on `/personalize`, step indicator connector fill correctly during transition
