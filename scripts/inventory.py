"""Extract design system inventory from downloaded index.html.
Outputs JSON to stdout for use in design-system.html generation."""

import json
import re
from collections import Counter
from pathlib import Path
from bs4 import BeautifulSoup

ROOT = Path(__file__).parent
HTML = (ROOT / "index.html").read_text(encoding="utf-8")
soup = BeautifulSoup(HTML, "html.parser")

# 1. Sections with IDs
sections = []
for s in soup.find_all("section"):
    sid = s.get("id") or ""
    h = s.find(["h1", "h2", "h3"])
    title = h.get_text(strip=True)[:80] if h else ""
    sections.append({"id": sid, "title": title, "classes": s.get("class", [])})

# 2. Original <style> blocks (exclude scroll-fix)
styles = []
for st in soup.find_all("style"):
    if st.get("data-scroll-fix"):
        continue
    txt = (st.string or "").strip()
    if txt:
        styles.append(txt)

# 3. Heading inventory (by tag, dedup by class signature)
headings = {}
for tag in ["h1", "h2", "h3", "h4", "h5", "h6"]:
    seen = {}
    for el in soup.find_all(tag):
        cls = " ".join(el.get("class", []))
        if cls not in seen:
            seen[cls] = el.get_text(strip=True)[:60]
    headings[tag] = [{"classes": k, "sample": v} for k, v in seen.items()]

# 4. Paragraph variants (group by class signature, top 8)
p_signatures = Counter()
p_samples = {}
for p in soup.find_all("p"):
    cls = " ".join(p.get("class", []))
    if not cls:
        continue
    p_signatures[cls] += 1
    if cls not in p_samples:
        p_samples[cls] = p.get_text(strip=True)[:80]
paragraphs = [
    {"classes": c, "count": p_signatures[c], "sample": p_samples[c]}
    for c, _ in p_signatures.most_common(10)
]

# 5. Buttons & links-as-buttons
buttons = []
seen_btn_sigs = set()
for b in soup.find_all("button"):
    cls = " ".join(b.get("class", []))
    if cls and cls not in seen_btn_sigs:
        seen_btn_sigs.add(cls)
        buttons.append(
            {
                "tag": "button",
                "classes": cls,
                "label": b.get_text(strip=True)[:40],
                "html": str(b),
            }
        )
        if len(buttons) >= 8:
            break

# 6. Color tokens from inline classes (Tailwind arbitrary values)
arbitrary_colors = Counter()
for el in soup.find_all(True):
    for c in el.get("class", []):
        m = re.match(r"^(?:bg|text|border|from|to|via)-\[#([0-9a-fA-F]{3,8})\]$", c)
        if m:
            arbitrary_colors[c] += 1
named_color_tokens = Counter()
for el in soup.find_all(True):
    for c in el.get("class", []):
        if re.match(
            r"^(?:bg|text|border)-(?:orange|neutral|white|black|gray|zinc|slate)-?[\w/]*$",
            c,
        ):
            named_color_tokens[c] += 1

# 7. Animation/motion classes
motion_classes = Counter()
motion_patterns = [
    "hero-fade",
    "gs-reveal",
    "word-wrapper",
    "word-inner",
    "perspective-container",
    "dashboard-plane",
    "scene-container",
    "border-gradient",
    "animate-",
]
for el in soup.find_all(True):
    for c in el.get("class", []):
        for p in motion_patterns:
            if p in c:
                motion_classes[c] += 1

# 8. Icon usage
icons = Counter()
for el in soup.find_all("iconify-icon"):
    icons[el.get("icon", "")] += 1

# 9. Backdrop & glass
glass_classes = Counter()
for el in soup.find_all(True):
    for c in el.get("class", []):
        if "backdrop-" in c or c.startswith("blur") or "/" in c and "neutral" in c:
            glass_classes[c] += 1

# 10. Container widths
containers = Counter()
for el in soup.find_all(True):
    for c in el.get("class", []):
        if c.startswith("max-w-"):
            containers[c] += 1

# 11. Section vertical rhythm
v_rhythm = Counter()
for s in soup.find_all("section"):
    for c in s.get("class", []):
        if re.match(r"^(?:py|pt|pb)-\d+$", c):
            v_rhythm[c] += 1

# 12. Hero raw HTML (entire first <section>)
hero_html = ""
first_section = soup.find("section")
if first_section:
    hero_html = str(first_section)

out = {
    "sections": sections,
    "styles_count": len(styles),
    "styles_total_kb": round(sum(len(s) for s in styles) / 1024, 1),
    "headings": headings,
    "paragraphs": paragraphs,
    "buttons": buttons,
    "arbitrary_colors": dict(arbitrary_colors.most_common(20)),
    "named_color_tokens": dict(named_color_tokens.most_common(30)),
    "motion_classes": dict(motion_classes.most_common(20)),
    "icons": dict(icons.most_common(40)),
    "icons_total": sum(icons.values()),
    "glass_classes": dict(glass_classes.most_common(15)),
    "containers": dict(containers.most_common(10)),
    "v_rhythm": dict(v_rhythm.most_common(10)),
    "hero_html_kb": round(len(hero_html) / 1024, 1),
    "total_html_kb": round(len(HTML) / 1024, 1),
}
print(json.dumps(out, indent=2, ensure_ascii=False))
