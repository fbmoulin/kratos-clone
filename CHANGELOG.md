# Changelog

All notable changes to **Kratos Clone — Website Downloader** are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Project does not strictly follow SemVer — minor numbers bump on each release
group, with the `0.x` series reflecting pre-1.0 status.

---

## [0.4.0] — 2026-05-16 — UI rebrand

### Added
- **Brand identity** — wordmark "KRATOS CLONE" (orange "CLONE" + text-shadow glow), descriptor per page ("WEBSITE DOWNLOADER" on `/`, "PERSONALIZADOR" on `/personalize`). Display font: Bricolage Grotesque via Google Fonts. (#32)
- **Design token system** — full `:root` CSS custom properties: ink + orange scales, semantic colors, multi-layer shadows, 8px spacing grid, radii, durations, easing. Single source of truth per template. (#32)
- **Body radial atmosphere** — two-radial orange bloom over `--ink-base #0a0a14`. `background-attachment: fixed`. (#32)
- **Highlight box on `/`** — `#personalizer-highlight` card with BETA chip + headline + orange CTA "Abrir personalizador →". Hover-lift + glow. Replaces prior plain footer link. (#32)
- **Tips banner on `/personalize`** — collapsible `<details id=tips-banner>` with 3 sections (Como funciona / Dicas para um bom brief / Tempo esperado). LocalStorage flag collapses on return visits. Zero JS for toggle. (#32)
- **Brief-assist on `/personalize`** — "Carregar exemplo pronto" button + 3 icebreaker chips (SaaS / fitness / educacional). Each populates the textarea with a realistic ~250-char PT-BR brief. (#32)
- **Motion grammar** — page-load stagger (header → tagline/tips → indicator → card), CTA pulse (paused on `:hover`), all wrapped in `prefers-reduced-motion: reduce` guard. (#32)

### Fixed
- **Step-indicator connector fill direction** — completing step N now fills the connector N→N+1 (forward, matching operator's mental model), not the connector behind. Discovered via Playwright smoke test; bundled into #32.

### Tests
- 266 passing (was 257), +9 rebrand regression assertions

---

## [0.3.0] — 2026-05-15 — UX hardening (audit U1–U9)

### Added
- **Elapsed timer during download** (U1) — `Processando — Ns` updates every second so long captures don't look stuck. Reset per run, cleared on done/error. (#29)
- **Captures dropdown on `/personalize`** (U5) — new `GET /api/captures` endpoint returns directory listing; `<datalist>` populates `html_dir` input with autocomplete. Free-text preserved. Cold-start safe. (#29)
- **Step indicator on `/personalize`** (U6) — `<nav>` landmark with 3 numbered nodes (Brief / Confirmar / Resultado), three states per node (upcoming / active / completed), animated connector fill, full a11y. (#30)
- **PT-BR error catalog** (U7) — `ERROR_MESSAGES` + `resolveError({status, endpoint, backendError, networkError})` helper. Covers network failure, 400/413/415/429/500 per endpoint with OpenAI/budget hints for 5xx on personalize routes. Tone: declarative, peer-to-peer, no apology theater. (#31)
- **localStorage URL persistence on `/`** (U8) — `loadLastUrl()` / `saveLastUrl()`, try/catch-wrapped for private mode. Re-running variant URLs is now one paste/edit. (#31)
- **Client-side URL validation on `/`** (U9) — `isValidUrl(value)` uses native `new URL()` constructor; restricts to http(s) schemes. Short-circuits malformed inputs before the fetch roundtrip. (#31)

### Changed
- **Logs persist on error** (U2) — log container no longer auto-hides when a session ended in error. Failure traces stay visible for inspection. (#24, refined in #29)
- **URL input no longer auto-clears** on success (U3) — re-running for variant is a common pattern. (#24)
- **`/personalize` discoverable from `/`** (U4) — footer link replaced by highlight box in #32. (#24 → #32)

### Tests
- 257 passing (was 233), +24 new

---

## [0.2.0] — 2026-05-11 — A11y essentials + smoke + mypy + deploy hardening

### Added — A11y essentials (#24)
- Real `<label class=sr-only>` for URL input (was placeholder-only)
- Inline error region (`#errorMessage`, `role=alert`, `aria-live=assertive`) replaces blocking `alert()`
- Log container: `role=log` + `aria-live=polite` + `aria-label`
- Success banner: `role=status` + `aria-live=polite` + focus migrates to download link on complete
- `<form>` wrapper with `type=submit` (removed inline `onclick`)
- `<main aria-busy>` toggles during long worker
- `:focus-visible` outline (3px) on every interactive element
- `<a href="/personalize">` discovery link on `/` (later replaced by highlight box in #32)

### Added — Smoke test (#23)
- `tests/test_download_smoke.py` — 9 pytest cases covering `POST /start-download` → daemon thread → `GET /download-file/<sid>` flow. Monkeypatches `WebsiteDownloader` + `zip_directory` + `DOWNLOAD_FOLDER`; covers happy path, `process()→False`, `process()` raise, unknown session, mid-processing 404, UUID uniqueness.

### Added — mypy Stage A–D (#16, #17, #18, #19)
- Full strict typing on every source file: `personalize/`, `kratos_clone/`, `scripts/`, `app.py`, `wsgi.py`, `downloader.py`
- Hard CI gate (dropped `|| true`); bandit gate raised HIGH → MEDIUM with 0 medium findings

### Changed
- `kratos_clone/capture.py` adopted structlog bound logger (snake_case events, no `print()`) (#20)
- `requirements.txt` fixed (4 missing runtime deps + 4 version drifts) — container deploy was crashing on `import app`; pre-deploy audit shipped (#21)
- `scripts/generate_design_system_v1.py` deleted (dead code; v2 supersedes) (#18)

### Fixed — Audit P2-12 (#15)
- `_on_response` skips responses whose request carried `Authorization` header (avoids JWT/API-key leakage when capturing authed views). One-shot warnings on first auth-skip + first `octet-stream`. New `authed_skipped` manifest counter.

### Tests
- 233 passing (was 74), +159 across the whole release block

---

## [0.1.0] — 2026-04-27 — Initial release

Hardened SPA capture + design-system extraction + observability + personalization MVP. See `ROADMAP.md` for full phase-by-phase history.

### Phase 1 — Tests + factory
- `app.py` refactored to `create_app(start_janitor, run_boot_cleanup)` factory; `wsgi.py` for gunicorn
- 52 pytest cases across `test_post.py`, `test_capture_helpers.py`, `test_client_errors.py`

### Phase 2 — Structural fixes
- Patch D shadow walker uses live DOM (was cloned)
- Asset write race resolved via `asyncio.create_task` + `gather`
- Generators use semantic class-signature lookup
- Iframe srcdoc length-compared against main doc
- Same-origin via `urlparse().netloc`

### Phase 3 — Production hardening
- gunicorn 21.2 → 22.0 (CVE-2024-1135)
- Content-type strict + 415 on non-JSON
- URL query/fragment stripped before logging (P1-I) + ANSI/control-char sanitization (P2-4)
- Browser logger queue cap (200, drop oldest)
- Three-pass scroll wall-clock budget (`KCD_MAX_SCROLL_S=120`)
- Global asset disk caps (`KCD_MAX_TOTAL_MB=200`, `KCD_MAX_ASSETS=500`)
- BS4-aware `rewrite_html_assets`
- Flask-Limiter on `/api/client-errors` (60/min/IP)
- `pip-audit` job in CI
- **All 9 P1 audit items closed**

### Phase 4 — Personalization MVP
- New `personalize/` package: `slots`, `sanitize`, `openai_client`, `patcher`, `pipeline`, `cli`
- 3 Flask routes (`/personalize`, `/api/personalize/structure`, `/api/personalize/run`) + intake template
- Hard budget cap (default $1.00) on `OpenAIBrandClient`
- Closed-enum strict JSON schema for patches+images (zero slot-id hallucination)
- Live-validated against gpt-5-mini Responses API (~$0.105 spent during E2E test)
- **Closes audit P2-11** (LLM input/output hardening)

### Phase 5 — Pipeline completion
- `scripts/probe.py` (Stage 1 site recon), `scripts/post_process.py` (Stage 3 asset audit + inline), `scripts/validate.py` (Stage 6 quality gate)
- Hardcoded `DTCG_CATEGORIES` removed; coverage score now computed by `validate.coverage_scorecard(inv)`
- **Closes audit P2-8** (tautological scorecard)

### Phase 6 — DevEx + observability polish
- Dependabot weekly grouped (pip + github-actions)
- ruff `[tool.ruff]` config (E/F/W/I/UP/B/C4/SIM)
- mypy `[tool.mypy]` strict on `personalize/` (Stage A)
- bandit HARD gate on HIGH severity
- `X-Request-ID` middleware: UUID4 + structlog contextvars + response header

### Tests
- 74 → 183 → 210 throughout the release block

---

[Unreleased]: https://github.com/fbmoulin/kratos-clone/compare/v0.4.0...HEAD
[0.4.0]: https://github.com/fbmoulin/kratos-clone/releases/tag/v0.4.0
[0.3.0]: https://github.com/fbmoulin/kratos-clone/releases/tag/v0.3.0
[0.2.0]: https://github.com/fbmoulin/kratos-clone/releases/tag/v0.2.0
[0.1.0]: https://github.com/fbmoulin/kratos-clone/releases/tag/v0.1.0
