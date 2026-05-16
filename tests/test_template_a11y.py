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


# ── U7: PT-BR error catalog on both templates ────────────────────────────────


def test_index_has_error_catalog(client):
    """U7: index.html must declare the ERROR_MESSAGES catalog + resolveError helper."""
    html = client.get("/").data.decode("utf-8")
    assert "ERROR_MESSAGES" in html
    assert "resolveError" in html
    # Catalog must cover network failure + 429 (rate limit) at minimum
    assert "Sem resposta do servidor" in html
    assert "Limite de requisições atingido" in html


def test_personalize_has_error_catalog(client):
    """U7: personalize.html must declare the same catalog (single-script-per-template dup)."""
    html = client.get("/personalize").data.decode("utf-8")
    assert "ERROR_MESSAGES" in html
    assert "resolveError" in html
    # Personalize-specific: budget/OpenAI hint on 500
    assert "OpenAI" in html
    assert "Brief rejeitado pelo servidor" in html


def test_index_no_raw_http_status_in_error_path(client):
    """U7: no `'HTTP ' + ` interpolation should leak into the error display path."""
    html = client.get("/").data.decode("utf-8")
    assert "'HTTP ' + " not in html
    assert '"HTTP " + ' not in html


def test_personalize_no_raw_http_status_in_error_path(client):
    """U7: same check for personalize.html — error catalog replaces raw HTTP fallback."""
    html = client.get("/personalize").data.decode("utf-8")
    assert "'HTTP ' + " not in html
    assert '"HTTP " + ' not in html


# ── U8: localStorage URL persistence on index.html ───────────────────────────


def test_index_persists_last_url_to_localstorage(client):
    """U8: index.html must save+restore the last URL across page loads."""
    html = client.get("/").data.decode("utf-8")
    assert "localStorage" in html
    assert "kratos_clone_last_url" in html
    assert "loadLastUrl" in html
    assert "saveLastUrl" in html


def test_index_localstorage_wrapped_in_try_catch(client):
    """U8: localStorage access must be try/catch-wrapped (private mode safety)."""
    html = client.get("/").data.decode("utf-8")
    # Both helpers must use try/catch — strict check that the literal pattern is present
    assert html.count("try {") >= 2  # at least loadLastUrl + saveLastUrl


# ── U9: client-side URL validation on index.html ─────────────────────────────


def test_index_validates_url_client_side(client):
    """U9: a client-side URL validator must run BEFORE the fetch roundtrip."""
    html = client.get("/").data.decode("utf-8")
    assert "isValidUrl" in html
    # Must use the URL constructor (the canonical, browser-native validator)
    assert "new URL(" in html
    # Must restrict to http(s) — file:// or javascript: must not be accepted
    assert "'http:'" in html or '"http:"' in html
    assert "'https:'" in html or '"https:"' in html


# ── Rebrand 2026-05-16: tokens, brand, highlight box, tips, brief-assist, motion ──


def test_brand_wordmark_in_both_templates(client):
    """Rebrand: 'KRATOS CLONE' wordmark appears on / and /personalize."""
    for route in ("/", "/personalize"):
        html = client.get(route).data.decode("utf-8")
        assert "KRATOS" in html, f"{route} missing KRATOS wordmark"
        assert "CLONE" in html, f"{route} missing CLONE wordmark"
        assert "brand-wordmark__logo" in html, f"{route} missing brand wordmark class"


def test_design_tokens_declared(client):
    """Rebrand: :root CSS custom properties for the token system."""
    for route in ("/", "/personalize"):
        html = client.get(route).data.decode("utf-8")
        assert "--ink-base" in html, f"{route} missing --ink-base token"
        assert "--orange-core" in html, f"{route} missing --orange-core token"


def test_bricolage_grotesque_font_loaded(client):
    """Rebrand: Google Fonts <link> for Bricolage Grotesque on both routes."""
    for route in ("/", "/personalize"):
        html = client.get(route).data.decode("utf-8")
        assert "Bricolage+Grotesque" in html, f"{route} missing Bricolage Grotesque font link"


def test_highlight_box_on_index(client):
    """Rebrand: highlight box CTA replaces the old plain personalize link."""
    html = client.get("/").data.decode("utf-8")
    assert 'id="personalizer-highlight"' in html
    assert "BETA" in html  # chip badge
    assert 'href="/personalize"' in html
    assert "Abrir personalizador" in html


def test_tips_banner_on_personalize(client):
    """Rebrand: collapsible tips banner with 3 sections + cost hint."""
    html = client.get("/personalize").data.decode("utf-8")
    assert "<details" in html and 'id="tips-banner"' in html
    assert "<summary" in html
    assert "Como funciona" in html
    assert "Dicas para um bom brief" in html
    assert "Tempo esperado" in html


def test_brief_assist_button_and_chips(client):
    """Rebrand: sample-brief button + 3 icebreaker chips on /personalize."""
    html = client.get("/personalize").data.decode("utf-8")
    assert 'id="btn-sample-brief"' in html
    # All 3 icebreaker chips with their domain labels
    assert "SaaS de produtividade" in html
    assert "App de fitness" in html
    assert "Plataforma educacional" in html


def test_u6_connector_fill_direction_fixed(client):
    """U6 fix: completing step N fills connector N→N+1 (forward), not (N-1)→N."""
    html = client.get("/personalize").data.decode("utf-8")
    # New (correct) pattern present
    assert "'step-connector-' + n + '-' + (n + 1)" in html
    # Old (buggy) pattern absent — guard against regression
    assert "(n - 1) + '-' + n" not in html


def test_prefers_reduced_motion_respected(client):
    """Rebrand: motion guard for users with prefers-reduced-motion: reduce."""
    for route in ("/", "/personalize"):
        html = client.get(route).data.decode("utf-8")
        assert "prefers-reduced-motion" in html, f"{route} missing motion guard"
        # Must zero out animation + transition durations
        assert "animation-duration: 0.01ms" in html, f"{route} guard doesn't disable animations"


def test_existing_a11y_contract_preserved(client):
    """Rebrand guard: prior a11y attributes must survive (no regression)."""
    index_html = client.get("/").data.decode("utf-8")
    personalize_html = client.get("/personalize").data.decode("utf-8")
    # Index a11y
    assert 'for="urlInput"' in index_html
    assert 'role="alert"' in index_html
    assert 'aria-live="polite"' in index_html
    # Personalize a11y
    assert 'id="step-indicator"' in personalize_html
    assert 'aria-label="Progresso do formulario"' in personalize_html
    assert 'aria-labelledby="step-1-heading"' in personalize_html
