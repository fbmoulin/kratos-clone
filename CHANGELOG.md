# Changelog

All notable changes to **Kratos Clone — Website Downloader** are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Project does not strictly follow SemVer — minor numbers bump on each release
group, with the `0.x` series reflecting pre-1.0 status.

---

## [Unreleased] — 2026-08-03: the container is finally tested

### Added
- **`docker image build + smoke` CI job.** Nothing in this pipeline had ever built the
  container. Every job installed dependencies its own way (`uv sync` into a runner venv),
  so the `Dockerfile` — the thing production runs — was verified by nobody. Confirmed by
  reading all 9 jobs: zero occurrences of `docker build`. Two independent adversarial
  review lenses rated the gap HIGH.

  The job builds the real image and asserts four things a green `pytest` cannot: it builds;
  `import app` works *inside* it; `gunicorn` resolves on PATH (`entrypoint.sh` invokes it
  bare, so any install-layout change that moves it would still build green and die on
  container start); and `/health` reports the `build_sha` it was built from, exercising the
  `GIT_SHA` ARG wiring nothing else touches.

  The `build_sha` assertion was sabotage-tested before committing — it fails on a mismatched
  SHA and on a response missing the field. Deliberately **not** a required status check yet
  (slowest job here), but **not** `continue-on-error` either: it fails visibly.

  Not hypothetical. PR #43 merged a one-line `requirements.txt` edit that made
  `pip install -r` unresolvable; CI was green and it surfaced at deploy time. PR #48 fixed it.

### Notes
- On a `pull_request` event `github.sha` is the ephemeral **merge commit**, so the
  `build_sha` the job prints on a PR run does not exist in permanent history. Measured and
  documented in the job. On a push to `main` it is the real commit — verified: `main` at
  `c692e8c` reported `build_sha: c692e8c9…`.
- The current `Dockerfile` has no `--retries`/`--timeout` on its `pip install`. Six
  consecutive local builds failed with `ReadTimeoutError` from `files.pythonhosted.org`,
  including two against the unmodified `main`. A `uv`-based install of the identical package
  set succeeded first try. The follow-up (removing `requirements.txt`) makes this moot rather
  than patching it — plan at `docs/superpowers/plans/2026-08-02-drop-requirements-txt.md`.

---

## [Unreleased] — 2026-08-02: CI made reproducible and enforcing

### Fixed
- **`mypy` was red on `main` from 2026-06-29 to 2026-08-02** and every PR opened in that
  window inherited the failure while staying mergeable. beautifulsoup4 4.15 declares
  `name: None` with no default on the overload that takes `attrs` as a dict, so
  `find_all(attrs={...})` matched no variant. Fixed at 5 call sites by passing
  `name=None` **by keyword** (bs4 removed a positional parameter in a minor release, so
  binding by name is the safer coupling). Verified green under both 4.14.3 and 4.15.0.
- **The `requirements.txt ⇄ uv.lock` guard did not check what its comment claimed.** A
  bare `uv export` silently re-locks on a pyproject/lock mismatch and exports the *fresh*
  resolution, so the diff compared against a network resolution rather than the committed
  lock. Fixed with `--locked`. Separately, nothing in CI detected pyproject↔lock drift at
  all; added `uv lock --check`, the only command that does.
- Three `_as_str(elem["KEY"])` reads in `downloader.py` now use `.get()`. Presence was
  guaranteed only by the `find_all` filter on the line above, and `Tag.__getitem__` raises
  rather than returning `None`, so mypy could not see the coupling — widening the filter
  later would have raised `KeyError` on the live download path with CI still green.

### Changed
- **Seven CI jobs pinned to `uv.lock`** (`lint`, `smoke`, `pytest`, `render-live`,
  `pip-audit`, `mypy`, `bandit`) via `astral-sh/setup-uv` + `uv sync --locked --group dev`,
  with `uv run --frozen` on every execution line. Each previously installed unpinned latest
  from PyPI, so a green run described whatever PyPI served that morning. `uv` pinned to
  0.12.1, re-verified against the four behaviours the design rests on before pinning.
  `actions/setup-python` dropped (`setup-uv` provisions the interpreter from
  `.python-version`); dead `cache: pip` keys removed.
- `astral-sh/setup-uv` pinned to a **commit SHA**, not a tag, so a re-pointed tag cannot
  change what executes on a public repo. Partially closes the `docs/AUDIT.md` P3 on CI
  action SHA-pinning — `actions/checkout@v7` remains on a tag.
- `.github/dependabot.yml`'s NOTE described the behaviour backwards. Re-measured: the uv
  ecosystem rewrites `requirements.txt` for **production**-group bumps but not development
  ones (it is exported `--no-dev`), and leaves it AHEAD of `uv.lock`.

### Added
- **`GET /health` reports `build_sha`.** A 200 proved a process was alive, not which commit
  it served. Resolution order: `KC_BUILD_SHA` (Dockerfile ARG) → `RENDER_GIT_COMMIT` →
  `RAILWAY_GIT_COMMIT_SHA` → the literal `"unknown"`, which is a finding rather than a
  default. Read per request, never cached at import. 13 tests.
- **`scripts/relock.sh`** as the single implementation of the requirements-regeneration
  command, which previously lived in two places that disagreed. Rejects package names
  absent from `uv.lock` — measured: `uv lock --upgrade-package` exits 0 on an unknown name,
  so a typo produced a successful run and an empty diff.
- **Non-blocking `forward-compat` canary.** Pinning removed the only thing exercising newer
  releases; this job resolves latest-from-PyPI and type-checks. Proven not decorative:
  reverting the bs4 fix at one call site makes it fail with `[call-overload]`.
- `tests/test_bs4_attr_filter.py` (8 tests) pinning bs4's attribute-presence contract.

### Security
- **Pillow 12.2.0 → 12.3.0**, closing **26 advisories**. `pip-audit` on `main` now reports
  `No known vulnerabilities found`. Repository `vulnerability-alerts` and
  `automated-security-fixes` enabled — the `security` group in `dependabot.yml` had never
  fired because the two are separate endpoints.
- Ruleset `Protect main` now requires **4** status checks (was 2): `mypy` and `pytest`
  added. `strict_required_status_checks_policy` deliberately left `false`.
- Dependency bumps: beautifulsoup4 4.15.0, openai 2.50.0, playwright 1.61.0, certifi
  2026.7.22, plus dev-group mypy 2.3.0 and ruff 0.16.0.

Test suite 337 → **358 passed, 3 skipped**.

---

## [Unreleased] — WIP on `feat/personalize-preview-modal` branch

### In progress
- **Personalize preview modal** (spec at `docs/superpowers/specs/2026-05-16-personalize-preview-modal-design.md`).
  Brainstorming + plan-review-cycle established the design across 2 review rounds.
  Round 1: 10 findings closed (1 Critical / 6 Major / 1 Minor / 2 Advisory).
  Round 2: 2 Critical closed (dual `<path:>` converter routing bug;
  iframe `sandbox="allow-scripts"` + ACAO restricted-to-host header for
  `@font-face` + `credentialless` attribute progressive enhancement).
  **Remaining R2 findings open**: 2 Major (R2-PRC003 symlink test
  portability, R2-PRC004 SVG XSS in-iframe phishing CSP defense) + 5 Minor
  (R2-PRC005 SPA verifiability, R2-PRC006 cache-clear before pipeline
  failure, R2-PRC007 mock strategy conflict, R2-PRC008 env override
  fragility, R2-PRC009 test_personalize_app.py existence unverified) +
  1 Advisory (R2-PRC010 template LOC growth note).
  Branch tip: `abbc741`. Next session should resume Round 2 walk-through.
  No code shipped yet; implementation will follow `writing-plans` skill
  after Round 2 closes.

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
