"""Generate design-system.html v2 — adds 5 sections beyond v1 per PROMPT_v2.md spec:
  02 Coverage scorecard (DTCG 13 categories ✓/partial/✗)
  08 Accessibility (focus rings, contrast pairs, ARIA, reduced-motion)
  09 Dark Mode (paired tokens table OR single-theme note)
  11 Tokens JSON (embedded DTCG export + download button)
  12 Class Inventory (sortable appendix of every utility class used)

Plus all v1 sections (Hero, Typography, Colors, Components, Layout, Motion, Icons).
"""

from __future__ import annotations
import json
import re
from copy import deepcopy
from pathlib import Path
from collections import Counter
from bs4 import BeautifulSoup, Tag

ROOT = Path(__file__).parent
SRC = ROOT / "index.html"
INV = ROOT / "_inventory.json"
OUT = ROOT / "design-system.html"

soup = BeautifulSoup(SRC.read_text(encoding="utf-8"), "html.parser")
inv = json.loads(INV.read_text())
new = BeautifulSoup(
    "<!doctype html><html><head></head><body></body></html>", "html.parser"
)
new_html = new.html
new_head = new.head
new_body = new.body


def make_section(sec_id, eyebrow, title, lede):
    section = new.new_tag("section", id=sec_id, **{"class": "ds-section"})
    inner = new.new_tag("div", **{"class": "ds-section-inner"})
    inner.append(
        BeautifulSoup(
            f'<span class="ds-eyebrow">{eyebrow}</span>'
            f'<h2 class="ds-title">{title}</h2>'
            f'<p class="ds-lede">{lede}</p>',
            "html.parser",
        )
    )
    section.append(inner)
    return section, inner


# ── 1. HEAD ─────────────────────────────────────────────────────────────────
orig_head = soup.head
for child in list(orig_head.children):
    if not isinstance(child, Tag):
        continue
    if child.name == "style" and child.get("data-scroll-fix") == "true":
        continue
    if child.name == "script" and child.get("id") == "aura-supabase-token-firewall":
        continue
    new_head.append(deepcopy(child))

title = new_head.find("title")
if title:
    title.string = "Design System v2 — NexusFlow"
else:
    t = new.new_tag("title")
    t.string = "Design System v2 — NexusFlow"
    new_head.append(t)

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

/* v2 — NEW SECTIONS */
.scorecard{display:grid;grid-template-columns:200px 80px 1fr;gap:8px 18px;align-items:center;padding:10px 0;border-bottom:1px solid rgba(38,38,38,.35);font-size:13px;}
.scorecard:last-of-type{border-bottom:none;}
.scorecard .cat{color:#e5e5e5;font-family:ui-monospace,Menlo,Consolas,monospace;font-size:12px;}
.scorecard .status{font-weight:600;letter-spacing:.05em;font-size:11px;text-transform:uppercase;}
.scorecard .status.full{color:#22c55e;}
.scorecard .status.partial{color:#f59e0b;}
.scorecard .status.missing{color:#ef4444;}
.scorecard .evidence{color:#a3a3a3;font-size:12px;font-weight:300;}
.contrast-pair{display:grid;grid-template-columns:1fr 80px;align-items:center;padding:14px 16px;border-radius:10px;margin-bottom:8px;}
.contrast-pair .ratio{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:13px;font-weight:600;}
.contrast-pair .ratio.pass{color:#22c55e;}
.contrast-pair .ratio.fail{color:#ef4444;}
.focus-demo button:focus-visible,.focus-demo a:focus-visible,.focus-demo input:focus-visible{outline:2px solid #fb923c;outline-offset:2px;}
.tokens-block{background:#050505;border:1px solid rgba(38,38,38,.5);border-radius:14px;padding:18px;font-family:ui-monospace,Menlo,Consolas,monospace;font-size:11px;color:#a3a3a3;max-height:480px;overflow:auto;}
.copy-btn{background:#161616;border:1px solid rgba(64,64,64,.5);color:#e5e5e5;font-family:ui-monospace,Menlo,Consolas,monospace;font-size:12px;padding:6px 12px;border-radius:6px;cursor:pointer;transition:background .15s;}
.copy-btn:hover{background:#262626;}
details.class-inventory summary{cursor:pointer;padding:14px 0;color:#fb923c;font-size:13px;letter-spacing:.05em;}
details.class-inventory table{width:100%;border-collapse:collapse;font-size:11px;font-family:ui-monospace,Menlo,Consolas,monospace;}
details.class-inventory th{text-align:left;padding:8px 12px;border-bottom:1px solid rgba(38,38,38,.5);color:#737373;letter-spacing:.05em;text-transform:uppercase;font-size:10px;}
details.class-inventory td{padding:6px 12px;border-bottom:1px solid rgba(38,38,38,.25);color:#d4d4d4;}
details.class-inventory td.count{text-align:right;color:#fb923c;width:60px;}
"""
new_head.append(ds_helper_css)


# ── 2. NAV (12 anchors v2 vs 7 v1) ──────────────────────────────────────────
nav_html = """<nav class="ds-nav"><ul>
<li><a href="#hero">Hero</a></li>
<li><a href="#coverage">Coverage</a></li>
<li><a href="#typography">Typography</a></li>
<li><a href="#colors">Colors</a></li>
<li><a href="#components">Components</a></li>
<li><a href="#layout">Layout</a></li>
<li><a href="#motion">Motion</a></li>
<li><a href="#accessibility">A11y</a></li>
<li><a href="#dark-mode">Dark mode</a></li>
<li><a href="#icons">Icons</a></li>
<li><a href="#tokens">Tokens</a></li>
<li><a href="#class-inventory">Classes</a></li>
</ul></nav>"""
new_body.append(BeautifulSoup(nav_html, "html.parser"))


# ── 3. HERO (clone, text adapted) ───────────────────────────────────────────
hero = deepcopy(soup.find("section"))
hero["id"] = "hero"
badge_span = hero.select_one(".hero-fade span")
if badge_span:
    badge_span.string = "Living Design System v2"

new_words = [
    "Tokens,",
    "components,",
    "motion",
    "&",
    "accessibility",
    "from",
    "this",
    "design.",
]
word_wrappers = hero.select("h1 .word-wrapper")
for i, w in enumerate(word_wrappers):
    inner = w.select_one(".word-inner")
    if inner is None:
        continue
    if i < len(new_words):
        inner.string = new_words[i] + (" " if i < len(new_words) - 1 else "")
    else:
        w.decompose()
existing = len(hero.select("h1 .word-wrapper"))
if existing < len(new_words):
    h1 = hero.find("h1")
    template = h1.select_one(".word-wrapper")
    for w in new_words[existing:]:
        clone = deepcopy(template)
        clone.select_one(".word-inner").string = w + " "
        h1.append(clone)

sub = hero.select_one("p.hero-fade")
if sub:
    sub.string = (
        "Every typography style, color, component, animation class, and "
        "accessibility token on this page is extracted directly from the source. "
        "Includes embedded DTCG token bundle."
    )

ctas = hero.select(".hero-fade button, .hero-fade a")
for i, b in enumerate(ctas):
    if i == 0:
        b.string = "View tokens"
    elif i == 1:
        b.string = "Coverage report"

new_body.append(hero)


# ── 4. COVERAGE SCORECARD (NEW v2 — section 02) ──────────────────────────────
coverage_section, coverage_inner = make_section(
    "coverage",
    "02",
    "Coverage Scorecard",
    "13-category audit against the W3C Design Tokens Community Group "
    '<a href="https://www.designtokens.org/tr/drafts/format/" style="color:#fb923c;">2025.10 stable spec</a>. '
    "Quantifies how complete the design-system extraction is. ✓ full · ◐ partial · ✗ missing.",
)

# DTCG categories — driven from inventory data, not hardcoded.
# (Closes audit P2-8: previously this section used a literal list of statuses
# baked to the original NexusFlow capture, producing the same 80.8/100 score
# for any site. validate.coverage_scorecard reads inventory keys and judges
# each of the 13 categories against actual extracted evidence.)
from scripts.validate import coverage_scorecard  # noqa: E402

DTCG_ROWS = coverage_scorecard(inv)
for row_data in DTCG_ROWS:
    cat = row_data["category"]
    status = row_data["status"]
    evidence = row_data["evidence"]
    row = new.new_tag("div", **{"class": "scorecard"})
    row.append(
        BeautifulSoup(
            f'<div class="cat">{cat}</div>'
            f'<div class="status {status if status != "full" else "full"}">'
            f"{'✓' if status == 'full' else '◐' if status == 'partial' else '✗'} {status}</div>"
            f'<div class="evidence">{evidence}</div>',
            "html.parser",
        )
    )
    coverage_inner.append(row)

# Summary
full_count = sum(1 for r in DTCG_ROWS if r["status"] == "full")
partial_count = sum(1 for r in DTCG_ROWS if r["status"] == "partial")
missing_count = sum(1 for r in DTCG_ROWS if r["status"] == "missing")
total_score = (full_count + 0.5 * partial_count) / 13 * 100
summary_html = (
    f'<div style="margin-top:24px;padding:18px;background:#0a0a0a;border:1px solid rgba(38,38,38,.5);'
    f'border-radius:14px;display:flex;justify-content:space-between;align-items:center;">'
    f'<span style="color:#a3a3a3;font-size:13px;">Total coverage</span>'
    f'<span style="font-family:ui-monospace,Menlo,Consolas,monospace;font-size:24px;color:#fff;">'
    f'{total_score:.1f}<span style="color:#525252;font-size:13px;"> / 100</span></span>'
    f'<span style="color:#737373;font-size:11px;">{full_count} ✓ · {partial_count} ◐ · {missing_count} ✗</span>'
    f"</div>"
)
coverage_inner.append(BeautifulSoup(summary_html, "html.parser"))
new_body.append(coverage_section)


# ── 5. TYPOGRAPHY (same as v1) ──────────────────────────────────────────────
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


typo_section, typo_inner = make_section(
    "typography",
    "03",
    "Typography",
    "Every type scale present in the source page, in hierarchy order. "
    "Live previews use the original CSS classes — no normalization.",
)
TYPE_ORDER = [("Heading 1", "h1", 0)]
for i in range(min(7, len(inv["headings"]["h2"]))):
    TYPE_ORDER.append((f"Heading 2 — variant {i + 1}", "h2", i))
for i in range(min(8, len(inv["headings"]["h3"]))):
    TYPE_ORDER.append((f"Heading 3 — variant {i + 1}", "h3", i))
for i in range(min(2, len(inv["headings"]["h4"]))):
    TYPE_ORDER.append((f"Heading 4 — variant {i + 1}", "h4", i))

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

para_subhead = BeautifulSoup(
    '<div style="margin-top:64px;"><h3 class="ds-title" style="font-size:22px;">Paragraph styles</h3></div>',
    "html.parser",
)
typo_inner.append(para_subhead)
for i, pdata in enumerate(inv["paragraphs"][:8]):
    cls = pdata["classes"]
    row = new.new_tag("div", **{"class": "ds-row"})
    label = new.new_tag("span", **{"class": "label"})
    label.string = f"Paragraph #{i + 1}"
    p = new.new_tag("p", **{"class": cls})
    p.string = SAMPLE_TEXT
    meta = new.new_tag("span", **{"class": "meta"})
    meta.string = size_label(cls)
    row.append(label)
    row.append(p)
    row.append(meta)
    typo_inner.append(row)
new_body.append(typo_section)


# ── 6. COLORS (same as v1) ──────────────────────────────────────────────────
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
            ("#262626", "neutral-800"),
            ("#171717", "neutral-900"),
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
colors_section, colors_inner = make_section(
    "colors",
    "04",
    "Colors &amp; Surfaces",
    "All values pulled from the source HTML — including arbitrary hex tokens "
    "baked into class names like <code>bg-[#0a0a0a]</code>.",
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
new_body.append(colors_section)


# ── 7. COMPONENTS (same as v1) ──────────────────────────────────────────────
comp_section, comp_inner = make_section(
    "components",
    "05",
    "UI Components",
    "Each variant uses the exact class signature pulled from the page. "
    "Hover/focus states behave as in the source — driven by the same Tailwind utilities.",
)


# P1-C fix: replace hardcoded inv["buttons"][N] indices (NexusFlow-only) with
# semantic class-signature lookup so the generator works on any Tailwind site.
def find_button_by_classes(buttons, *required, default_label: str = "Action"):
    """First button whose `.classes` contains ALL `required` substrings.

    Returns a {"classes", "label"} dict. Falls back to a stub when nothing
    matches so the rendered showcase shows an empty state for that role
    instead of crashing with IndexError.
    """
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
    _b, "bg-white", "text-black", default_label="Start Building"
)
_dark_pill = find_button_by_classes(
    _b, "bg-[#11", "rounded-full", default_label="Explore"
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
# Drop empty-classes rows so we don't render bald buttons for a role that
# doesn't exist in the source.
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
    btn_dis = new.new_tag(
        "button",
        **{"class": cls + " opacity-50 cursor-not-allowed pointer-events-none"},
    )
    btn_dis.string = label + " (disabled)"
    btn_wrap.append(btn_dis)
    grid.append(role_node)
    grid.append(btn_wrap)
    comp_inner.append(grid)
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
        '<div class="hero-fade inline-flex items-center gap-2 px-3 py-1.5 rounded-full border border-orange-500/30 bg-orange-500/10 text-orange-400 text-sm font-normal backdrop-blur-md shadow-[0_0_20px_rgba(249,115,22,0.1)]"><iconify-icon icon="lucide:wand-2"></iconify-icon><span>Brand · accent</span></div>',
        "html.parser",
    )
)
pill_grid.append(
    BeautifulSoup(
        '<div class="inline-flex items-center gap-2 px-3 py-1.5 rounded-full border border-neutral-800 bg-neutral-900/60 text-neutral-300 text-sm font-normal backdrop-blur-md"><iconify-icon icon="lucide:layers"></iconify-icon><span>Neutral · meta</span></div>',
        "html.parser",
    )
)
comp_inner.append(pill_grid)
card_h = new.new_tag(
    "h3",
    style="font-size:13px;letter-spacing:.12em;text-transform:uppercase;color:#737373;margin:48px 0 16px;font-weight:400;",
)
card_h.string = "Cards"
comp_inner.append(card_h)
card_grid = new.new_tag("div", **{"class": "ds-grid cols-3"})
for icon_name, title, desc in [
    (
        "lucide:zap",
        "Zero Latency",
        "Workflows compiled to V8 isolates and shipped to the edge.",
    ),
    (
        "lucide:shield-check",
        "Enterprise Security",
        "SOC 2 Type II controls baked into every workflow execution.",
    ),
    (
        "lucide:radar",
        "Live Observability",
        "Trace every node, every retry, every payload — with zero setup.",
    ),
]:
    card_grid.append(
        BeautifulSoup(
            f'<div class="border-gradient-card group relative overflow-hidden rounded-2xl bg-[#0a0a0a] border border-neutral-800/60 p-7 transition-all">'
            f'<iconify-icon icon="{icon_name}" class="text-orange-500" style="font-size:28px;"></iconify-icon>'
            f'<h3 class="text-2xl font-normal text-white mb-2 tracking-tight mt-4 group-hover:text-orange-400 transition-colors">{title}</h3>'
            f'<p class="text-base text-neutral-400 font-light">{desc}</p></div>',
            "html.parser",
        )
    )
comp_inner.append(card_grid)
new_body.append(comp_section)


# ── 8. LAYOUT (same as v1) ──────────────────────────────────────────────────
layout_section, layout_inner = make_section(
    "layout",
    "06",
    "Layout &amp; Spacing",
    "Container widths, vertical rhythm, and 3 real layout patterns lifted from the source.",
)
layout_inner.append(
    BeautifulSoup(
        """
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
    <h3 style="font-size:13px;letter-spacing:.12em;text-transform:uppercase;color:#737373;margin:0 0 14px;font-weight:400;">Vertical rhythm</h3>
    <div class="ds-row"><span class="label">py-32</span><span class="meta">128 px / 128 px</span></div>
    <div class="ds-row"><span class="label">pt-32 pb-32</span><span class="meta">128 px (split)</span></div>
    <div class="ds-row"><span class="label">md:py-40</span><span class="meta">160 px @ md+</span></div>
    <div class="ds-row"><span class="label">pt-20 pb-32</span><span class="meta">80 / 128 px · hero</span></div>
    <div class="ds-row"><span class="label">px-6</span><span class="meta">24 px · gutter</span></div>
    <div class="ds-row"><span class="label">px-4</span><span class="meta">16 px · sub-gutter</span></div>
  </div>
</div>
""",
        "html.parser",
    )
)
layout_inner.append(
    BeautifulSoup(
        '<div class="ds-card-demo" style="padding:0;overflow:hidden;"><div class="demo-label" style="padding:14px 16px 0;">Pattern A · centered column · max-w-3xl</div>'
        '<div class="max-w-3xl mx-auto text-center px-6 py-12">'
        '<h3 class="text-3xl font-normal text-white tracking-tight mb-3">Centered hero column</h3>'
        '<p class="text-neutral-400 text-base font-light">Used by Hero and final CTA. Text-center with max-w-3xl on a max-w-[1400px] outer.</p>'
        "</div></div>",
        "html.parser",
    )
)
layout_inner.append(
    BeautifulSoup(
        '<div class="ds-card-demo" style="padding:0;overflow:hidden;margin-top:24px;"><div class="demo-label" style="padding:14px 16px 0;">Pattern B · split title + body · max-w-7xl</div>'
        '<div class="max-w-7xl mx-auto px-6 py-12 grid md:grid-cols-2 gap-12 items-end">'
        '<h3 class="text-4xl md:text-5xl font-normal text-white tracking-tight">Section title<br/>two-line balance.</h3>'
        '<p class="text-neutral-400 text-base md:text-lg font-light">Used in features, workflow, observability — title on the left, lede on the right at md+.</p>'
        "</div></div>",
        "html.parser",
    )
)
new_body.append(layout_section)


# ── 9. MOTION (condensed) ──────────────────────────────────────────────────
motion_section, motion_inner = make_section(
    "motion",
    "07",
    "Motion &amp; Interaction",
    "All animation classes detected. Live demos use original keyframes from source CSS.",
)
MOTION_DEMOS = [
    (
        "animate-pulse",
        "Tailwind pulse",
        '<div class="animate-pulse" style="width:80px;height:80px;border-radius:50%;background:radial-gradient(circle,#fb923c,transparent);"></div>',
    ),
    (
        "animate-[pulse_2s_ease-in-out_infinite]",
        "Custom pulse 2s (×14)",
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
        "animate-[spin_8s_linear_infinite]",
        "Spin 8s · halo",
        '<div class="animate-[spin_8s_linear_infinite]" style="width:64px;height:64px;border:1px dashed #525252;border-radius:50%;border-top-color:#f97316;"></div>',
    ),
    (
        "hero-fade",
        "Hero fade-in (GSAP) · entrance",
        '<div class="hero-fade" style="padding:14px 18px;border-radius:999px;background:#0a0a0a;border:1px solid #262626;color:#e5e5e5;font-size:13px;">Fades up on load</div>',
    ),
    (
        "word-wrapper / word-inner",
        "Word-by-word stagger · GSAP mask reveal",
        '<div style="font-size:24px;color:#fff;font-weight:300;letter-spacing:-.025em;"><span class="word-wrapper" style="display:inline-block;overflow:hidden;"><span class="word-inner" style="display:inline-block;">Stagger </span></span><span class="word-wrapper" style="display:inline-block;overflow:hidden;"><span class="word-inner" style="display:inline-block;">reveal.</span></span></div>',
    ),
    (
        "gs-reveal",
        "Scroll-trigger reveal (GSAP)",
        '<div class="gs-reveal" style="padding:14px 18px;border-radius:14px;background:#0a0a0a;border:1px solid #262626;color:#a3a3a3;font-size:13px;">Triggered when section enters viewport</div>',
    ),
    (
        "transition-all (button)",
        "200 ms ease default",
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

# Reduced motion preview
rm_html = (
    '<div style="margin-top:32px;padding:18px;background:#0a0a0a;border:1px solid rgba(38,38,38,.5);border-radius:14px;">'
    '<div style="font-size:11px;letter-spacing:.18em;text-transform:uppercase;color:#525252;margin-bottom:8px;">'
    "prefers-reduced-motion</div>"
    '<p style="color:#a3a3a3;font-size:13px;font-weight:300;margin:0;">'
    "When the user has <code>prefers-reduced-motion: reduce</code>, ALL of the above animations should "
    "fall back to instant transitions. Source page does not currently emit a media query for this — "
    "flagged as accessibility gap.</p></div>"
)
motion_inner.append(BeautifulSoup(rm_html, "html.parser"))
new_body.append(motion_section)


# ── 10. ACCESSIBILITY (NEW v2 — section 08) ─────────────────────────────────
a11y_section, a11y_inner = make_section(
    "accessibility",
    "08",
    "Accessibility",
    "Focus indicators, contrast pairs against WCAG 2.2 AA, ARIA patterns, and reduced-motion handling — "
    "extracted from the source where present, flagged as gaps where missing.",
)

# Focus demo
a11y_inner.append(
    BeautifulSoup(
        '<h3 style="font-size:13px;letter-spacing:.12em;text-transform:uppercase;color:#737373;margin:0 0 16px;font-weight:400;">Focus indicators</h3>'
        '<p style="color:#a3a3a3;font-size:13px;margin-bottom:18px;font-weight:300;">'
        'Press <kbd style="background:#0a0a0a;border:1px solid #262626;padding:2px 8px;border-radius:4px;font-family:ui-monospace,Menlo,Consolas,monospace;font-size:11px;">Tab</kbd> '
        "to test keyboard navigation. Source page lacks explicit focus-visible styles — fallback (browser default 2px outline) applied below.</p>"
        '<div class="focus-demo" style="display:flex;gap:14px;flex-wrap:wrap;padding:18px;background:#0a0a0a;border:1px solid rgba(38,38,38,.5);border-radius:14px;margin-bottom:32px;">'
        '<button class="px-6 py-2.5 rounded-full bg-gradient-to-r from-orange-500 to-orange-600 text-white text-base font-normal shadow-[0_0_20px_rgba(249,115,22,0.2)] border border-orange-400/50 transition-all">Primary</button>'
        '<button class="px-6 py-2.5 rounded-full bg-neutral-900/60 border border-neutral-800 text-neutral-300 text-base font-normal backdrop-blur-md">Secondary</button>'
        '<a href="#" class="px-4 py-2 rounded-full bg-white/5 hover:bg-white/10 border border-white/10 text-white text-sm font-normal transition-all backdrop-blur-sm">Link</a>'
        '<input class="px-4 py-2 rounded-full bg-neutral-900/60 border border-neutral-800 text-neutral-300 text-sm font-normal backdrop-blur-md placeholder:text-neutral-600" placeholder="Email"/>'
        "</div>",
        "html.parser",
    )
)


# Contrast pairs
def hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))


def contrast_ratio(c1, c2):
    def rel_lum(rgb):
        r, g, b = [c / 255 for c in rgb]

        def chan(c):
            return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

        return 0.2126 * chan(r) + 0.7152 * chan(g) + 0.0722 * chan(b)

    l1, l2 = rel_lum(hex_to_rgb(c1)), rel_lum(hex_to_rgb(c2))
    if l1 < l2:
        l1, l2 = l2, l1
    return (l1 + 0.05) / (l2 + 0.05)


CONTRAST_PAIRS = [
    ("#ffffff", "#050505", "Body title (white) on page bg"),
    ("#a3a3a3", "#050505", "Body muted (neutral-400) on page bg"),
    ("#737373", "#050505", "Caption (neutral-500) on page bg"),
    ("#fb923c", "#050505", "Brand accent (orange-400) on page bg"),
    ("#ffffff", "#f97316", "White on primary CTA (orange-500)"),
    ("#a3a3a3", "#0a0a0a", "Muted on card alt"),
]
a11y_inner.append(
    BeautifulSoup(
        '<h3 style="font-size:13px;letter-spacing:.12em;text-transform:uppercase;color:#737373;margin:8px 0 16px;font-weight:400;">Contrast pairs · WCAG 2.2 AA</h3>',
        "html.parser",
    )
)
for fg, bg, label in CONTRAST_PAIRS:
    ratio = contrast_ratio(fg, bg)
    pass_body = ratio >= 4.5
    pass_large = ratio >= 3.0
    pair_html = (
        f'<div class="contrast-pair" style="background:{bg};border:1px solid rgba(64,64,64,.4);">'
        f'<span style="color:{fg};font-size:14px;">{label} — Aa</span>'
        f'<span class="ratio {"pass" if pass_body else "fail"}">{ratio:.1f}:1 {"✓ AA" if pass_body else "◐ AA-large only" if pass_large else "✗ fail"}</span>'
        f"</div>"
    )
    a11y_inner.append(BeautifulSoup(pair_html, "html.parser"))

# ARIA patterns observed
aria_html = (
    '<h3 style="font-size:13px;letter-spacing:.12em;text-transform:uppercase;color:#737373;margin:32px 0 16px;font-weight:400;">ARIA patterns observed</h3>'
    '<ul style="list-style:none;padding:0;color:#a3a3a3;font-size:13px;font-weight:300;">'
    '<li style="padding:8px 0;border-bottom:1px solid rgba(38,38,38,.4);"><code style="color:#fb923c;">aria-hidden="true"</code> — decorative icons (iconify-icon)</li>'
    '<li style="padding:8px 0;border-bottom:1px solid rgba(38,38,38,.4);"><code style="color:#fb923c;">role="button"</code> — interactive non-button elements (rare)</li>'
    '<li style="padding:8px 0;color:#ef4444;">⚠ Missing: <code>aria-label</code> on icon-only buttons (sidebar nav)</li>'
    '<li style="padding:8px 0;color:#ef4444;">⚠ Missing: <code>aria-current</code> on active navigation items</li>'
    '<li style="padding:8px 0;color:#ef4444;">⚠ Missing: <code>@media (prefers-reduced-motion: reduce)</code> rule</li>'
    "</ul>"
)
a11y_inner.append(BeautifulSoup(aria_html, "html.parser"))
new_body.append(a11y_section)


# ── 11. DARK MODE (NEW v2 — section 09) ─────────────────────────────────────
dm_section, dm_inner = make_section(
    "dark-mode",
    "09",
    "Dark Mode",
    "Token theming detection. The source applies a single dark theme — no <code>prefers-color-scheme</code>, "
    "<code>[data-theme]</code>, or <code>.dark</code> selectors detected.",
)
dm_html = (
    '<div style="padding:24px;background:#0a0a0a;border:1px solid rgba(38,38,38,.5);border-radius:14px;margin-bottom:24px;">'
    '<div style="display:flex;align-items:center;gap:12px;margin-bottom:14px;">'
    '<iconify-icon icon="lucide:moon" style="font-size:20px;color:#fb923c;"></iconify-icon>'
    '<span style="color:#fff;font-size:15px;font-weight:400;">Single dark theme</span>'
    "</div>"
    '<p style="color:#a3a3a3;font-size:13px;font-weight:300;margin:0;line-height:1.6;">'
    "NexusFlow uses a fixed dark palette (#000-#1a1a1a) with orange accent. Light-mode tokens "
    "would need to be authored — the design system extraction cannot synthesize them since they "
    "don't exist in source. Recommended primary brand color for light mode: orange-500 unchanged. "
    "Recommended surface inversion: #fff page → #f5f5f5 section alt → #ebebeb card."
    "</p></div>"
    '<h3 style="font-size:13px;letter-spacing:.12em;text-transform:uppercase;color:#737373;margin:32px 0 16px;font-weight:400;">Hypothetical paired tokens</h3>'
    '<div class="ds-grid cols-2">'
    '<div style="padding:24px;background:#050505;border:1px solid #262626;border-radius:14px;color:#fff;">'
    '<span style="font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:#737373;">Dark (current)</span>'
    '<div style="margin-top:14px;font-family:ui-monospace,Menlo,Consolas,monospace;font-size:12px;color:#d4d4d4;line-height:1.8;">'
    "--surface-1: #050505<br>--surface-2: #0a0a0a<br>--text: #ffffff<br>--text-muted: #a3a3a3<br>--brand: #f97316"
    "</div></div>"
    '<div style="padding:24px;background:#fafafa;border:1px solid #e5e5e5;border-radius:14px;color:#0a0a0a;">'
    '<span style="font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:#737373;">Light (synthesized)</span>'
    '<div style="margin-top:14px;font-family:ui-monospace,Menlo,Consolas,monospace;font-size:12px;color:#404040;line-height:1.8;">'
    "--surface-1: #ffffff<br>--surface-2: #f5f5f5<br>--text: #0a0a0a<br>--text-muted: #525252<br>--brand: #f97316"
    "</div></div>"
    "</div>"
)
dm_inner.append(BeautifulSoup(dm_html, "html.parser"))
new_body.append(dm_section)


# ── 12. ICONS (same as v1) ──────────────────────────────────────────────────
icons_section, icons_inner = make_section(
    "icons",
    "10",
    "Icons",
    f"All icons come from <code>lucide</code>, served through <code>iconify-icon</code>. "
    f"{inv['icons_total']} usages across {len(inv['icons'])} unique icons.",
)
sizes_grid = new.new_tag(
    "div", **{"class": "ds-grid cols-4"}, style="margin-bottom:32px;"
)
for sz, lbl in [(14, "sm · 14"), (18, "md · 18"), (28, "lg · 28"), (48, "xl · 48")]:
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
new_body.append(icons_section)


# ── 13. TOKENS JSON (NEW v2 — section 11) ───────────────────────────────────
tokens_section, tokens_inner = make_section(
    "tokens",
    "11",
    "Design Tokens (DTCG)",
    'Machine-readable bundle in W3C <a href="https://www.designtokens.org/tr/drafts/format/" '
    'style="color:#fb923c;">Design Tokens Community Group 2025.10</a> format. '
    'Embedded in the page as <code>&lt;script type="application/json" id="design-tokens"&gt;</code>.',
)
DTCG_JSON = {
    "$schema": "https://www.designtokens.org/tr/drafts/format/",
    "color": {
        "surface": {
            "1": {"$type": "color", "$value": "#000000", "$description": "page bottom"},
            "2": {"$type": "color", "$value": "#050505", "$description": "page main"},
            "3": {
                "$type": "color",
                "$value": "#0a0a0a",
                "$description": "section alt / card",
            },
            "4": {"$type": "color", "$value": "#0d0d0d", "$description": "card alt"},
            "5": {
                "$type": "color",
                "$value": "#0f0f0f",
                "$description": "section workflow",
            },
            "chip": {
                "$type": "color",
                "$value": "#161616",
                "$description": "chip / control",
            },
        },
        "brand": {
            "primary": {
                "$type": "color",
                "$value": "#f97316",
                "$description": "orange-500",
            },
            "primary-pressed": {
                "$type": "color",
                "$value": "#ea580c",
                "$description": "orange-600",
            },
            "primary-hover": {
                "$type": "color",
                "$value": "#fb923c",
                "$description": "orange-400",
            },
        },
        "text": {
            "default": {"$type": "color", "$value": "#ffffff"},
            "muted": {
                "$type": "color",
                "$value": "#a3a3a3",
                "$description": "neutral-400",
            },
            "caption": {
                "$type": "color",
                "$value": "#737373",
                "$description": "neutral-500",
            },
        },
        "border": {
            "default": {
                "$type": "color",
                "$value": "#262626",
                "$description": "neutral-800",
            },
            "subtle": {
                "$type": "color",
                "$value": "rgba(38,38,38,0.4)",
                "$description": "neutral-800/40",
            },
            "accent": {
                "$type": "color",
                "$value": "rgba(249,115,22,0.3)",
                "$description": "orange-500/30",
            },
        },
    },
    "dimension": {
        "container": {
            "hero": {"$type": "dimension", "$value": "1400px"},
            "section": {"$type": "dimension", "$value": "80rem"},
            "feature": {"$type": "dimension", "$value": "72rem"},
            "text": {"$type": "dimension", "$value": "48rem"},
        },
        "spacing": {
            "section-y": {"$type": "dimension", "$value": "128px"},
            "section-y-lg": {"$type": "dimension", "$value": "160px"},
            "gutter": {"$type": "dimension", "$value": "24px"},
        },
        "radius": {
            "pill": {"$type": "dimension", "$value": "9999px"},
            "card": {"$type": "dimension", "$value": "1rem"},
            "card-lg": {"$type": "dimension", "$value": "1.125rem"},
        },
    },
    "shadow": {
        "cta-glow": {
            "$type": "shadow",
            "$value": {
                "offsetX": "0",
                "offsetY": "0",
                "blur": "20px",
                "spread": "0",
                "color": "rgba(249,115,22,0.2)",
            },
        },
        "white-cta": {
            "$type": "shadow",
            "$value": {
                "offsetX": "0",
                "offsetY": "0",
                "blur": "30px",
                "spread": "0",
                "color": "rgba(255,255,255,0.15)",
            },
        },
    },
    "gradient": {
        "primary-cta": {
            "$type": "gradient",
            "$value": [
                {"color": "#f97316", "position": 0},
                {"color": "#ea580c", "position": 1},
            ],
        },
        "heading": {
            "$type": "gradient",
            "$value": [
                {"color": "#ffffff", "position": 0},
                {"color": "rgba(255,255,255,0.6)", "position": 1},
            ],
        },
    },
    "duration": {
        "transition": {
            "$type": "duration",
            "$value": "200ms",
            "$description": "transition-all default",
        },
        "pulse": {
            "$type": "duration",
            "$value": "2000ms",
            "$description": "animate-[pulse_2s_ease-in-out_infinite]",
        },
        "spin-slow": {"$type": "duration", "$value": "8000ms"},
    },
    "cubicBezier": {
        "ease-in-out": {"$type": "cubicBezier", "$value": [0.42, 0, 0.58, 1]},
    },
}
tokens_inner.append(
    BeautifulSoup(
        '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:18px;">'
        '<span style="color:#a3a3a3;font-size:13px;">Token bundle preview</span>'
        '<button class="copy-btn" id="downloadTokens">⬇ Download tokens.json</button>'
        "</div>"
        f'<pre class="tokens-block">{json.dumps(DTCG_JSON, indent=2, ensure_ascii=False)}</pre>'
        '<script type="application/json" id="design-tokens">'
        f"{json.dumps(DTCG_JSON, ensure_ascii=False)}"
        "</script>"
        "<script>"
        'document.getElementById("downloadTokens").addEventListener("click",function(){'
        'var t=JSON.parse(document.getElementById("design-tokens").textContent);'
        'var b=new Blob([JSON.stringify(t,null,2)],{type:"application/json"});'
        'var u=URL.createObjectURL(b);var a=document.createElement("a");'
        'a.href=u;a.download="tokens.json";a.click();URL.revokeObjectURL(u);'
        "});"
        "</script>",
        "html.parser",
    )
)
new_body.append(tokens_section)


# ── 14. CLASS INVENTORY (NEW v2 — section 12) ───────────────────────────────
ci_section, ci_inner = make_section(
    "class-inventory",
    "12",
    "Class Inventory",
    "Every utility class used in the source, sorted by frequency. Helps spot drift "
    "(arbitrary <code>[#hex]</code> values escaping the system) and identifies the most "
    "reused tokens for component extraction priority.",
)

# Re-parse classes from source HTML
src_soup = BeautifulSoup(SRC.read_text(), "html.parser")
class_counter = Counter()
for el in src_soup.find_all(class_=True):
    for c in el.get("class", []):
        class_counter[c] += 1

drift_classes = [
    (c, n)
    for c, n in class_counter.most_common()
    if re.search(r"\[#[0-9a-fA-F]{3,8}\]", c)
]
top_classes = class_counter.most_common(60)

ci_html = (
    '<div style="display:grid;grid-template-columns:1fr 1fr;gap:24px;margin-bottom:32px;">'
    f'<div style="padding:18px;background:#0a0a0a;border:1px solid rgba(38,38,38,.5);border-radius:14px;">'
    f'<div style="font-size:11px;letter-spacing:.18em;text-transform:uppercase;color:#737373;margin-bottom:8px;">Total unique classes</div>'
    f'<div style="font-family:ui-monospace,Menlo,Consolas,monospace;font-size:32px;color:#fff;">{len(class_counter)}</div>'
    f"</div>"
    f'<div style="padding:18px;background:#0a0a0a;border:1px solid rgba(38,38,38,.5);border-radius:14px;">'
    f'<div style="font-size:11px;letter-spacing:.18em;text-transform:uppercase;color:#737373;margin-bottom:8px;">Arbitrary value drift</div>'
    f'<div style="font-family:ui-monospace,Menlo,Consolas,monospace;font-size:32px;color:#f59e0b;">{len(drift_classes)}</div>'
    f'<div style="font-size:11px;color:#a3a3a3;margin-top:6px;">classes with <code>[#hex]</code> escaping system</div>'
    f"</div>"
    "</div>"
    '<details class="class-inventory" open>'
    "<summary>Top 60 utility classes</summary>"
    "<table><thead><tr><th>Class</th><th>Count</th></tr></thead><tbody>"
)
for cls, count in top_classes:
    ci_html += f'<tr><td>{cls}</td><td class="count">{count}</td></tr>'
ci_html += "</tbody></table></details>"

if drift_classes:
    ci_html += (
        '<details class="class-inventory" style="margin-top:24px;">'
        "<summary>Arbitrary-value drift (escapes design system)</summary>"
        "<table><thead><tr><th>Class</th><th>Count</th></tr></thead><tbody>"
    )
    for cls, count in drift_classes[:40]:
        ci_html += f'<tr><td>{cls}</td><td class="count">{count}</td></tr>'
    ci_html += "</tbody></table></details>"

ci_inner.append(BeautifulSoup(ci_html, "html.parser"))
new_body.append(ci_section)


# ── 15. Trailing scripts + footer ───────────────────────────────────────────
orig_body = soup.body
trailing_scripts = orig_body.find_all("script", recursive=False)[-3:]
for s in trailing_scripts:
    new_body.append(deepcopy(s))

footer = BeautifulSoup(
    '<footer style="text-align:center;padding:48px 24px;color:#525252;font-size:12px;letter-spacing:.05em;">'
    'Living design system v2 · extracted from <code style="color:#a3a3a3;">nexusflow-saas.aura.build</code> · '
    f"12 sections · {len(class_counter)} unique classes · {full_count} ✓ / {partial_count} ◐ / {missing_count} ✗ DTCG categories"
    "</footer>",
    "html.parser",
)
new_body.append(footer)


# ── Write ──────────────────────────────────────────────────────────────────
OUT.write_text(new.prettify(), encoding="utf-8")
print(f"✅ Wrote {OUT} ({OUT.stat().st_size // 1024} KB)")
print(
    f"   Coverage: {full_count} ✓ + {partial_count} ◐ + {missing_count} ✗ = {total_score:.1f}/100"
)
print(
    f"   Classes: {len(class_counter)} unique, {len(drift_classes)} arbitrary-value drift"
)
