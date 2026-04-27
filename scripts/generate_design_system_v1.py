"""Generate design-system.html from cloned NexusFlow HTML.

Pipeline:
  1. Parse index.html with BeautifulSoup
  2. Build new <head>: same fonts/scripts/styles, MINUS the destructive scroll-fix
  3. Hero section: deep-clone first <section>, swap only text leaves
  4. Append generated sections: Typography, Colors, Components, Layout, Motion, Icons
  5. Close with same trailing scripts
"""

from __future__ import annotations
import json
import re
from copy import deepcopy
from pathlib import Path
from bs4 import BeautifulSoup, Tag

ROOT = Path(__file__).parent
SRC = ROOT / "index.html"
OUT = ROOT / "design-system.html"

soup = BeautifulSoup(SRC.read_text(encoding="utf-8"), "html.parser")
new = BeautifulSoup(
    "<!doctype html><html><head></head><body></body></html>", "html.parser"
)
new_html = new.html
new_head = new.head
new_body = new.body

# ── 1. HEAD: copy original head minus scroll-fix and aura supabase firewall ────
orig_head = soup.head
for child in list(orig_head.children):
    if not isinstance(child, Tag):
        continue
    if child.name == "style" and child.get("data-scroll-fix") == "true":
        continue  # drop destructive overrides
    if child.name == "script" and child.get("id") == "aura-supabase-token-firewall":
        continue  # offline-only DS, don't need supabase ws shim
    new_head.append(deepcopy(child))

# Override title
title = new_head.find("title")
if title:
    title.string = "Design System — NexusFlow"
else:
    t = new.new_tag("title")
    t.string = "Design System — NexusFlow"
    new_head.append(t)

# Inject minimal extra CSS for design-system page layout (NOT touching tokens)
ds_helper_css = new.new_tag("style")
ds_helper_css.string = """
.ds-nav{position:sticky;top:0;z-index:50;backdrop-filter:blur(12px);background:rgba(5,5,5,.85);border-bottom:1px solid rgba(38,38,38,.5);padding:14px 24px;}
.ds-nav ul{display:flex;flex-wrap:wrap;gap:18px;justify-content:center;list-style:none;margin:0;padding:0;}
.ds-nav a{color:#a3a3a3;font-size:13px;text-decoration:none;letter-spacing:.04em;transition:color .2s;}
.ds-nav a:hover{color:#fb923c;}
.ds-section{padding:96px 24px;border-bottom:1px solid rgba(23,23,23,.6);}
.ds-section-inner{max-width:1200px;margin:0 auto;}
.ds-eyebrow{display:inline-block;font-size:11px;letter-spacing:.2em;text-transform:uppercase;color:#737373;margin-bottom:12px;}
.ds-section h2.ds-title{font-size:36px;color:#fff;font-weight:300;letter-spacing:-.025em;margin-bottom:8px;}
.ds-section p.ds-lede{color:#a3a3a3;font-size:15px;font-weight:300;max-width:640px;margin-bottom:48px;}
.ds-row{display:flex;align-items:flex-end;justify-content:space-between;gap:24px;padding:20px 0;border-bottom:1px solid rgba(38,38,38,.4);}
.ds-row:last-child{border-bottom:none;}
.ds-row .meta{font-size:11px;letter-spacing:.08em;color:#737373;font-family:ui-monospace,Menlo,Consolas,monospace;text-align:right;flex-shrink:0;}
.ds-row .label{font-size:11px;letter-spacing:.08em;color:#525252;text-transform:uppercase;flex-shrink:0;width:140px;}
.ds-grid{display:grid;gap:20px;}
.ds-grid.cols-2{grid-template-columns:repeat(2,minmax(0,1fr));}
.ds-grid.cols-3{grid-template-columns:repeat(3,minmax(0,1fr));}
.ds-grid.cols-4{grid-template-columns:repeat(4,minmax(0,1fr));}
.ds-grid.cols-6{grid-template-columns:repeat(6,minmax(0,1fr));}
@media(max-width:768px){.ds-grid.cols-3,.ds-grid.cols-4,.ds-grid.cols-6{grid-template-columns:repeat(2,minmax(0,1fr));}}
.ds-swatch{aspect-ratio:1.6;border-radius:14px;border:1px solid rgba(64,64,64,.4);position:relative;overflow:hidden;cursor:default;}
.ds-swatch .tag{position:absolute;bottom:8px;left:10px;font-size:11px;color:#e5e5e5;font-family:ui-monospace,Menlo,Consolas,monospace;background:rgba(0,0,0,.55);padding:3px 6px;border-radius:4px;backdrop-filter:blur(4px);}
.ds-swatch .ctx{position:absolute;top:8px;right:10px;font-size:10px;color:#a3a3a3;font-family:ui-monospace,Menlo,Consolas,monospace;background:rgba(0,0,0,.55);padding:2px 5px;border-radius:4px;letter-spacing:.05em;}
.ds-card-demo{background:#0a0a0a;border:1px solid rgba(38,38,38,.5);border-radius:18px;padding:28px;display:flex;flex-direction:column;gap:14px;min-height:160px;}
.ds-card-demo .demo-label{font-size:10px;letter-spacing:.18em;text-transform:uppercase;color:#525252;font-family:ui-monospace,Menlo,Consolas,monospace;}
.ds-state-grid{display:grid;grid-template-columns:120px 1fr;gap:18px 28px;align-items:center;padding:18px 0;border-bottom:1px solid rgba(38,38,38,.35);}
.ds-state-grid:last-of-type{border-bottom:none;}
.ds-state-label{font-size:11px;letter-spacing:.1em;text-transform:uppercase;color:#737373;font-family:ui-monospace,Menlo,Consolas,monospace;}
.ds-icon-cell{display:flex;flex-direction:column;align-items:center;gap:8px;padding:18px 8px;border:1px solid rgba(38,38,38,.4);border-radius:12px;background:#0a0a0a;}
.ds-icon-cell iconify-icon{font-size:28px;color:#e5e5e5;}
.ds-icon-cell .name{font-size:10px;color:#737373;font-family:ui-monospace,Menlo,Consolas,monospace;letter-spacing:.04em;}
.motion-frame{background:linear-gradient(135deg,#0d0d0d,#050505);border:1px solid rgba(38,38,38,.5);border-radius:18px;padding:32px;min-height:140px;display:flex;align-items:center;justify-content:center;position:relative;overflow:hidden;}
"""
new_head.append(ds_helper_css)

# ── 2. NAV ─────────────────────────────────────────────────────────────────────
nav_html = """<nav class="ds-nav"><ul>
<li><a href="#hero">Hero</a></li>
<li><a href="#typography">Typography</a></li>
<li><a href="#colors">Colors &amp; Surfaces</a></li>
<li><a href="#components">Components</a></li>
<li><a href="#layout">Layout &amp; Spacing</a></li>
<li><a href="#motion">Motion</a></li>
<li><a href="#icons">Icons</a></li>
</ul></nav>"""
new_body.append(BeautifulSoup(nav_html, "html.parser"))

# ── 3. HERO: deep-clone first <section>, swap text only ────────────────────────
hero = deepcopy(soup.find("section"))
# Anchor
hero["id"] = "hero"

# Swap badge text
badge_span = hero.select_one(".hero-fade span")
if badge_span:
    badge_span.string = "Living Design System"

# Swap H1 word-wrappers — keep the structure (each word in its own wrapper for GSAP stagger)
new_words = ["Tokens,", "components", "&", "motion", "from", "this", "exact", "design."]
word_wrappers = hero.select("h1 .word-wrapper")
# Adjust count: pad/truncate to fit
for i, w in enumerate(word_wrappers):
    inner = w.select_one(".word-inner")
    if inner is None:
        continue
    if i < len(new_words):
        inner.string = new_words[i] + (" " if i < len(new_words) - 1 else "")
    else:
        # remove extra wrappers if new words are fewer
        w.decompose()
# If we have more new words than wrappers, append additional wrappers
existing = len(hero.select("h1 .word-wrapper"))
if existing < len(new_words):
    h1 = hero.find("h1")
    template = h1.select_one(".word-wrapper")
    for w in new_words[existing:]:
        clone = deepcopy(template)
        clone.select_one(".word-inner").string = w + " "
        h1.append(clone)

# Swap subheadline
sub = hero.select_one("p.hero-fade")
if sub:
    sub.string = (
        "Every typography style, color, component, and animation class on this page is "
        "extracted directly from the source — no approximations, no redesign."
    )

# Swap CTA labels
ctas = hero.select(".hero-fade button, .hero-fade a")
labels = ["View tokens", "Explore motion"]
for i, b in enumerate(ctas):
    if i < len(labels):
        b.string = labels[i]

new_body.append(hero)

# ── 4. TYPOGRAPHY ──────────────────────────────────────────────────────────────
TW_SIZE = {
    "text-xs": "12px / 16px",
    "text-sm": "14px / 20px",
    "text-base": "16px / 24px",
    "text-lg": "18px / 28px",
    "text-xl": "20px / 28px",
    "text-2xl": "24px / 32px",
    "text-3xl": "30px / 36px",
    "text-4xl": "36px / 40px",
    "text-5xl": "48px / 1",
    "text-6xl": "60px / 1",
    "text-7xl": "72px / 1",
}


def size_label(class_str: str) -> str:
    """Return 'min / max' label using base size + largest md/lg override."""
    sizes = []
    for c in class_str.split():
        m = re.match(r"^(?:md:|lg:|xl:)?(text-\w+)$", c)
        if m and m.group(1) in TW_SIZE:
            sizes.append(TW_SIZE[m.group(1)])
    if not sizes:
        return "—"
    if len(sizes) == 1:
        return sizes[0]
    return f"{sizes[0]} → {sizes[-1]}"


inv = json.loads((ROOT / "_inventory.json").read_text())

typo_section = new.new_tag("section", id="typography", **{"class": "ds-section"})
typo_inner = new.new_tag("div", **{"class": "ds-section-inner"})
typo_inner.append(
    BeautifulSoup(
        '<span class="ds-eyebrow">01</span>'
        '<h2 class="ds-title">Typography</h2>'
        '<p class="ds-lede">Every type scale present in the source page, in hierarchy order. '
        "Live previews use the original CSS classes — no normalization.</p>",
        "html.parser",
    )
)
TYPE_ORDER = [
    ("Heading 1", "h1", 0),
    ("Heading 2 — XL display", "h2", 1),  # big section titles
    ("Heading 2 — workflow", "h2", 2),
    ("Heading 2 — feature title", "h2", 4),
    ("Heading 2 — gradient text", "h2", 5),
    ("Heading 2 — hero variant", "h2", 6),
    ("Heading 3 — card title L", "h3", 2),
    ("Heading 3 — card title M", "h3", 0),
    ("Heading 3 — stat", "h3", 6),
    ("Heading 4 — meta", "h4", 0),
    ("Heading 4 — footer", "h4", 1),
]
SAMPLE_TEXT = "Pack my box with five dozen liquor jugs."
for name, tag, idx in TYPE_ORDER:
    items = inv["headings"].get(tag, [])
    if idx >= len(items):
        continue
    cls = items[idx]["classes"]
    sample_node = new.new_tag(tag, **{"class": cls})
    sample_node.string = SAMPLE_TEXT
    row = new.new_tag("div", **{"class": "ds-row"})
    label = new.new_tag("span", **{"class": "label"})
    label.string = name
    meta = new.new_tag("span", **{"class": "meta"})
    meta.string = size_label(cls)
    row.append(label)
    row.append(sample_node)
    row.append(meta)
    typo_inner.append(row)

# Paragraphs (top variants)
para_subhead = BeautifulSoup(
    '<div style="margin-top:64px;"><h3 class="ds-title" style="font-size:22px;">Paragraph styles</h3></div>',
    "html.parser",
)
typo_inner.append(para_subhead)
PARA_PICK = [
    (
        "Paragraph — Hero L",
        "hero-fade text-neutral-400 text-base md:text-lg lg:text-xl mb-8 max-w-xl leading-relaxed font-light",
    ),
    (
        "Paragraph — Section L",
        "text-neutral-400 text-base md:text-lg font-light max-w-xl",
    ),
    (
        "Paragraph — Section M",
        "text-neutral-400 text-lg font-light mb-8 max-w-md leading-relaxed",
    ),
    ("Paragraph — Body M", "text-base text-neutral-400 font-light"),
    (
        "Paragraph — Body S",
        "text-sm md:text-base text-neutral-400 font-light leading-relaxed",
    ),
    ("Paragraph — Caption", "text-sm text-neutral-500 leading-relaxed font-light"),
    (
        "Paragraph — Eyebrow",
        "text-sm tracking-[0.2em] uppercase text-neutral-500 font-normal",
    ),
]
for name, cls in PARA_PICK:
    row = new.new_tag("div", **{"class": "ds-row"})
    label = new.new_tag("span", **{"class": "label"})
    label.string = name
    p = new.new_tag("p", **{"class": cls})
    p.string = SAMPLE_TEXT
    meta = new.new_tag("span", **{"class": "meta"})
    meta.string = size_label(cls)
    row.append(label)
    row.append(p)
    row.append(meta)
    typo_inner.append(row)

typo_section.append(typo_inner)
new_body.append(typo_section)

# ── 5. COLORS & SURFACES ───────────────────────────────────────────────────────
COLOR_GROUPS = [
    (
        "Backgrounds (page & sections)",
        [
            ("#000000", "page bottom"),
            ("#050505", "page main"),
            ("#0a0a0a", "section alt"),
            ("#0d0d0d", "card alt"),
            ("#0f0f0f", "section workflow"),
            ("#111111", "card cta"),
            ("#141414", "card subtle"),
            ("#161616", "chip / control"),
            ("#1a1a1a", "card popover"),
        ],
    ),
    (
        "Brand — Orange",
        [
            ("#f97316", "orange-500 / primary"),
            ("#ea580c", "orange-600 / pressed"),
            ("#fb923c", "orange-400 / hover"),
            ("#fed7aa", "orange-200 / decorative"),
        ],
    ),
    (
        "Borders & dividers",
        [
            ("#262626", "neutral-800 / border default"),
            ("#171717", "neutral-900 / divider"),
            ("rgba(38,38,38,0.4)", "neutral-800/40"),
            ("rgba(23,23,23,0.5)", "neutral-900/50"),
            ("rgba(255,255,255,0.05)", "white/5 — glass border"),
            ("rgba(255,255,255,0.1)", "white/10 — glass border"),
            ("rgba(249,115,22,0.3)", "orange-500/30 — accent border"),
        ],
    ),
    (
        "Glass & overlays (with backdrop-blur)",
        [
            ("rgba(23,23,23,0.6)", "neutral-900/60 + blur-md"),
            ("rgba(255,255,255,0.05)", "white/5 — nav pill"),
            ("rgba(249,115,22,0.1)", "orange-500/10 — pill badge"),
        ],
    ),
]
GRADIENTS = [
    (
        "linear-gradient(90deg,#f97316,#ea580c)",
        "Primary CTA · from-orange-500 to-orange-600",
    ),
    (
        "linear-gradient(90deg,#fff,#ffffff99)",
        "Heading gradient · from-white to-white/60",
    ),
    (
        "linear-gradient(180deg,#050505,#0a0a0a)",
        "Section · from-[#050505] to-[#0a0a0a]",
    ),
    (
        "radial-gradient(circle at 30% 30%,#fb923c33,transparent 60%)",
        "Glow · orange-500/20",
    ),
]
colors_section = new.new_tag("section", id="colors", **{"class": "ds-section"})
colors_inner = new.new_tag("div", **{"class": "ds-section-inner"})
colors_inner.append(
    BeautifulSoup(
        '<span class="ds-eyebrow">02</span>'
        '<h2 class="ds-title">Colors &amp; Surfaces</h2>'
        '<p class="ds-lede">All values pulled from the source HTML — including arbitrary hex tokens '
        "baked into class names like <code>bg-[#0a0a0a]</code>.</p>",
        "html.parser",
    )
)
for group_name, swatches in COLOR_GROUPS:
    h = new.new_tag(
        "h3",
        style="font-size:13px;letter-spacing:.12em;text-transform:uppercase;color:#737373;margin:40px 0 16px;font-weight:400;",
    )
    h.string = group_name
    colors_inner.append(h)
    grid = new.new_tag("div", **{"class": "ds-grid cols-4"})
    for color, ctx in swatches:
        sw = new.new_tag("div", **{"class": "ds-swatch"}, style=f"background:{color};")
        tag_node = new.new_tag("span", **{"class": "tag"})
        tag_node.string = color
        ctx_node = new.new_tag("span", **{"class": "ctx"})
        ctx_node.string = ctx
        sw.append(tag_node)
        sw.append(ctx_node)
        grid.append(sw)
    colors_inner.append(grid)

# Gradients
h_grad = new.new_tag(
    "h3",
    style="font-size:13px;letter-spacing:.12em;text-transform:uppercase;color:#737373;margin:40px 0 16px;font-weight:400;",
)
h_grad.string = "Gradients"
colors_inner.append(h_grad)
grad_grid = new.new_tag("div", **{"class": "ds-grid cols-2"})
for grad_css, ctx in GRADIENTS:
    sw = new.new_tag(
        "div",
        **{"class": "ds-swatch"},
        style=f"background:{grad_css};aspect-ratio:2.4;",
    )
    tag_node = new.new_tag("span", **{"class": "tag"})
    tag_node.string = grad_css[:60] + ("…" if len(grad_css) > 60 else "")
    ctx_node = new.new_tag("span", **{"class": "ctx"})
    ctx_node.string = ctx
    sw.append(tag_node)
    sw.append(ctx_node)
    grad_grid.append(sw)
colors_inner.append(grad_grid)

colors_section.append(colors_inner)
new_body.append(colors_section)

# ── 6. UI COMPONENTS ───────────────────────────────────────────────────────────
comp_section = new.new_tag("section", id="components", **{"class": "ds-section"})
comp_inner = new.new_tag("div", **{"class": "ds-section-inner"})
comp_inner.append(
    BeautifulSoup(
        '<span class="ds-eyebrow">03</span>'
        '<h2 class="ds-title">UI Components</h2>'
        '<p class="ds-lede">Each variant uses the exact class signature pulled from the page. '
        "Hover/focus states behave as in the source — driven by the same Tailwind utilities.</p>",
        "html.parser",
    )
)


# P1-C fix: semantic class-signature lookup instead of hardcoded indices.
def find_button_by_classes(buttons, *required, default_label: str = "Action"):
    """First button whose `.classes` contains ALL `required` substrings."""
    for b in buttons:
        cls = b.get("classes", "")
        if all(s in cls for s in required):
            return {"classes": cls, "label": b.get("label", "") or default_label}
    return {"classes": "", "label": default_label}


_b = inv["buttons"]
_primary = find_button_by_classes(
    _b, "gradient-to-r", "from-orange", default_label="Start for free"
)
_secondary = find_button_by_classes(
    _b, "neutral-900/", "border-neutral-800", default_label="View demo"
)
_ghost = find_button_by_classes(_b, "white/5", "white/10", default_label="Get Started")
_white_pill = find_button_by_classes(
    _b, "bg-white", "text-black", default_label="Start Building for Free"
)
_dark_pill = find_button_by_classes(
    _b, "bg-[#11", "rounded-full", default_label="Explore Analytics"
)
_chip_active = find_button_by_classes(
    _b, "bg-orange-500/10", "border-orange-500/30", default_label="All"
)
_chip_idle = find_button_by_classes(
    _b, "bg-[#161616]", "rounded-full", default_label="Active"
)

BUTTON_ROLES = [
    ("Primary CTA", _primary["classes"], _primary["label"]),
    ("Secondary CTA", _secondary["classes"], _secondary["label"]),
    ("Ghost (nav)", _ghost["classes"], _ghost["label"]),
    ("Pill — White solid", _white_pill["classes"], _white_pill["label"]),
    ("Pill — Dark", _dark_pill["classes"], _dark_pill["label"]),
    ("Filter chip — active", _chip_active["classes"], _chip_active["label"]),
    ("Filter chip — idle", _chip_idle["classes"], _chip_idle["label"]),
]
BUTTON_ROLES = [(role, cls, lbl) for (role, cls, lbl) in BUTTON_ROLES if cls]
btn_h = new.new_tag(
    "h3",
    style="font-size:13px;letter-spacing:.12em;text-transform:uppercase;color:#737373;margin:0 0 16px;font-weight:400;",
)
btn_h.string = "Buttons"
comp_inner.append(btn_h)
for role, cls, label in BUTTON_ROLES:
    grid = new.new_tag("div", **{"class": "ds-state-grid"})
    role_node = new.new_tag("span", **{"class": "ds-state-label"})
    role_node.string = role
    btn_wrap = new.new_tag(
        "div", style="display:flex;align-items:center;gap:14px;flex-wrap:wrap;"
    )
    btn = new.new_tag("button", **{"class": cls})
    btn.string = label
    btn_wrap.append(btn)
    # disabled mirror
    btn_dis = new.new_tag(
        "button",
        **{"class": cls + " opacity-50 cursor-not-allowed pointer-events-none"},
    )
    btn_dis.string = label + " (disabled)"
    btn_wrap.append(btn_dis)
    grid.append(role_node)
    grid.append(btn_wrap)
    comp_inner.append(grid)

# Pill badge component (from hero)
pill_h = new.new_tag(
    "h3",
    style="font-size:13px;letter-spacing:.12em;text-transform:uppercase;color:#737373;margin:48px 0 16px;font-weight:400;",
)
pill_h.string = "Pill badges"
comp_inner.append(pill_h)
pill_grid = new.new_tag(
    "div",
    style="display:flex;gap:16px;flex-wrap:wrap;align-items:center;padding:8px 0;",
)
pill_grid.append(
    BeautifulSoup(
        '<div class="hero-fade inline-flex items-center gap-2 px-3 py-1.5 rounded-full border border-orange-500/30 bg-orange-500/10 text-orange-400 text-sm font-normal backdrop-blur-md shadow-[0_0_20px_rgba(249,115,22,0.1)]">'
        '<iconify-icon icon="lucide:wand-2"></iconify-icon><span>Brand · accent</span></div>',
        "html.parser",
    )
)
pill_grid.append(
    BeautifulSoup(
        '<div class="inline-flex items-center gap-2 px-3 py-1.5 rounded-full border border-neutral-800 bg-neutral-900/60 text-neutral-300 text-sm font-normal backdrop-blur-md">'
        '<iconify-icon icon="lucide:layers"></iconify-icon><span>Neutral · meta</span></div>',
        "html.parser",
    )
)
comp_inner.append(pill_grid)

# Cards (extract a real one)
card_h = new.new_tag(
    "h3",
    style="font-size:13px;letter-spacing:.12em;text-transform:uppercase;color:#737373;margin:48px 0 16px;font-weight:400;",
)
card_h.string = "Cards"
comp_inner.append(card_h)
card_grid = new.new_tag("div", **{"class": "ds-grid cols-3"})
# Generic feature card pattern
card_grid.append(
    BeautifulSoup(
        '<div class="border-gradient-card group relative overflow-hidden rounded-2xl bg-[#0a0a0a] border border-neutral-800/60 p-7 transition-all">'
        '<iconify-icon icon="lucide:zap" class="text-orange-500" style="font-size:28px;"></iconify-icon>'
        '<h3 class="text-2xl font-normal text-white mb-2 tracking-tight mt-4 group-hover:text-orange-400 transition-colors">Zero Latency</h3>'
        '<p class="text-base text-neutral-400 font-light">Workflows compiled to V8 isolates and shipped to the edge.</p>'
        "</div>",
        "html.parser",
    )
)
card_grid.append(
    BeautifulSoup(
        '<div class="border-gradient-card group relative overflow-hidden rounded-2xl bg-[#0a0a0a] border border-neutral-800/60 p-7 transition-all">'
        '<iconify-icon icon="lucide:shield-check" class="text-orange-500" style="font-size:28px;"></iconify-icon>'
        '<h3 class="text-2xl font-normal text-white mb-2 tracking-tight mt-4 group-hover:text-orange-400 transition-colors">Enterprise Security</h3>'
        '<p class="text-base text-neutral-400 font-light">SOC 2 Type II controls baked into every workflow execution.</p>'
        "</div>",
        "html.parser",
    )
)
card_grid.append(
    BeautifulSoup(
        '<div class="border-gradient-card group relative overflow-hidden rounded-2xl bg-[#0a0a0a] border border-neutral-800/60 p-7 transition-all">'
        '<iconify-icon icon="lucide:radar" class="text-orange-500" style="font-size:28px;"></iconify-icon>'
        '<h3 class="text-2xl font-normal text-white mb-2 tracking-tight mt-4 group-hover:text-orange-400 transition-colors">Live Observability</h3>'
        '<p class="text-base text-neutral-400 font-light">Trace every node, every retry, every payload — with zero setup.</p>'
        "</div>",
        "html.parser",
    )
)
comp_inner.append(card_grid)

comp_section.append(comp_inner)
new_body.append(comp_section)

# ── 7. LAYOUT & SPACING ────────────────────────────────────────────────────────
layout_section = new.new_tag("section", id="layout", **{"class": "ds-section"})
layout_inner = new.new_tag("div", **{"class": "ds-section-inner"})
layout_inner.append(
    BeautifulSoup(
        '<span class="ds-eyebrow">04</span>'
        '<h2 class="ds-title">Layout &amp; Spacing</h2>'
        '<p class="ds-lede">Container widths, vertical rhythm, and 3 real layout patterns lifted from the source.</p>',
        "html.parser",
    )
)

# Token tables
spacing_html = """
<div class="ds-grid cols-2" style="margin-bottom:48px;">
  <div>
    <h3 style="font-size:13px;letter-spacing:.12em;text-transform:uppercase;color:#737373;margin:0 0 14px;font-weight:400;">Container widths</h3>
    <div class="ds-row"><span class="label">max-w-[1400px]</span><span class="meta">1400 px · hero</span></div>
    <div class="ds-row"><span class="label">max-w-7xl</span><span class="meta">80 rem · sections</span></div>
    <div class="ds-row"><span class="label">max-w-6xl</span><span class="meta">72 rem · features</span></div>
    <div class="ds-row"><span class="label">max-w-5xl</span><span class="meta">64 rem · dashboard</span></div>
    <div class="ds-row"><span class="label">max-w-3xl</span><span class="meta">48 rem · text block</span></div>
    <div class="ds-row"><span class="label">max-w-xl</span><span class="meta">36 rem · subhead</span></div>
  </div>
  <div>
    <h3 style="font-size:13px;letter-spacing:.12em;text-transform:uppercase;color:#737373;margin:0 0 14px;font-weight:400;">Vertical rhythm (sections)</h3>
    <div class="ds-row"><span class="label">py-32</span><span class="meta">128 px / 128 px</span></div>
    <div class="ds-row"><span class="label">pt-32 pb-32</span><span class="meta">128 px (split)</span></div>
    <div class="ds-row"><span class="label">md:py-40</span><span class="meta">160 px @ md+</span></div>
    <div class="ds-row"><span class="label">pt-20 pb-32</span><span class="meta">80 / 128 px · hero</span></div>
    <div class="ds-row"><span class="label">px-6</span><span class="meta">24 px · gutter</span></div>
    <div class="ds-row"><span class="label">px-4</span><span class="meta">16 px · sub-gutter</span></div>
  </div>
</div>
"""
layout_inner.append(BeautifulSoup(spacing_html, "html.parser"))

# Pattern A: hero centered column
pat_a = BeautifulSoup(
    '<div class="ds-card-demo" style="padding:0;overflow:hidden;">'
    '<div class="demo-label" style="padding:14px 16px 0;">Pattern A · centered column · max-w-3xl</div>'
    '<div class="max-w-3xl mx-auto text-center px-6 py-12">'
    '<h3 class="text-3xl font-normal text-white tracking-tight mb-3">Centered hero column</h3>'
    '<p class="text-neutral-400 text-base font-light">Used by Hero and final CTA. Text-center with max-w-3xl on a max-w-[1400px] outer.</p>'
    "</div></div>",
    "html.parser",
)
layout_inner.append(pat_a)
# Pattern B: split title + body grid
pat_b = BeautifulSoup(
    '<div class="ds-card-demo" style="padding:0;overflow:hidden;margin-top:24px;">'
    '<div class="demo-label" style="padding:14px 16px 0;">Pattern B · split title + body · max-w-7xl</div>'
    '<div class="max-w-7xl mx-auto px-6 py-12 grid md:grid-cols-2 gap-12 items-end">'
    '<h3 class="text-4xl md:text-5xl font-normal text-white tracking-tight">Section title<br/>two-line balance.</h3>'
    '<p class="text-neutral-400 text-base md:text-lg font-light">Used in features, workflow, observability — title on the left, lede on the right at md breakpoint.</p>'
    "</div></div>",
    "html.parser",
)
layout_inner.append(pat_b)
# Pattern C: 3-col card grid
pat_c = BeautifulSoup(
    '<div class="ds-card-demo" style="padding:0;overflow:hidden;margin-top:24px;">'
    '<div class="demo-label" style="padding:14px 16px 0;">Pattern C · 3-column card grid · max-w-6xl</div>'
    '<div class="max-w-6xl mx-auto px-6 py-12 grid md:grid-cols-3 gap-6">'
    + "".join(
        [
            '<div class="bg-[#0a0a0a] border border-neutral-800/60 rounded-2xl p-6">'
            '<iconify-icon icon="lucide:'
            + ic
            + '" class="text-orange-500" style="font-size:24px;"></iconify-icon>'
            '<h4 class="text-base font-normal text-white tracking-tight mt-3">'
            + t
            + "</h4>"
            '<p class="text-sm text-neutral-500 leading-relaxed font-light mt-1">'
            + d
            + "</p>"
            "</div>"
            for ic, t, d in [
                ("box", "Modular nodes", "Drag, drop, connect."),
                ("cpu", "Compiled", "V8 isolates at the edge."),
                ("globe-2", "Global", "99.99% uptime SLA."),
            ]
        ]
    )
    + "</div></div>",
    "html.parser",
)
layout_inner.append(pat_c)

layout_section.append(layout_inner)
new_body.append(layout_section)

# ── 8. MOTION & INTERACTION ────────────────────────────────────────────────────
motion_section = new.new_tag("section", id="motion", **{"class": "ds-section"})
motion_inner = new.new_tag("div", **{"class": "ds-section-inner"})
motion_inner.append(
    BeautifulSoup(
        '<span class="ds-eyebrow">05</span>'
        '<h2 class="ds-title">Motion &amp; Interaction</h2>'
        '<p class="ds-lede">All animation classes detected in the page. Live demos use the original keyframes from the source CSS.</p>',
        "html.parser",
    )
)

MOTION_DEMOS = [
    (
        "animate-pulse",
        "Tailwind pulse · used on status dots",
        '<div class="animate-pulse" style="width:80px;height:80px;border-radius:50%;background:radial-gradient(circle,#fb923c,transparent);"></div>',
    ),
    (
        "animate-[pulse_2s_ease-in-out_infinite]",
        "Custom pulse 2s · used on connection markers (×14)",
        '<div class="animate-[pulse_2s_ease-in-out_infinite]" style="width:14px;height:14px;border-radius:50%;background:#f97316;box-shadow:0 0 24px #f97316;"></div>',
    ),
    (
        "animate-ping",
        "Tailwind ping · radar scan",
        '<div style="position:relative;width:14px;height:14px;"><span class="animate-ping" style="position:absolute;inset:0;border-radius:50%;background:#fb923c;opacity:.6;"></span><span style="position:absolute;inset:3px;border-radius:50%;background:#f97316;"></span></div>',
    ),
    (
        "animate-float-slow",
        "Float slow · ambient drift",
        '<iconify-icon icon="lucide:cloud" class="animate-float-slow text-neutral-300" style="font-size:48px;"></iconify-icon>',
    ),
    (
        "animate-float-med",
        "Float medium",
        '<iconify-icon icon="lucide:layers" class="animate-float-med text-orange-500" style="font-size:48px;"></iconify-icon>',
    ),
    (
        "animate-float-fast",
        "Float fast",
        '<iconify-icon icon="lucide:zap" class="animate-float-fast text-white" style="font-size:48px;"></iconify-icon>',
    ),
    (
        "animate-[spin_8s_linear_infinite]",
        "Spin 8s · halo",
        '<div class="animate-[spin_8s_linear_infinite]" style="width:64px;height:64px;border:1px dashed #525252;border-radius:50%;border-top-color:#f97316;"></div>',
    ),
    (
        "animate-infinite-scroll",
        "Infinite scroll · logo strip",
        '<div style="overflow:hidden;width:100%;"><div class="animate-infinite-scroll" style="display:flex;gap:32px;color:#525252;font-size:14px;letter-spacing:.1em;">'
        + " · ".join(
            ["ACME", "VERTEX", "ATLAS", "NORTH", "PRISM", "HALO", "ECHO", "VELA"] * 3
        )
        + "</div></div>",
    ),
    (
        "hero-fade",
        "Hero fade-in (GSAP) · entrance",
        '<div class="hero-fade" style="padding:14px 18px;border-radius:999px;background:#0a0a0a;border:1px solid #262626;color:#e5e5e5;font-size:13px;">Fades up on load</div>',
    ),
    (
        "word-wrapper / word-inner",
        "Word-by-word stagger · GSAP mask reveal",
        '<div style="font-size:24px;color:#fff;font-weight:300;letter-spacing:-.025em;"><span class="word-wrapper" style="display:inline-block;overflow:hidden;"><span class="word-inner" style="display:inline-block;">Stagger </span></span><span class="word-wrapper" style="display:inline-block;overflow:hidden;"><span class="word-inner" style="display:inline-block;">reveal </span></span><span class="word-wrapper" style="display:inline-block;overflow:hidden;"><span class="word-inner" style="display:inline-block;">animation.</span></span></div>',
    ),
    (
        "gs-reveal",
        "Scroll-trigger reveal (GSAP)",
        '<div class="gs-reveal" style="padding:14px 18px;border-radius:14px;background:#0a0a0a;border:1px solid #262626;color:#a3a3a3;font-size:13px;">Triggered when the section enters viewport</div>',
    ),
    (
        "perspective-container + dashboard-plane",
        "3D tilted plane (CSS perspective)",
        '<div class="perspective-container" style="width:200px;"><div class="dashboard-plane border-gradient-surface" style="width:100%;aspect-ratio:16/10;background:linear-gradient(135deg,#0a0a0a,#1a1a1a);border-radius:14px;display:flex;align-items:center;justify-content:center;color:#737373;font-size:11px;">3D dashboard plane</div></div>',
    ),
    (
        "transition-all (button)",
        "200 ms ease default — used by every interactive surface",
        '<button class="px-6 py-2.5 rounded-full bg-gradient-to-r from-orange-500 to-orange-600 text-white text-base font-normal shadow-[0_0_20px_rgba(249,115,22,0.2)] hover:from-orange-400 hover:to-orange-500 border border-orange-400/50 transition-all">Hover me</button>',
    ),
]
demos_grid = new.new_tag("div", **{"class": "ds-grid cols-3"})
for cls, desc, demo_html in MOTION_DEMOS:
    cell = new.new_tag("div", **{"class": "ds-card-demo"})
    label = new.new_tag("div", **{"class": "demo-label"})
    label.string = cls
    desc_el = new.new_tag("div", style="font-size:12px;color:#a3a3a3;font-weight:300;")
    desc_el.string = desc
    frame = new.new_tag("div", **{"class": "motion-frame"})
    frame.append(BeautifulSoup(demo_html, "html.parser"))
    cell.append(label)
    cell.append(desc_el)
    cell.append(frame)
    demos_grid.append(cell)
motion_inner.append(demos_grid)

motion_section.append(motion_inner)
new_body.append(motion_section)

# ── 9. ICONS ───────────────────────────────────────────────────────────────────
icons_section = new.new_tag("section", id="icons", **{"class": "ds-section"})
icons_inner = new.new_tag("div", **{"class": "ds-section-inner"})
icons_inner.append(
    BeautifulSoup(
        '<span class="ds-eyebrow">06</span>'
        '<h2 class="ds-title">Icons</h2>'
        f'<p class="ds-lede">All icons come from the <code>lucide</code> set, served through <code>iconify-icon</code>. '
        f"{inv['icons_total']} usages across {len(inv['icons'])} unique icons. Color inherits from <code>color</code>; size via inline <code>font-size</code> or <code>width</code> attribute.</p>",
        "html.parser",
    )
)

# Sizes row
sizes_grid = new.new_tag(
    "div", **{"class": "ds-grid cols-4"}, style="margin-bottom:32px;"
)
for sz, lbl in [
    (14, "sm · 14"),
    (18, "md · 18 (default)"),
    (28, "lg · 28"),
    (48, "xl · 48"),
]:
    cell = new.new_tag("div", **{"class": "ds-icon-cell"})
    cell.append(
        BeautifulSoup(
            f'<iconify-icon icon="lucide:settings" style="font-size:{sz}px;"></iconify-icon>',
            "html.parser",
        )
    )
    name = new.new_tag("span", **{"class": "name"})
    name.string = lbl
    cell.append(name)
    sizes_grid.append(cell)
icons_inner.append(sizes_grid)

# Color inheritance row
colors_h = new.new_tag(
    "h3",
    style="font-size:13px;letter-spacing:.12em;text-transform:uppercase;color:#737373;margin:8px 0 16px;font-weight:400;",
)
colors_h.string = "Color inheritance"
icons_inner.append(colors_h)
color_row = new.new_tag(
    "div", **{"class": "ds-grid cols-4"}, style="margin-bottom:32px;"
)
for cls, lbl in [
    ("text-white", "white · primary"),
    ("text-neutral-400", "neutral-400 · meta"),
    ("text-orange-500", "orange-500 · brand"),
    ("text-orange-400", "orange-400 · hover"),
]:
    cell = new.new_tag("div", **{"class": "ds-icon-cell"})
    cell.append(
        BeautifulSoup(
            f'<iconify-icon icon="lucide:zap" class="{cls}" style="font-size:32px;"></iconify-icon>',
            "html.parser",
        )
    )
    name = new.new_tag("span", **{"class": "name"})
    name.string = lbl
    cell.append(name)
    color_row.append(cell)
icons_inner.append(color_row)

# Full icon set used
all_h = new.new_tag(
    "h3",
    style="font-size:13px;letter-spacing:.12em;text-transform:uppercase;color:#737373;margin:8px 0 16px;font-weight:400;",
)
all_h.string = f"Icons used in this page ({len(inv['icons'])})"
icons_inner.append(all_h)
all_grid = new.new_tag("div", **{"class": "ds-grid cols-6"})
for icon_name in inv["icons"]:
    cell = new.new_tag("div", **{"class": "ds-icon-cell"})
    cell.append(
        BeautifulSoup(
            f'<iconify-icon icon="{icon_name}"></iconify-icon>', "html.parser"
        )
    )
    short = icon_name.split(":", 1)[-1]
    name = new.new_tag("span", **{"class": "name"})
    name.string = short
    cell.append(name)
    all_grid.append(cell)
icons_inner.append(all_grid)

icons_section.append(icons_inner)
new_body.append(icons_section)

# ── 10. Copy trailing scripts (gsap re-init, etc.) ─────────────────────────────
# Append all <script> from original body that come AFTER all <section> tags
orig_body = soup.body
# Take the very last script blocks (image fallback, etc.) — keep behavior intact
trailing_scripts = orig_body.find_all("script", recursive=False)[-3:]
for s in trailing_scripts:
    new_body.append(deepcopy(s))

# Footer note
footer = BeautifulSoup(
    '<footer style="text-align:center;padding:48px 24px;color:#525252;font-size:12px;letter-spacing:.05em;">'
    'Living design system · extracted from <code style="color:#a3a3a3;">nexusflow-saas.aura.build</code>'
    "</footer>",
    "html.parser",
)
new_body.append(footer)

# ── Write ──────────────────────────────────────────────────────────────────────
OUT.write_text(new.prettify(), encoding="utf-8")
print(f"✅ Wrote {OUT} ({OUT.stat().st_size // 1024} KB)")
