# Roadmap — kratos-clone

Phased plan derived from `docs/AUDIT.md` (multi-agent audit, 2026-04-27) and the
proposed architecture in `docs/WORKFLOW.md` + `docs/PERSONALIZATION.md`.

> **Current state:** MVP capture + design-system extraction works end-to-end on
> NexusFlow-class Aura.build sites. 3 implementation flaws + zero unit tests + 3
> aspirational scripts not yet coded. See `TODO.md` for next-sprint actionable items.

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

## Phase 4 — Personalization MVP (~8h)

Implements `docs/PERSONALIZATION.md` as code.

| Item | New file | Effort |
|------|----------|--------|
| Slot extractor — augment `inventory.py` to emit `slots[]` array with `{id, selector, type, max_chars, structure?}` per personalizable element. | `scripts/inventory.py` (extension) | M ~2h |
| `personalize.py` CLI — Step 5 (gpt-5-mini + Vision, structured output) + Step 7 (BeautifulSoup patch applicator) | `scripts/personalize.py` | L ~3h |
| `gen_images.py` — Step 6 parallel gpt-image-1 generation with style reference | `scripts/gen_images.py` | M ~1.5h |
| Brief intake form — extend `templates/index.html` OR new `/personalize` route | `app.py` + `templates/personalize.html` | M ~1.5h |
| **Security hardening** — sanitize brief fields before LLM interpolation (use structured input not f-strings); DOM-parse + strip `<script>`/`on*`/`javascript:` from LLM HTML output; verify image magic bytes (PNG/JPEG only); strip EXIF | All of the above | (built into above) |

**Exit criteria:** End-to-end run on a real brief produces personalized HTML in <60s, <$1 per run. No prompt-injection vulnerability.

---

## Phase 5 — Pipeline completion (~5h)

Code the aspirational stages currently described only in `docs/WORKFLOW.md`.

| Item | New file | Effort |
|------|----------|--------|
| `scripts/probe.py` — Stage 1: HEAD + GET, framework detection, scroll-depth estimate, CSP summary → `probe.json` | `scripts/probe.py` | M ~1.5h |
| `scripts/post_process.py` — Stage 3: asset audit, scroll-fix strip wrapper, base64-inline of small assets | `scripts/post_process.py` | M ~1h |
| `scripts/validate.py` — Stage 6: coverage scorecard (driven by inventory NOT hardcoded), Playwright visual diff Hero source vs clone, asset reference resolution check, no-placeholder grep, WCAG contrast pass | `scripts/validate.py` | L ~2h |
| Drop the hardcoded scorecard from `generate_design_system_v2.py`; have it read `_inventory.json` to compute coverage dynamically. | `scripts/generate_design_system_v2.py` | S ~30m |

**Exit criteria:** Full 6-stage pipeline runnable; `scripts/validate.py` produces objective coverage measurement (not the current literal-driven 80.8 score).

---

## Phase 6 — DevEx + observability polish (~3h)

| Item | Effort |
|------|--------|
| Type hints on `app.py` (currently 0%); `mypy --strict kratos_clone/` in CI | M ~1.5h |
| `bandit -r` security lint job in CI | XS ~10m |
| Dependabot grouped weekly updates (`.github/dependabot.yml`) | XS ~10m |
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
