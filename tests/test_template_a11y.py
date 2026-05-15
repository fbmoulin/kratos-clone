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


# ── U5: captures datalist on /personalize ────────────────────────────────────


def test_personalize_has_captures_datalist(client):
    """U5: html-dir input must be wired to a `<datalist id=captures-list>`."""
    html = client.get("/personalize").data.decode("utf-8")
    assert 'list="captures-list"' in html
    assert 'id="captures-list"' in html
    assert "<datalist" in html


def test_personalize_fetches_captures_on_load(client):
    """U5: page-load JS must fetch /api/captures to populate the datalist."""
    html = client.get("/personalize").data.decode("utf-8")
    assert "/api/captures" in html
    assert "loadCaptures" in html


# ── U1: elapsed timer on / ───────────────────────────────────────────────────


def test_index_has_elapsed_timer_state(client):
    """U1: index.html JS must declare timer state for processing feedback."""
    html = client.get("/").data.decode("utf-8")
    # Both bookkeeping variables present
    assert "elapsedTimer" in html
    assert "elapsedSeconds" in html


def test_index_timer_updates_button_text(client):
    """U1: timer must render `Processando — Ns` (1s resolution) on the button."""
    html = client.get("/").data.decode("utf-8")
    # Initial render (0s)
    assert "Processando — 0s" in html
    # Tick interval is 1s (1000ms)
    assert "setInterval" in html
    assert "1000" in html


def test_index_timer_cleared_on_completion(client):
    """U1: timer must be cleared (no leak) when setLoading(false) is called."""
    html = client.get("/").data.decode("utf-8")
    assert "clearInterval(elapsedTimer)" in html


# ── U6: step indicator on /personalize ───────────────────────────────────────


def test_step_indicator_structure(client):
    """U6: <nav> landmark with aria-label and ordered list scaffold."""
    html = client.get("/personalize").data.decode("utf-8")
    assert 'id="step-indicator"' in html
    assert 'aria-label="Progresso do formulario"' in html


def test_step_nodes_present(client):
    """U6: three step nodes with deterministic IDs for programmatic state updates."""
    html = client.get("/personalize").data.decode("utf-8")
    for node_id in ("step-node-1", "step-node-2", "step-node-3"):
        assert f'id="{node_id}"' in html, f"Missing {node_id}"


def test_step1_is_active_on_load(client):
    """U6: only step 1 carries aria-current=step on initial page render."""
    html = client.get("/personalize").data.decode("utf-8")
    assert 'id="step-node-1"' in html
    assert 'aria-current="step"' in html
    # Exactly one node is "active" on load
    assert html.count('aria-current="step"') == 1


def test_step_connectors_unfilled_on_load(client):
    """U6: connectors exist but no <li> carries the --filled modifier on load.

    The literal string `step-indicator__connector--filled` appears in the CSS
    selector and JS source regardless of state, so this test inspects the
    actual `class=` attribute on each connector <li>.
    """
    import re

    html = client.get("/personalize").data.decode("utf-8")
    for conn_id in ("step-connector-1-2", "step-connector-2-3"):
        match = re.search(rf'<li id="{conn_id}"[^>]*class="([^"]+)"', html)
        assert match, f"Connector <li id={conn_id}> not found in rendered HTML"
        classes = match.group(1).split()
        assert "step-indicator__connector--filled" not in classes, (
            f"{conn_id} should not be filled on initial page load (was: {classes})"
        )
