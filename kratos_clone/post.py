"""Post-capture HTML rewriting: replace absolute asset URLs with local relative paths,
strip destructive scroll-fix overlays, inject orphan CSS links."""

from __future__ import annotations
import re
from urllib.parse import quote


def rewrite_html_assets(
    html: str, captured_assets: dict[str, str], base_url: str
) -> str:
    """Replace every absolute URL we captured with its local relative path,
    then inject <link> tags for orphan stylesheets (CSS captured but not referenced
    by the iframe-srcdoc content — common pattern for Aura/Webflow wrappers)."""
    # 1. Sort by URL length desc so longer URLs replace first (avoids prefix collisions)
    items = sorted(captured_assets.items(), key=lambda kv: -len(kv[0]))
    for url, local in items:
        html = html.replace(url, local)
        encoded = quote(url, safe=":/?#[]@!$&'()*+,;=")
        if encoded != url:
            html = html.replace(encoded, local)

    # 2. Inject orphan CSS bundles (captured but not <link>ed). The Aura iframe
    # srcdoc references only Google Fonts CSS; the actual Tailwind bundle lives
    # on the wrapper page and gets dropped during srcdoc extraction.
    css_assets = [v for v in captured_assets.values() if v.endswith(".css")]
    orphans = [css for css in css_assets if css not in html]
    if orphans:
        # Insert before </head> if present, else at start of <body>
        link_tags = "\n".join(f'<link rel="stylesheet" href="{c}">' for c in orphans)
        if "</head>" in html:
            html = html.replace("</head>", f"{link_tags}\n</head>", 1)
        elif "<body" in html:
            # No head — inject as first body child
            html = re.sub(r"(<body[^>]*>)", rf"\1\n{link_tags}", html, count=1)
        else:
            html = link_tags + "\n" + html

    return html


def strip_scroll_fix(html: str) -> str:
    """Remove <style data-scroll-fix="true"> blocks — they kill GSAP/AOS animations."""
    return re.sub(
        r'<style[^>]*data-scroll-fix=["\']true["\'][^>]*>.*?</style>',
        "",
        html,
        flags=re.DOTALL | re.IGNORECASE,
    )
