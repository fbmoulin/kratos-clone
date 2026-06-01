"""Contract guard for the deterministic SPA preview fixture (R2-PRC005).

The fixture is exercised for real by the Playwright smoke (Task 7) — that smoke
confirmed its toggle + carousel scripts execute inside the sandboxed
(allow-scripts, opaque-origin) preview iframe. This test is the cheap CI-level
net: it locks the "self-contained, no external network" contract so the fixture
can never silently start depending on the network (which would make the smoke
non-deterministic).
"""

from __future__ import annotations

import re
from pathlib import Path

FIXTURE = Path(__file__).parent / "fixtures" / "spa_sample.html"


def test_spa_fixture_exists():
    assert FIXTURE.is_file(), "tests/fixtures/spa_sample.html is missing (R2-PRC005)"


def test_spa_fixture_has_interactive_markup():
    html = FIXTURE.read_text(encoding="utf-8")
    # A click toggle and a no-dependency carousel — the two behaviors the smoke drives.
    assert 'id="toggle"' in html
    assert 'id="panel"' in html
    assert 'id="carousel"' in html
    assert 'id="next"' in html
    assert html.count('class="slide') >= 2  # at least two carousel slides
    assert "<script>" in html  # the behavior is script-driven (R1-PRC006 allow-scripts)


def test_spa_fixture_makes_no_external_requests():
    """No external URLs / fetch / XHR / external src — keeps the smoke deterministic."""
    html = FIXTURE.read_text(encoding="utf-8")
    assert not re.search(r"https?://", html), "fixture must not reference external URLs"
    for forbidden in ("fetch(", "XMLHttpRequest", "import(", "src="):
        assert forbidden not in html, f"fixture must not use {forbidden!r} (no network)"
