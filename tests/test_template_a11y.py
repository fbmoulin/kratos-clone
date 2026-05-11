"""Regression net for the WCAG-essentials added to index.html + personalize.html.

These assertions lock down the **a11y contract** so future template edits
that silently drop a `role`, `aria-live`, or `<label>` get caught in CI.

What's intentionally NOT tested here:
- Visual rendering / pixel diff — out of scope for headless pytest
- Screen-reader narration — needs Playwright + accessibility tree probe
- Focus management at runtime — DOM mutation is JS-side, not in the
  rendered template. Trust the manual QA + JS unit-test future work.
"""

from __future__ import annotations

# ── / (Website Downloader) ───────────────────────────────────────────────────


def test_index_url_input_has_real_label(client):
    """`<input type=url>` must be associated with a visible-or-sr-only `<label>`."""
    html = client.get("/").data.decode("utf-8")
    assert 'for="urlInput"' in html
    assert "URL do site para baixar" in html  # the label text


def test_index_uses_form_with_submit_button(client):
    """Native form > onclick — Enter key + AT 'submit' both work without JS."""
    html = client.get("/").data.decode("utf-8")
    assert 'id="downloadForm"' in html
    assert 'type="submit"' in html
    # The deprecated inline onclick must be gone (was: <button ... onclick="startDownload()">)
    assert "onclick=" not in html


def test_index_error_message_has_role_alert(client):
    """Error region must be `role=alert` so AT announces it immediately."""
    html = client.get("/").data.decode("utf-8")
    assert 'id="errorMessage"' in html
    assert 'role="alert"' in html
    assert 'aria-live="assertive"' in html


def test_index_log_container_is_live_region(client):
    """Log container must be `role=log` + polite live so SSE updates are announced."""
    html = client.get("/").data.decode("utf-8")
    assert 'id="logContainer"' in html
    assert 'role="log"' in html
    assert 'aria-live="polite"' in html


def test_index_success_message_is_status_live(client):
    """Success banner is `role=status` (polite) — non-interruptive completion announce."""
    html = client.get("/").data.decode("utf-8")
    assert 'id="successMessage"' in html
    assert 'role="status"' in html


def test_index_main_card_has_aria_busy(client):
    """Main card flips `aria-busy` so AT knows when a long task is in flight."""
    html = client.get("/").data.decode("utf-8")
    assert 'id="mainCard"' in html
    assert 'aria-busy="false"' in html  # initial state


def test_index_links_to_personalize(client):
    """Discoverability: /personalize must be reachable from / (was hidden before)."""
    html = client.get("/").data.decode("utf-8")
    assert 'href="/personalize"' in html


def test_index_no_alert_call_in_inline_script(client):
    """`alert()` is a UX anti-pattern (blocks AT, ugly mobile, unstyled).

    Allow it in the browser-logger script (defensive try/catch text might mention it),
    but the main download flow must not use it.
    """
    html = client.get("/").data.decode("utf-8")
    # Be specific — the legacy call was `alert('Por favor, insira uma URL válida')`.
    assert "alert('Por favor" not in html
    assert 'alert("Por favor' not in html


# ── /personalize ─────────────────────────────────────────────────────────────


def test_personalize_status_regions_are_polite_live(client):
    """Both `extract-status` and `run-status` must be polite live regions."""
    html = client.get("/personalize").data.decode("utf-8")
    # Both status divs have role=status + aria-live=polite
    assert html.count('role="status"') >= 2
    assert html.count('aria-live="polite"') >= 2
    assert 'id="extract-status"' in html
    assert 'id="run-status"' in html


def test_personalize_main_card_has_aria_busy(client):
    html = client.get("/personalize").data.decode("utf-8")
    assert 'id="mainCard"' in html
    assert 'aria-busy="false"' in html


def test_personalize_sections_are_labelled(client):
    """Each section must reference its heading via `aria-labelledby` for landmark nav."""
    html = client.get("/personalize").data.decode("utf-8")
    assert 'aria-labelledby="step-1-heading"' in html
    assert 'aria-labelledby="step-3-heading"' in html
    assert 'aria-labelledby="step-out-heading"' in html


def test_personalize_links_back_to_root(client):
    """Discoverability: /personalize must link back to / so users don't get stranded."""
    html = client.get("/personalize").data.decode("utf-8")
    assert 'href="/"' in html


# ── Shared focus-visible style (keyboard navigation discoverability) ─────────


def test_index_has_focus_visible_outline(client):
    html = client.get("/").data.decode("utf-8")
    assert ":focus-visible" in html


def test_personalize_has_focus_visible_outline(client):
    html = client.get("/personalize").data.decode("utf-8")
    assert ":focus-visible" in html
