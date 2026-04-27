"""Coverage for kratos_clone/post.py — rewrite_html_assets + strip_scroll_fix.

Phase 1 of ROADMAP. Targets audit P1-F (rewrite collision risk) and the orphan
CSS injection pattern (the Aura-srcdoc fix that makes the entire fork worth
shipping).
"""

from __future__ import annotations
import pytest

from kratos_clone.post import rewrite_html_assets, strip_scroll_fix


# ── rewrite_html_assets ──────────────────────────────────────────────────────


def test_rewrite_empty_dict_unchanged():
    """No captured assets → HTML unchanged."""
    html = '<html><head></head><body><img src="https://x.com/a.png"></body></html>'
    out = rewrite_html_assets(html, {}, "https://x.com")
    assert out == html


def test_rewrite_single_exact_match():
    """Single asset URL → replaced with local path."""
    html = '<html><body><img src="https://x.com/a.png"></body></html>'
    out = rewrite_html_assets(
        html, {"https://x.com/a.png": "assets/a_abc.png"}, "https://x.com"
    )
    assert "assets/a_abc.png" in out
    assert "https://x.com/a.png" not in out


def test_rewrite_prefix_collision_longer_first():
    """`/a.png` is a substring of `/a.png/v2.png` — longer-first sort prevents corruption.

    Without sort, replacing `/a.png` first would corrupt the longer URL.
    """
    html = '<a href="https://x.com/a.png/v2.png"></a><img src="https://x.com/a.png">'
    assets = {
        "https://x.com/a.png": "assets/short.png",
        "https://x.com/a.png/v2.png": "assets/long.png",
    }
    out = rewrite_html_assets(html, assets, "https://x.com")
    # Both targets must resolve correctly — neither should be corrupted by partial overlap
    assert "assets/short.png" in out
    assert "assets/long.png" in out
    # Original URLs gone
    assert "https://x.com/a.png" not in out
    assert "https://x.com/a.png/v2.png" not in out


def test_rewrite_percent_encoded_url():
    """URL appears percent-encoded in HTML; raw form in captured_assets."""
    raw_url = "https://x.com/path with spaces/img.png"
    encoded = "https://x.com/path%20with%20spaces/img.png"
    html = f'<img src="{encoded}">'
    out = rewrite_html_assets(html, {raw_url: "assets/spaces.png"}, "https://x.com")
    # The encoded form should also be replaced (post.py's quote() branch)
    assert "assets/spaces.png" in out
    assert encoded not in out


def test_orphan_css_injected_before_head_close():
    """CSS captured but not <link>ed → injected before </head>.

    This is the Aura-srcdoc fix: the wrapper page loads the Tailwind bundle
    via <link>, but the iframe srcdoc content (which we extract) only has
    Google Fonts. We re-link orphan CSS so the captured site still styles.
    """
    html = "<html><head><title>x</title></head><body>hi</body></html>"
    assets = {"https://x.com/main.css": "assets/main.css"}
    out = rewrite_html_assets(html, assets, "https://x.com")
    assert '<link rel="stylesheet" href="assets/main.css">' in out
    # Injected BEFORE </head>
    assert out.index('<link rel="stylesheet"') < out.index("</head>")


def test_orphan_css_injected_into_body_when_no_head():
    """No </head> tag → injected after <body...> as fallback."""
    html = '<html><body class="x">hi</body></html>'
    assets = {"https://x.com/main.css": "assets/main.css"}
    out = rewrite_html_assets(html, assets, "https://x.com")
    assert '<link rel="stylesheet" href="assets/main.css">' in out
    # Injected AFTER opening <body...>
    body_open = out.index('<body class="x">') + len('<body class="x">')
    link_pos = out.index('<link rel="stylesheet"')
    assert link_pos > body_open


def test_orphan_css_prepended_when_no_head_no_body():
    """Pure fragment with neither head nor body → injected at start."""
    html = "<div>fragment</div>"
    assets = {"https://x.com/main.css": "assets/main.css"}
    out = rewrite_html_assets(html, assets, "https://x.com")
    assert out.startswith('<link rel="stylesheet" href="assets/main.css">')


# ── strip_scroll_fix ─────────────────────────────────────────────────────────


def test_strip_basic_scroll_fix_block():
    """Standard <style data-scroll-fix="true"> block is removed."""
    html = (
        "<head>"
        '<style data-scroll-fix="true">.x{transform:none !important}</style>'
        "<style>p{color:red}</style>"
        "</head>"
        "<body><p>keep</p></body>"
    )
    out = strip_scroll_fix(html)
    assert "data-scroll-fix" not in out
    assert "transform:none" not in out
    # Other style block + body content preserved
    assert "p{color:red}" in out
    assert "<p>keep</p>" in out


def test_strip_uppercase_TRUE_value():
    """re.IGNORECASE means TRUE / True / true all match."""
    html = '<style data-scroll-fix="TRUE">.x{}</style><p>keep</p>'
    out = strip_scroll_fix(html)
    assert "data-scroll-fix" not in out
    assert "<p>keep</p>" in out


def test_strip_idempotent():
    """Running strip twice produces same result as once."""
    html = '<style data-scroll-fix="true">.x{}</style><p>keep</p>'
    once = strip_scroll_fix(html)
    twice = strip_scroll_fix(once)
    assert once == twice


def test_strip_does_not_touch_unrelated_style():
    """A normal <style> with no data-scroll-fix attr is untouched."""
    html = '<style>body{margin:0}</style><style data-other="y">.q{}</style>'
    out = strip_scroll_fix(html)
    # Both <style> blocks survive
    assert "body{margin:0}" in out
    assert ".q{}" in out


# ── parametrized smoke ───────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "captured,html_in,expected_in,expected_not_in",
    [
        ({}, "<p></p>", "<p></p>", None),
        (
            {"http://a/b.js": "assets/b.js"},
            '<script src="http://a/b.js"></script>',
            "assets/b.js",
            "http://a/b.js",
        ),
        (
            {"http://a/c.png": "assets/c.png"},
            '<img src="http://a/c.png">',
            "assets/c.png",
            "http://a/c.png",
        ),
    ],
)
def test_rewrite_parametrized(captured, html_in, expected_in, expected_not_in):
    out = rewrite_html_assets(html_in, captured, "http://a")
    assert expected_in in out
    if expected_not_in is not None:
        assert expected_not_in not in out
