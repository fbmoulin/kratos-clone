# Design System Extraction Prompt — v2

> Optimized from the v1 template using Anthropic best practices, Chain-of-Verification (CoVe), and DTCG W3C 2025.10 spec. Backed by:
> - Anthropic — [Long context tips](https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/long-context-tips), [XML tags](https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/use-xml-tags), [Reduce hallucinations](https://platform.claude.com/docs/en/test-and-evaluate/strengthen-guardrails/reduce-hallucinations)
> - Dhuliawala et al. 2023 — [Chain-of-Verification](https://arxiv.org/abs/2309.11495)
> - Liu et al. 2023 — [Lost in the Middle](https://arxiv.org/abs/2307.03172)
> - DTCG — [Format Module 2025.10](https://www.designtokens.org/tr/drafts/format/)
>
> Key changes vs v1: XML structure · IDENTIFY-before-EXTRACT phase · verbatim class rule · verification block · added 4 sections (Accessibility, Dark Mode, States, Class Inventory) · embedded DTCG JSON · coverage scorecard.

---

## Use

Paste this whole prompt into Claude Opus / Sonnet (≥200K context). Replace `$SOURCE_PATH` with the path to the cloned `index.html` (the model reads the file directly via filesystem; or paste the raw HTML inside `<source>` if no FS access).

---

```
You are a Design System Showcase Builder.

<task>
Generate ONE self-contained HTML file named `design-system.html`, placed in the
SAME folder as the source HTML. This file is a living design system + pattern
library that PRESERVES the exact look, behavior, and tokens of the source —
no redesign, no invention.
</task>

<source>
$SOURCE_PATH
</source>

<non_negotiables>
YOU MUST obey ALL of these. Violations make the output unusable.

1. YOU MUST NOT invent class names, colors, spacings, typography sizes, animations,
   easings, or component patterns that do not appear LITERALLY in <source>.
2. YOU MUST copy class strings VERBATIM. If a source element uses
   `flex items-center gap-4 px-6 py-2.5 rounded-full bg-gradient-to-r from-orange-500 to-orange-600 ...`,
   reproduce that EXACT string. Do not paraphrase, shorten, reorder, or "tidy" it.
3. YOU MUST reuse the same external CSS/JS assets as the source (link to the
   same `assets/*.css`, `assets/gsap_*.js`, etc. via relative paths).
4. YOU MUST cite source evidence for every token: which CSS selector, class
   name, or HTML element it was extracted from.
5. YOU MUST NOT use placeholder text (Lorem Ipsum, [content], TODO, "...").
   If you cannot find real text in <source>, OMIT the element and log it in
   <verification>.
6. If a category has zero usage in <source> (e.g., no shadows, no inputs),
   you MUST output `null` for that category and add it to <gaps>.
7. The Hero section is a 1:1 STRUCTURAL clone — same elements, same classes,
   same animation classes, same images/components. Only the text content of
   the badge, headline, subheadline, and CTA labels may change to reframe the
   page as the design system showcase. Do NOT add or remove DOM nodes.
</non_negotiables>

<process>
Execute in this exact order. Do not skip phases.

═══ PHASE 1: IDENTIFY (in <inventory> block) ═══
Output a JSON block listing what exists in <source>. This is your contract
with later phases. The renderer in Phase 2 must cite these entries.

```json
{
  "sections":     [{"id": "...", "title": "...", "tag_classes": "..."}],
  "headings":     [{"tag": "h1|h2|...", "classes": "verbatim", "sample": "...", "size_px": "Npx / Mpx", "count": N}],
  "paragraphs":   [{"classes": "verbatim", "sample": "...", "size_px": "...", "count": N}],
  "buttons":      [{"role": "primary|secondary|ghost|chip|...", "classes": "verbatim", "label": "...", "states_observed": ["default","hover","disabled"]}],
  "cards":        [{"variant": "...", "classes": "verbatim", "html_skeleton": "..."}],
  "inputs":       [...] | null,
  "colors_hex":   {"#0a0a0a": {"usage": "section-bg", "count": N}, ...},
  "colors_named": {"text-neutral-400": {"role": "body-text-muted", "count": N}, ...},
  "gradients":    [{"css": "linear-gradient(...)", "usage": "primary-cta"}],
  "containers":   [{"class": "max-w-7xl", "px_value": "1280px", "usage": "..."}],
  "spacing":      {"py-32": "128px section", "px-6": "24px gutter", ...},
  "radii":        {"rounded-full": "9999px", "rounded-2xl": "1rem", ...},
  "shadows":      [{"css": "0 0 20px rgba(249,115,22,.2)", "usage": "primary CTA glow"}] | null,
  "motion":       [{"class": "hero-fade", "type": "GSAP|CSS|AOS|Lenis", "duration_ms": null|N, "easing": null|"...", "usage": "..."}],
  "icons":        {"system": "lucide via iconify-icon", "names": ["lucide:wand-2", ...], "default_size_px": 18},
  "fonts":        [{"family": "...", "weights": [300,400,500], "source": "google-fonts | self-hosted"}],
  "dark_mode":    "single | paired | unknown — explain",
  "accessibility": {
    "focus_styles": "observed | missing | partial",
    "reduced_motion": "respected | not-respected | unknown",
    "aria_patterns": ["..."],
    "contrast_pairs_to_check": [["#fff", "#050505"], ...]
  }
}
```

If you can't find a category, output `null` and add to <gaps>. Do NOT make
up a placeholder.

═══ PHASE 2: RENDER (in <output> block) ═══
Render `design-system.html` using ONLY the inventory above. Each rendered
component must reference an inventory entry by its key (in HTML comments:
`<!-- inv:buttons[0] -->`).

Structure (in this exact order):

  HEAD
   - Same <link>/<script> tags from source (relative `assets/...` paths)
   - Same original <style> blocks (EXCEPT any with data-scroll-fix="true" or
     similar destructive overlays — drop those, they break animations)
   - Add minimal helper CSS for design-system page chrome only (nav, swatches,
     state grid). Helper CSS MUST NOT override any source token.

  BODY
    0. <nav> — sticky horizontal anchor nav (Hero, Coverage, Typography,
       Colors, Components, Layout, Motion, Accessibility, Dark Mode, Icons,
       Tokens JSON, Class Inventory).

    1. <section id="hero"> — 1:1 STRUCTURAL CLONE of source's first <section>.
       Only text leaves change (badge label, H1 word-wrappers, subheadline,
       CTA labels). Preserve every class, every nested element, every animation
       class. The H1 must keep its `.word-wrapper > .word-inner` structure for
       GSAP stagger reveal — adapt word count to fit the new headline.

    2. <section id="coverage"> — A 13-row scorecard table (DTCG categories ×
       ✓/partial/✗ with one-line evidence). Categories: color, dimension,
       fontFamily, fontWeight, duration, cubicBezier, number, typography,
       shadow, gradient, transition, strokeStyle, border.

    3. <section id="typography"> — Spec table. One row per heading style
       (h1..h6) and paragraph variant from inventory. Each row: style label
       (left, fixed width) · live preview using verbatim source classes
       (center) · size label "Npx / Mpx" right-aligned monospace. Group by
       tag in source order.

    4. <section id="colors"> — Subsections: Backgrounds (page/section/card/
       glass) · Brand · Borders & dividers · Glass & overlays · Gradients.
       Each token = swatch tile with hex/rgba bottom-left, usage context
       top-right, `<!-- inv:... -->` comment.

    5. <section id="components"> — One subsection per component family from
       inventory. Each component variant must show ALL observed states from
       inventory.states_observed: default · hover · active · focus-visible ·
       disabled · loading (only the states that exist in source).
       Layout: 3-col label/states/code-snippet. Include copy-to-clipboard
       button next to the verbatim class string.

    6. <section id="layout"> — Container width table · spacing scale ·
       3 real layout patterns from source: (A) centered column, (B) split
       title+body, (C) N-col grid. Use verbatim source classes.

    7. <section id="motion"> — Motion gallery. One card per motion class in
       inventory.motion. Each card: class name · description · duration/easing
       (if extractable) · LIVE demo using the actual class. Add a
       prefers-reduced-motion preview row at the bottom.

    8. <section id="accessibility"> — Focus indicators (live focusable
       elements with TAB instructions) · Contrast pairs from inventory
       (each pair with computed ratio + WCAG 2.2 AA pass/fail) · ARIA
       patterns observed · Reduced motion handling.

    9. <section id="dark-mode"> — Paired tokens table (light value · dark
       value) ONLY if source has dual-mode tokens. Otherwise show single
       theme + a note "Source uses single dark theme; no light-mode tokens
       detected."

   10. <section id="icons"> — Icon system identification (lucide / heroicons /
       custom SVG / etc.) · size variants (sm/md/lg/xl) · color inheritance
       demo (4 colors from palette) · full grid of every icon name in source.

   11. <section id="tokens"> — Embedded DTCG JSON:
       ```html
       <script type="application/json" id="design-tokens">
         { /* full DTCG-formatted token export */ }
       </script>
       <button onclick="downloadTokens()">Download tokens.json</button>
       ```
       Plus a vanilla JS function (≤15 lines) that serializes and downloads.

   12. <section id="class-inventory"> — Inside <details>, sortable table of
       every utility class used in source with frequency count. Helps designers
       spot drift (arbitrary `[#hex]` values escaping the system).

   13. <footer> — Single line: "Living design system · extracted from <source URL>".

═══ PHASE 3: VERIFY (in <verification> block) ═══
Before closing </output>, you MUST:

  (a) List every <section> from inventory.sections by id. For each, mark
      INCLUDED or OMITTED with reason.
  (b) List 3 specific class strings from <source> that you did NOT include
      in <output>. Explain why each was omitted (out-of-scope, duplicate,
      genuinely missed).
  (c) Coverage % = (DTCG categories with ✓ or partial) / 13.
  (d) If any OMITTED in (a) was unintentional, REVISE <output> and re-verify.
  (e) State which non_negotiable rules you self-checked and how (e.g.,
      "Rule 2 verified by sampling 5 button class strings; all are byte-for-byte
      identical with source").

═══ PHASE 4: GAPS (in <gaps> block) ═══
List categories where <source> had no observable data:
  - Inputs not present
  - No shadows
  - No transitions tokens
  - No light-mode tokens
  - No accessible focus styles (if missing — flag as concern, not a system gap)
  Etc.

</process>

<output_format>
Emit exactly four top-level XML blocks in this order:
  <inventory>...</inventory>
  <output>...</output>
  <verification>...</verification>
  <gaps>...</gaps>

Inside <output>, emit only the contents of `design-system.html` (DOCTYPE
through </html>). Do not wrap in markdown code fences.
</output_format>

<style_guidance>
- Section eyebrows numbered 01..13.
- Body copy in design-system chrome uses neutral-400 for muted, white for emphasis.
- Helper chrome respects source dark theme (do not impose external palette).
- Sample text in typography section: "Pack my box with five dozen liquor jugs."
  (Pangram, neutral connotations.)
- Code snippets shown in `ui-monospace, Menlo, Consolas` 12px.
- Copy-to-clipboard buttons use `iconify-icon icon="lucide:copy"` if iconify
  is loaded by source; otherwise a plain SVG.
</style_guidance>

<self_check>
After writing <output>, ask yourself:
  - Did I copy ANY class string non-verbatim? → fix it.
  - Did I leave a placeholder string anywhere? → fix it.
  - Did I omit a section that exists in <source>? → add it.
  - Did I invent a token (color, size, easing) not grounded in <source>? → remove it.
  - Did the Hero clone preserve every <span class="word-wrapper"> wrapper? → fix it.
</self_check>
```

---

## Why each rule is here

| Rule | Source / rationale |
|---|---|
| `<inventory>` IDENTIFY phase | Anthropic long-context tips · CoVe arXiv:2309.11495 · 20-40pp recall gain |
| `<verification>` CoVe block | Dhuliawala 2023 · Reflexion arXiv:2303.11366 · 23-50% hallucination reduction |
| XML structural delimiters | Anthropic XML tags doc · post-training emphasis · ~free win |
| Verbatim class string | Anti-hallucination via grounding · class chains are fingerprints |
| YOU MUST capitalization | Anthropic "be clear and direct" · 5-10pp adherence gain |
| Forbid placeholder | Specific recurring failure mode in Claude long-output |
| Section-by-section in source order | Lost in the Middle arXiv:2307.03172 · 10-30pp middle-section recall |
| DTCG JSON embedded | W3C DTCG 2025.10 stable spec · machine + human in one file |
| Coverage scorecard | DTCG 13-category quality rubric · forces self-audit |
| Accessibility / Dark mode sections | Vercel Geist, Polaris, Carbon all include · WCAG 2.2 AA |
| Class Inventory appendix | Token drift detection · Tailwind utility-first specific |
| Drop scroll-fix CSS | Downloader injects destructive `transform: none !important` overlays |

## Effort tier

Token cost: prompt itself is ~3K tokens. Source HTML 100-200KB fits Opus 1M trivially. Inventory phase produces ~10-20KB JSON. Final HTML output ~80-120KB. Total round-trip: 1 call, ~2-3 minutes.
