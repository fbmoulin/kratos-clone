# Roadmap — Kratos Clone

Phased plan derived from `docs/AUDIT.md` (multi-agent audit, 2026-04-27) and
the proposed architecture in `docs/WORKFLOW.md` + `docs/PERSONALIZATION.md`.

> **Current state (2026-05-16):** All 6 original phases shipped. Personalization
> MVP live (gpt-5-mini Responses + gpt-image-1, hard budget cap, sanitize
> hardened). All 9 P1 + all 12 P2 audit items closed. mypy strict on every
> source file. **Phase 7 (UX audit U1–U9 + A11y P0) shipped 2026-05-11/15
> across PRs #23, #24, #29, #30, #31.** **Phase 8 (visual rebrand to
> "Kratos Clone" — dark + vivid orange radial + Bricolage Grotesque display)
> shipped 2026-05-16, PR #32.** Pre-deploy audit completed (PR #21 merged):
> both BLOCKERs fixed, urllib3 CVE bumped. See `TODO.md` for opportunistic
> follow-ups, `CHANGELOG.md` for the per-release log, and
> `docs/PRE_DEPLOY_AUDIT_2026-05-10.md` for the remaining MAJOR/MINOR backlog.
> Test count: 266 passing + 2 skipped.

---

## Phase 0 — Doc honesty pass ✅ (this commit)

- README rewrite reflecting fork's actual scope (kratos_clone, scripts, docs, observability)
- Soften 3 overstated claims (`+70%`, `80.8/100`, `+6650%`)
- Add ⚠ STATUS banners to PERSONALIZATION.md (spec only) and Patch D in WORKFLOW.md (broken)
- Create ROADMAP, TODO, CLAUDE.md
- Commit `docs/AUDIT.md` to repo

**Outcome:** docs match reality. Future visitors don't trip on phantom features.

---

## Phase 1 — Tests + factory refactor (next sprint, ~6h)

**Goal:** unblock all future refactors with a regression net.

| Item | File | Effort | Source |
|------|------|--------|--------|
| Refactor `app.py` to `create_app(start_janitor=True)` factory — removes module-level side effects (`cleanup_downloads_folder()`, janitor thread) | `app.py` | S ~1h | AUDIT P2-7 |
| Create `tests/test_post.py` — 7 cases for `rewrite_html_assets()` (empty, single, prefix collision, percent-encoded, orphan-CSS injection in 3 head/body/none scenarios) + `strip_scroll_fix` | `tests/test_post.py` | M ~1.5h | AUDIT P1-H |
| Create `tests/test_capture_helpers.py` — `asset_filename()` (8 cases incl. unicode + `..`/spaces sanitization), `hash_url()` collision sample, `contrast_ratio()` WCAG-cited values | `tests/test_capture_helpers.py` | M ~1.5h | AUDIT P1-H |
| Create `tests/test_client_errors.py` — lift CI inline asserts to fixtures + parametrize. Add: level coercion, `_truncate` boundary, dict-injection-via-`__class__`, RFC 9110 204-no-body | `tests/test_client_errors.py` | M ~1.5h | AUDIT P1-H |
| Add `pytest` job to CI; keep ruff + smoke jobs intact | `.github/workflows/ci.yml` | S ~30m | quality-engineer P0 |

**Exit criteria:** `pytest -q` passes locally and in CI. ≥30 test cases. `coverage.py` >50% on `kratos_clone/` + `app.py`.

---

## Phase 2 — Fix structural bugs (~6h)

| Item | File:line | Effort | Audit ref |
|------|-----------|--------|-----------|
| **Fix Patch D shadow walker** — walk live `document.documentElement`, build serialization string. Remove `cloneNode(true)`. Add `skipped_closed_shadow_roots` counter to manifest. | `kratos_clone/capture.py:78-101` | M ~3h | P1-A |
| **Fix asset write race** — track `asyncio.Task` handles from response handlers, `await asyncio.gather(*pending)` before `context.close()`. | `kratos_clone/capture.py:319` | S ~1h | P1-B |
| **Refactor generators** — replace `inv["buttons"][N]` with semantic class-signature lookup (e.g., find buttons whose classes contain `gradient-to-r from-orange`). Until merged, rename files `generate_nexusflow_*.py`. | `scripts/generate_design_system_v{1,2}.py` | M ~2h | P1-C |
| **Same-origin predicate** — `urlparse().netloc` compare instead of substring. | `kratos_clone/capture.py:517` | XS ~5m | P1-D |
| **Iframe srcdoc length compare** — log decision, opt-out flag, prefer main doc when length ratio < 0.5. | `kratos_clone/capture.py:490` | S ~1h | P1-G |

**Exit criteria:** Patches A-E all working OR documented honestly. New tests cover the fixes.

---

## Phase 3 — Production hardening (~4h)

| Item | File | Effort | Audit ref |
|------|------|--------|-----------|
| Global asset disk caps — `KCD_MAX_TOTAL_MB` (default 200), `KCD_MAX_ASSETS` (default 500). Track cumulative bytes in `_on_response`. | `kratos_clone/capture.py` | S ~30m | P1-E |
| Three-pass scroll wall-clock budget — `KCD_MAX_SCROLL_S` (default 120). Emit `scroll_budget_exceeded: true` in manifest. | `kratos_clone/capture.py:444` | S ~30m | P2-2 |
| Strip query strings + ANSI from logger — privacy + log injection mitigation. | `templates/index.html`, `app.py:_truncate` | XS ~15m | P1-I + P2-4 |
| Drop `force=True` in `request.get_json` + return 415 on wrong content-type. | `app.py:client_errors` | XS ~5m | P2-3 |
| Rate-limit `/api/client-errors` via Flask-Limiter (60/min/IP). | `app.py` | S ~30m | P2-5 |
| Bump `gunicorn>=22.0.0` (CVE-2024-1135) + add `pip-audit` job to CI. | `pyproject.toml`, `.github/workflows/ci.yml` | XS ~15m | P2-6 |
| Browser logger queue cap (`if (queue.length > 200) queue.shift()`). | `templates/index.html` | XS ~5m | L3 |
| `rewrite_html_assets` — switch from raw `str.replace` to BeautifulSoup attribute-targeted rewriting. | `kratos_clone/post.py:18` | M ~1.5h | P1-F |
| Skip authenticated responses in `_on_response` (`request.headers.get("authorization")`); warn on `octet-stream`. | `kratos_clone/capture.py` | S ~30m | P2-12 |

**Exit criteria:** Production-deployable with documented rate limits, disk caps, and privacy guarantees.

---

## Phase 4 — Personalization MVP ✅ SHIPPED 2026-04-27

Implemented `docs/PERSONALIZATION.md` as code in branch `feat/personalize-mvp`.

| Item | Landed in | Notes |
|------|-----------|-------|
| Slot extractor (Step 4) | `personalize/slots.py` | 9 tests; deterministic, no LLM |
| OpenAI client (Steps 2/5/6) | `personalize/openai_client.py` | gpt-5-mini Responses + AsyncOpenAI gpt-image-1; hard budget cap (default \$1.00); 12 mocked tests |
| BS4 patcher (Step 7) | `personalize/patcher.py` | text/word-wrappers/palette/image; 7 tests |
| Pipeline orchestrator | `personalize/pipeline.py` | 7 tests; structured logging per step |
| Flask routes | `app.py` + `templates/personalize.html` | GET /personalize + POST /api/personalize/{structure,run}; 8 route tests |
| CLI | `personalize/cli.py` + `__main__.py` | `python -m personalize ... --dry-run` |
| Security hardening (P2-11) | `personalize/sanitize.py` | text/image/HTML; 21 tests; closes audit P2-11 |
| Live OpenAI smoke (gated) | `tests/integration/test_personalize_live.py` | RUN_OPENAI_LIVE=1; structure_brief + personalize validated against real API (~\$0.105 spent during validation) |

**Exit criteria met:** structure_brief ~\$0.005/10s; personalize ~\$0.10/70s; image gen budget-tested. End-to-end well under \$1/run. Closed-enum schema = zero slot-id hallucination. P2-11 closed.

**Out of scope (deferred to follow-on work):**
- Streaming UI / SSE for run progress (long-poll OK for MVP)
- A/B harness for the "+70%" claim (P2-9 doc-reword closed 2026-05-10; A/B harness itself still deferred)
- Multi-language brief input (English-only first cut)

---

## Phase 5 — Pipeline completion ✅ SHIPPED 2026-04-27

| Item | Landed in | Notes |
|------|-----------|-------|
| Stage 1 site recon | `scripts/probe.py` | HEAD/GET, framework markers, CSP summary → `probe.json`; 12 tests |
| Stage 3 post-process | `scripts/post_process.py` | asset audit + base64 inline; 6 tests |
| Stage 6 validation gate | `scripts/validate.py` | data-driven scorecard + asset refs + placeholder grep + WCAG contrast; 21 tests; **closes P2-8** |
| Drop hardcoded scorecard | `scripts/generate_design_system_v2.py` | DTCG rows + score now computed by `validate.coverage_scorecard(inv)` |

**Exit criteria met:** every pipeline stage now has runnable Python, tested in isolation; coverage score is data-driven and reflects actual inventory evidence.

**Out of scope (deferred to follow-on):**
- Playwright visual diff in `validate.py` — keeps the gate headless + CI-friendly. Add a `validate_visual.py` later if needed.
- Enriching `inventory.py` to extract font_families / durations / shadows / gradients / transitions / stroke_styles / borders — the new scorecard will reward this work directly.

---

## Phase 6 — DevEx + observability polish ✅ SHIPPED 2026-04-27

| Item | Landed in | Notes |
|------|-----------|-------|
| Dependabot grouped weekly | `.github/dependabot.yml` | pip + github-actions, separate security group |
| ruff lint config | `pyproject.toml` `[tool.ruff]` | E/F/W/I/UP/B/C4/SIM rules |
| mypy CI job | `.github/workflows/ci.yml` (mypy job) | strict on personalize/, permissive on legacy; soft gate (`\|\| true`) until app.py + kratos_clone get full hints |
| bandit CI job | `.github/workflows/ci.yml` (bandit job) | hard gate on HIGH severity; existing HIGH (B324 MD5, B201 debug=True) annotated as false-positives in code |
| `request_id` middleware | `app.py` | UUID4 + structlog contextvars; X-Request-ID header in/out; 5 tests |
| `KCD_*` env-var README table | `README.md` | full reference for capture + server tunables |

**Out of scope (deferred to Phase 7 / cleanup sprint):**
- Type hints on `app.py` and full `kratos_clone/` (gradual typing — flip the soft gate when ready)
- Bumping bandit gate to MEDIUM
- Type stubs for the OpenAI SDK overload-mismatch (see `# type: ignore[call-overload]` in `personalize/openai_client.py`)
| `request_id` middleware in Flask via `structlog.contextvars.bind_contextvars` for trace correlation | S ~30m |
| `[tool.ruff]` section in pyproject.toml with `select = ["E", "F", "W", "I", "B", "UP", "SIM"]` + `target-version = "py312"` | XS ~10m |
| Document all `KCD_*` env vars in README + table | XS ~15m |
| README quickstart for `scripts/inventory.py` + generators (currently buried) | XS ~15m |
| Browser logger sampling for high-traffic deploys | S ~30m |

**Exit criteria:** Repo is comfortable for collaborator onboarding. All knobs documented.

---

## Phase 7 — UX audit U1–U9 + A11y P0 ✅ SHIPPED 2026-05-11/15

UX audit on both Flask templates identified 7 a11y categories + 9 user-experience frictions. Shipped across 5 PRs.

| Item | Landed in | Notes |
|------|-----------|-------|
| A1–A7 P0 a11y | PR #24 | `<label>` + `<form>`+`submit`, inline `role=alert` error, `role=log`+`aria-live` log, `role=status` success, `<main aria-busy>`, focus migration, `:focus-visible` outlines, contrast AA |
| Smoke `/start-download → /download-file` | PR #23 | 9 cases monkeypatching `WebsiteDownloader` + `zip_directory`; happy path + `process()→False` + raise + race-during-processing + UUID uniqueness |
| U1 elapsed timer on `/` | PR #29 | `Processando — Ns` 1s tick in `setLoading()`; reset per run; cleared on done/error |
| U5 captures dropdown on `/personalize` | PR #29 | New `GET /api/captures` endpoint + `<datalist>` autocomplete + cold-start safe |
| U6 step indicator on `/personalize` | PR #30 (fix in #32) | `<nav>` 3 nodes + 2 connectors, three states per node, animated `scaleX` connector fill, PT-BR `aria-label`, CSS-only checkmark |
| U7 PT-BR error catalog | PR #31 | `ERROR_MESSAGES` + `resolveError({...})` helper in both templates; replaces 4 `'HTTP ' + status` + 2 `'Falha de rede: ...'` |
| U8 localStorage URL persistence | PR #31 | `loadLastUrl()` / `saveLastUrl()`, try/catch-wrapped |
| U9 client-side URL validation | PR #31 | `isValidUrl()` via native `new URL()`; restricts to http(s) |

**Exit criteria met:** WCAG-essential a11y closed (label/form/aria-live/focus/contrast); operator-facing friction U1–U9 eliminated; backlog audit table empty. 210 → 257 tests.

---

## Phase 9 — Personalize preview modal 🔄 IN DESIGN (2026-05-16)

Visual preview of personalize output (today operator sees only `Saída: <path>`
text). Modal with 3 tabs (Inspecionar iframe / Thumb screenshot / Antes-Depois
split). Spec finalized via brainstorming + plan-review-cycle (2 review rounds,
12 findings dispositioned). Implementation deferred to next session.

| Component | Status |
|-----------|--------|
| Brainstorm + design | ✅ user-approved |
| Spec doc + Plan Review Log | ✅ committed (`abbc741`) |
| Round 1 review | ✅ 10/10 findings closed |
| Round 2 review | 🔄 2 Critical closed; 2 Major + 5 Minor + 1 Advisory open |
| Validator green | ⏳ pending R2 closure |
| writing-plans → tasked plan | ⏳ pending validator |
| Code shipped | ⏳ pending plan execution |

**Spec**: `docs/superpowers/specs/2026-05-16-personalize-preview-modal-design.md`
**Branch**: `feat/personalize-preview-modal`

---

## Phase 8 — Visual rebrand ✅ SHIPPED 2026-05-16

Full rebrand from generic "Website Downloader" to **"Kratos Clone — Website Downloader"** identity. Industrial-luxe aesthetic: dark heavy + vivid orange forge accent. Followed dev-workflow Alta complexity (spec at `docs/superpowers/specs/2026-05-16-ui-rebrand-orange-radial.md`); design by `frontend-design` skill + `ui-ux-designer` agent.

| Component | Landed in | Notes |
|-----------|-----------|-------|
| Brand wordmark | PR #32 | "KRATOS CLONE" — orange "CLONE" with text-shadow glow; descriptor per page |
| Display typography | PR #32 | Bricolage Grotesque via Google Fonts (variable, 500+700, `display=swap`) |
| Design token system | PR #32 | Full `:root` CSS custom properties; ink/orange scales, semantic colors, multi-layer shadows, 8px grid, durations, easing |
| Body radial atmosphere | PR #32 | Two-radial orange bloom over `--ink-base #0a0a14`, `background-attachment: fixed` |
| Highlight box on `/` | PR #32 | BETA chip + headline + orange CTA → `/personalize`; hover-lift + glow; inner `::before` bloom |
| Tips banner on `/personalize` | PR #32 | Collapsible `<details>` with 3 sections + localStorage flag; zero JS for toggle |
| Brief assist | PR #32 | "Carregar exemplo pronto" button + 3 icebreaker chips populating realistic ~250-char PT-BR briefs |
| Motion grammar | PR #32 | Page-load stagger (0/80/160/240ms), CTA pulse, `prefers-reduced-motion: reduce` guard |
| U6 connector fill direction fix | PR #32 (drive-by) | Was `(n-1)→n` → now `n→(n+1)` forward; caught via Playwright smoke pre-PR |

**Exit criteria met:** brand identity established + display font installed + token system in place + highlight box + tips + icebreakers + motion + a11y preserved (no regression in existing role/aria/landmark contracts). 257 → 266 tests. Playwright smoke screenshots in `/home/fbmoulin/rebrand-0[1-4]-*.png`.

**Out of scope (deferred):**
- Logo SVG mark (wordmark only)
- Light-mode toggle (dark-only)
- Web font self-host (using Google Fonts CDN with preconnect)
- Progress percentage on download (needs `downloader.py` instrumentation)
- SSE reconnect logic

---

## Out of scope (intentionally)

- ESLint/Prettier — no JS bundle; one inline script in `templates/index.html`. The `LintLogObservability` skill was correctly adapted to skip these.
- React migration — Flask + Jinja UI is sufficient for the operator-tool use case.
- Multi-page site cloning — current scope is single-URL marketing pages. Browsertrix Crawler is the right tool if multi-page is ever needed.
- Replacing `downloader.py` — keep it as-is for backward compat with the Flask UI; `kratos_clone/` is the new path. Eventual deprecation possible after Phase 5.

---

## Cumulative effort estimate

| Phase | Hours | Risk |
|-------|-------|------|
| 0 — doc honesty | 1h | Low — all writes |
| 1 — tests + factory | 6h | Low — well-bounded |
| 2 — fix structural bugs | 6h | Medium — Patch D refactor needs Playwright testing |
| 3 — prod hardening | 4h | Low |
| 4 — personalization MVP | 8h | Medium — first OpenAI integration in repo |
| 5 — pipeline completion | 5h | Low |
| 6 — devex polish | 3h | Low |
| 7 — UX audit U1–U9 + a11y P0 | ~8h | Low — well-bounded per-PR |
| 8 — visual rebrand | ~5h | Medium — broad surface area, mitigated by Playwright smoke |
| **Total shipped** | **~46h** | All phases complete |

Recommended order: 0 → 1 → 2 → 3 → 6 → 5 → 4 → 7 → 8 (personalization before UX polish; rebrand last on a stable foundation).
