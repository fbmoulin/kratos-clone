"""Post-capture HTML rewriting: replace absolute asset URLs with local relative paths,
strip destructive scroll-fix overlays, inject orphan CSS links.

P1-F fix: rewriting is now BeautifulSoup-aware. Earlier versions used naive
`html.replace(url, local)` which would corrupt URL substrings appearing inside
`<script>` blocks, comments, or JSON data attributes. The new implementation
only rewrites:

  - URL-bearing attributes (`src`, `href`, `srcset`, `data-src`, `data-original`,
    `data-lazy-src`, `data-image`, `data-bg`, `poster`, `content`, `xlink:href`)
  - `style="..."` inline attribute `url(...)` refs
  - `<style>` block `url(...)` refs

Script bodies, HTML comments, and arbitrary text nodes are NEVER touched.
"""

from __future__ import annotations

import re
from urllib.parse import quote

from bs4 import BeautifulSoup
from bs4.element import AttributeValueList

# Attributes that commonly carry a URL value (single URL).
# Security review extension: cite, data, formaction, action, manifest, background
# (rare but real on legacy/SVG-embedded pages — broken offline if not rewritten).
_URL_ATTRS = (
    "src",
    "href",
    "data-src",
    "data-original",
    "data-lazy-src",
    "data-image",
    "data-bg",
    "data-url",
    "poster",
    "xlink:href",
    "data-srcset",
    "cite",  # <blockquote>, <q>, <ins>, <del>
    "data",  # <object>
    "formaction",  # <button>, <input type=submit>
    "action",  # <form>
    "manifest",  # <html>
    "background",  # <body> (deprecated but still seen)
)
# `srcset` (and `data-srcset`) parse differently — each item is `URL [Wd|N.Mx]`.
_SRCSET_ATTRS = ("srcset", "data-srcset")
# `<meta content="...">` may contain a URL when itemprop/property is og:image, etc.
_CONTENT_URL_ELEMENTS = ("meta",)

_URL_FUNC_RE = re.compile(
    r"""url\(
        \s*
        (['"]?)        # optional quote
        ([^)'"]+)      # the URL itself (no parens or matching quote)
        \1             # closing quote
        \s*
    \)""",
    re.VERBOSE,
)


def _as_str(v: str | AttributeValueList) -> str:
    """Narrow BS4's ``el[attr]`` value to ``str`` for url-bearing attrs.

    BS4 types attribute access as ``str | AttributeValueList``; for the
    URL-carrying attributes we touch (``src``, ``href``, ``content``,
    ``style``), real-world HTML5 always yields ``str``. This helper
    coerces the unreachable multi-valued case via ``" ".join(v)`` so
    mypy is satisfied without losing semantics.
    """
    return v if isinstance(v, str) else " ".join(v)


def _build_url_map(captured: dict[str, str]) -> dict[str, str]:
    """Returns map of URL → local path with both raw + percent-encoded keys.

    Sorted longest-first when iterated to avoid prefix collisions on lookup.
    """
    out: dict[str, str] = {}
    for url, local in captured.items():
        out[url] = local
        encoded = quote(url, safe=":/?#[]@!$&'()*+,;=")
        if encoded != url:
            out[encoded] = local
    return out


def _try_replace(value: str, url_map: dict[str, str]) -> str:
    """Replace `value` if it equals any captured URL (or contains them)."""
    if not value:
        return value
    # Exact match — common case
    if value in url_map:
        return url_map[value]
    # Substring match (rare; e.g. `?ref=https://...`). Sort longest-first to
    # avoid prefix collisions.
    out = value
    for url in sorted(url_map.keys(), key=len, reverse=True):
        if url in out:
            out = out.replace(url, url_map[url])
    return out


def _rewrite_srcset(value: str, url_map: dict[str, str]) -> str:
    """Rewrite each URL in a srcset attribute. Format: `url1 1x, url2 2x` etc."""
    if not value:
        return value
    parts = []
    for item in value.split(","):
        item = item.strip()
        if not item:
            continue
        # First whitespace-delimited token is the URL; rest is descriptor (1x, 100w...)
        bits = item.split(None, 1)
        url_part = bits[0]
        rest = (" " + bits[1]) if len(bits) > 1 else ""
        parts.append(_try_replace(url_part, url_map) + rest)
    return ", ".join(parts)


def _rewrite_css_url_funcs(css: str, url_map: dict[str, str]) -> str:
    """Rewrite all url(...) function calls in CSS."""
    if not css:
        return css

    def _sub(m: re.Match[str]) -> str:
        quote_char = m.group(1)
        url = m.group(2).strip()
        new = _try_replace(url, url_map)
        return f"url({quote_char}{new}{quote_char})"

    return _URL_FUNC_RE.sub(_sub, css)


def rewrite_html_assets(html: str, captured_assets: dict[str, str], base_url: str) -> str:
    """Surgical, attribute-aware URL rewriting + orphan CSS injection.

    Audit P1-F: previous `str.replace`-based approach corrupted URL substrings
    that appeared inside `<script>` bodies, comments, and JSON data attributes.
    BeautifulSoup walk now isolates rewriting to actual URL-bearing positions.
    """
    if not captured_assets:
        # Fast-path: no rewrites needed — skip BS4 round-trip to preserve exact
        # input bytes (matters for tests + for downstream byte-stable tooling).
        return html

    url_map = _build_url_map(captured_assets)

    # Use html.parser to keep it dependency-light and avoid lxml-specific quirks.
    soup = BeautifulSoup(html, "html.parser")

    for el in soup.find_all(True):
        # Plain URL attributes
        for attr in _URL_ATTRS:
            if el.has_attr(attr):
                el[attr] = _try_replace(_as_str(el[attr]), url_map)
        # srcset (multi-URL)
        for attr in _SRCSET_ATTRS:
            if el.has_attr(attr):
                el[attr] = _rewrite_srcset(_as_str(el[attr]), url_map)
        # <meta content="...url..."> for og:image and similar
        if el.name in _CONTENT_URL_ELEMENTS and el.has_attr("content"):
            cur = _as_str(el["content"] or "")
            if cur.startswith(("http://", "https://", "//")):
                el["content"] = _try_replace(cur, url_map)
        # Inline style="..." with url(...)
        if el.has_attr("style"):
            el["style"] = _rewrite_css_url_funcs(_as_str(el["style"]), url_map)

    # <style> blocks
    for style in soup.find_all("style"):
        if style.string:
            style.string = _rewrite_css_url_funcs(style.string, url_map)

    # Orphan CSS injection — captured CSS not referenced by any <link>
    css_assets = [v for v in captured_assets.values() if v.endswith(".css")]
    serialized_after = str(soup)
    orphans = [css for css in css_assets if css not in serialized_after]
    if orphans:
        link_tags = "\n".join(f'<link rel="stylesheet" href="{c}">' for c in orphans)
        if "</head>" in serialized_after:
            serialized_after = serialized_after.replace("</head>", f"{link_tags}\n</head>", 1)
        elif "<body" in serialized_after:
            serialized_after = re.sub(
                r"(<body[^>]*>)", rf"\1\n{link_tags}", serialized_after, count=1
            )
        else:
            serialized_after = link_tags + "\n" + serialized_after

    return serialized_after


def strip_scroll_fix(html: str) -> str:
    """Remove <style data-scroll-fix="true"> blocks — they kill GSAP/AOS animations."""
    return re.sub(
        r'<style[^>]*data-scroll-fix=["\']true["\'][^>]*>.*?</style>',
        "",
        html,
        flags=re.DOTALL | re.IGNORECASE,
    )
