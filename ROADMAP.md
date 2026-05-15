# Roadmap — kratos-clone

Phased plan derived from `docs/AUDIT.md` (multi-agent audit, 2026-04-27) and the
proposed architecture in `docs/WORKFLOW.md` + `docs/PERSONALIZATION.md`.

> **Current state (2026-05-10):** All 6 phases shipped. Personalization MVP
> live (gpt-5-mini Responses + gpt-image-1, hard budget cap, sanitize hardened).
> All 9 P1 + all 12 P2 audit items closed. mypy strict on every source file.
> Pre-deploy audit completed (PR #21 merged): both BLOCKERs fixed, urllib3 CVE
> bumped. See `TODO.md` for opportunistic follow-ups and
> `docs/PRE_DEPLOY_AUDIT_2026-05-10.md` for the remaining MAJOR/MINOR backlog.

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
| **Total** | **~33h** | |

Recommended order: 0 → 1 → 2 → 3 → 6 → 5 → 4 (personalization last so the foundation is solid).
