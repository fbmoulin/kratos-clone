# Handoff — kratos-clone (2026-04-27)

> ### 📍 Looking for the CURRENT session handoff? It is not this file.
>
> **`docs/handoff/2026-08-02-ci-unblock.md`** — plus its resumption prompt at
> `docs/handoff/2026-08-02-ci-unblock-prompt.md`. Start there.
>
> This file is a **standing project reference**, kept current for the sections it
> owns (CI pipeline, required checks, `/health` build identity, branch protection,
> conventions). It is *not* a session log, and its 2026-04-27 title reflects when it
> was first written, not how fresh its contents are.

> Snapshot for the next Claude Code session (or any new contributor) joining
> after a `/clear`. Tells you exactly what's done, what's next, and how to
> pick up without re-reading the full conversation history.

> **📌 Update 2026-05-10** — this doc is a historical snapshot. Since it was
> written, Phases 4 (Personalization MVP), 5 (Pipeline completion), and 6
> (DevEx polish) all shipped, all 12 P2 audit items closed, mypy strict
> coverage reached every source file, and a pre-deploy audit (PR #21) landed
> with both BLOCKERs fixed + urllib3 CVE bumped. Current authoritative
> state lives in `ROADMAP.md` (phase log), `TODO.md` (open work), and
> `docs/PRE_DEPLOY_AUDIT_2026-05-10.md` (deploy backlog). Test count is now
> **210 passed + 2 skipped**, not the 74 below.

---

## TL;DR

`kratos-clone` is a fork of `asimov-academy/Website-Downloader` extended with a
hardened Playwright capture module, a DTCG design-system extractor, an
observability layer, and an OpenAI-driven personalization spec (last one not
yet implemented). **All 9 P1 audit findings closed across 3 sprint phases
(2026-04-27). 74 pytest cases green. CI: 5 jobs (lint, smoke, pytest, pip-audit,
+2 bot reviewers).** No P0 ever existed; 8 P2 items remain open in the audit
backlog.

---

## Where everything is

| Aspect | Value |
|--------|-------|
| Repo | https://github.com/fbmoulin/kratos-clone (public) |
| Local path | `/home/fbmoulin/Website-Downloader/` |
| Default branch | `main` (protected — PR + status checks required, admin bypass available) |
| Working tree | clean as of 2026-04-27 |
| Open PRs | none |
| Open branches | none (all merged) |
| Last commit on `main` | `9f4c453 — feat: Phase 3 — production hardening` |
| Upstream remote | `upstream` → `asimov-academy/Website-Downloader` (read-only, for `git fetch upstream main` to pull future fixes) |
| Authority docs | `docs/AUDIT.md` (state of the codebase), `ROADMAP.md` (7 phases, ~33h cumulative), `TODO.md` (next-sprint actionable), `CLAUDE.md` (project-specific guidance) |

---

## What was shipped (5 commits on `main`, in order)

| SHA | Phase | Summary |
|-----|-------|---------|
| `c3e2c90` | (initial fork+features) | kratos_clone capture module · scripts/ generators · docs/PROMPT_v2 + WORKFLOW + PERSONALIZATION |
| `02b32df` | (chore) | MIT LICENSE + NOTICE attribution + first CI (ruff lint + smoke) |
| `d4f7e99` | (observability) | structlog backend · `/api/client-errors` · inline browser logger (sendBeacon batching) |
| `885fee0` | **Phase 0** | doc honesty pass — README rewrite + AUDIT + ROADMAP + TODO + CLAUDE.md |
| `b54939a` | **Phase 1** | `create_app()` factory pattern (no side effects on `import app`) + 52-case pytest suite |
| `ea6cf1a` | **Phase 2** | 5 P1 structural fixes (Patch D shadow walker · asset write race · semantic generators · same-origin · iframe srcdoc length compare) |
| `9f4c453` | **Phase 3** | production hardening (gunicorn CVE · content-type 415 · client-side PII strip · ANSI sanitize · disk caps · scroll budget · BS4 rewrite · Flask-Limiter · pip-audit) |

---

## Audit status — `docs/AUDIT.md`

| Severity | Total | Resolved | Open |
|----------|-------|----------|------|
| **P0** | 0 | — | — |
| **P1** | 9 | **9 (all)** | 0 |
| P2 | 12 | 4 (P2-3, P2-4, P2-5, P2-6) | 8 |
| P3 | ~13 | — | ~13 |

### Remaining P2 (Phase 6 candidates, ~3-4h total)
- P2-1 — `asset_filename` extension regex tightening (defensive only; no traversal)
- P2-2 — already resolved Phase 3 (`KCD_MAX_SCROLL_S`)
- P2-7 — already resolved Phase 1 (factory pattern)
- P2-8 — DTCG coverage scorecard is hardcoded (drive from inventory in Phase 5)
- P2-9 — "+70%" claim still unmeasured (need A/B harness)
- P2-10 — "+6650% CSS" attribution (already softened in WORKFLOW.md, can clarify further)
- P2-11 — PERSONALIZATION.md prompt-injection handling (Phase 4 will implement)
- P2-12 — authenticated-response capture should redact (Phase 6)

### P3 (Phase 6 — quality polish)
type hints on `app.py` (currently 0%) · `mypy --strict` in CI · `bandit -r` · Dependabot grouped weekly · `request_id` middleware · `[tool.ruff]` section · KCD_* env-var README table.

---

## Test inventory — `tests/`

```
tests/
├── __init__.py
├── conftest.py                    # flask_app + client fixtures via create_app(side-effect-free)
├── test_post.py                   # 19 cases — rewrite_html_assets + strip_scroll_fix + P1-F regressions
├── test_capture_helpers.py        # 16 cases — asset_filename + hash_url + WCAG contrast (inline)
├── test_client_errors.py          # 29 cases — /api/client-errors happy + RFC 9110 + content-type + ANSI + PII
└── test_generator_helpers.py      # 10 cases — find_button_by_classes semantic lookup
```

Total: **74 cases · 0.77s local · 18s CI**

### How to run
```bash
cd /home/fbmoulin/Website-Downloader
uv run pytest tests/ -q          # all
uv run pytest tests/test_post.py -v  # specific file
```

---

## CI pipeline — `.github/workflows/ci.yml`

| Job | Time | Purpose |
|-----|------|---------|
| Lint (ruff) | ~5s | `ruff check + ruff format --check` on `kratos_clone/`, `scripts/`, `app.py` |
| Import + module smoke test | ~13s | factory pattern verified (`threading.active_count()` unchanged on `import app`); /api/client-errors registered; `create_app()` returns module-level app |
| pytest | ~18s | full 74-case suite |
| pip-audit (CVE scan) | ~29s | osv vulnerability service, soft gate (`\|\| true`) — flip to strict in Phase 6 |
| CodeRabbit | ~10s | auto-review on every PR (3rd-party bot installed at user level) |
| Code Review Doctor | ~5s | auto-review on every PR (3rd-party bot) |

**4 of the 9 jobs are required-status-checks**, via repo ruleset (`Protect main`, ruleset id
`15582219`), as of 2026-08-02:

- `Lint (ruff)`
- `Import + module smoke test`
- `mypy (…)` — added 2026-08-02
- `pytest (kratos_clone + post + client_errors)` — added 2026-08-02

`bandit`, `pip-audit`, `render-live`, `uv.lock ⇄ pyproject.toml sync`, `docker image build +
smoke` and the `forward-compat` canary run on every PR but gate nothing. (The lock-sync job was
called `requirements.txt ⇄ uv.lock sync` until 2026-08-03; renaming it was safe precisely
because it is not a required context — a required context that never arrives blocks every PR
forever, which is why the `mypy` job's name must NOT be touched without updating the ruleset.)

**The container installs from `uv.lock`, not from a committed `requirements.txt`** (removed
2026-08-03). The `Dockerfile` runs `uv sync --locked --no-dev` into `/app/.venv` and puts that
venv on `PATH`. Operator consequence: `docker exec <c> pip install X` is a silent no-op, because
`pip` still resolves to the system Python while `python` resolves to the venv. Use
`docker exec <c> uv pip install --python /app/.venv/bin/python X`. Until 2026-08-02 only the first two were required, which
is why `mypy` could stay red on `main` from 2026-06-29 onward while every PR opened in that window
inherited the failure and remained mergeable.

`strict_required_status_checks_policy` is deliberately **false**: enabling it would force every
dependabot branch to be brought up to date with `main` before it could merge, turning each push to
`main` into a rebase round for every open PR.

`bypass_actors: RepositoryRole id=5, bypass_mode=always` — the repository owner bypasses the
ruleset entirely, so all four checks remain advisory for that account.

> ### 🔴 The `mypy` context string is TRUNCATED — do not retype it from `ci.yml`
>
> The `mypy` job's `name:` in `ci.yml` is **114 characters**. GitHub truncates emitted check-run
> names at **98**, ending in a literal `...`. The ruleset context must be the *emitted* 98-char
> string, not the declared one.
>
> This fails silently and expensively: a context that never matches an emitted check does not
> error — it creates a required check that never arrives, so **every PR blocks forever** waiting
> for it. Read the emitted names, never the declared ones:
>
> ```bash
> gh api repos/fbmoulin/kratos-clone/commits/main/check-runs -q '.check_runs[] | "\(.name|length)|\(.name)"'
> ```
>
> Consequence: **renaming the `mypy` job breaks the required check.** If you shorten that name
> below 98 characters the truncation disappears, the context stops matching, and `main` blocks.
> Update the ruleset in the same change, and verify afterwards that an open PR reports
> `MERGEABLE/CLEAN` rather than `BLOCKED`.

---

## Proving which build is answering — `/health` `build_sha`

`GET /health` returns `build_sha`. A 200 alone proves a process is alive, not that it
runs the commit you believe you deployed: an image can be rebuilt under the same tag,
`docker compose up -d` declines to re-pull when the tag already exists locally, and a
failed deploy leaves the previous release serving. All keep answering 200 from stale
code. Read `build_sha`, never the image tag or a version string — a stale image under a
fresh tag makes label and code lie in the same direction.

Resolution order, first non-blank wins (`app.py:_resolve_build_sha`):

1. `KC_BUILD_SHA` — injected by our `Dockerfile` from the `GIT_SHA` build arg
2. `RENDER_GIT_COMMIT` — injected by Render at runtime
3. `RAILWAY_GIT_COMMIT_SHA` — injected by Railway at runtime
4. `"unknown"` — nothing resolved

**`"unknown"` is a finding, not a default.** It means the running process cannot identify
its own commit, so no measurement taken against that instance is trustworthy.

**Build the image so the field is populated:**

```bash
docker build --build-arg GIT_SHA="$(git rev-parse HEAD)" -t kratos-clone .
```

Measured 2026-08-02: omitting `--build-arg` sets `KC_BUILD_SHA` to the **empty string**,
not to an unset variable — which is why the resolver treats blank as unresolved and falls
through. A runtime `-e KC_BUILD_SHA=...` overrides the baked value without a rebuild.

The value is read per request, never cached at import: a cached value would describe the
build that imported the module, which is the same stale-label bug the field exists to
detect. `tests/test_health_build_sha.py` pins all of the above.

---

## Architecture key facts

### Two coexisting capture paths
- `downloader.py` — original upstream module, synchronous Playwright, **still used by Flask UI** at `http://localhost:5001`
- `kratos_clone/` — new hardened async Playwright module with 5 patches (A=IO pre-fire, B=DOM-stable+networkidle, C=3-pass scroll, D=shadow walker fixed in Phase 2, E=computed-style snapshot). Invoke via `python -m kratos_clone <url>`

> ⚠️ **For new code: always touch `kratos_clone/`, NEVER `downloader.py`.**
> Domain-explorer agent in the audit got confused about this.

### Factory pattern (Phase 1)
- `app.py` keeps `app = Flask(__name__)` at module level so `@app.route` decorators work
- Side effects (cleanup_downloads_folder, janitor thread, limiter.init_app) are gated inside `create_app(start_janitor=True, run_boot_cleanup=True)`
- Production: `gunicorn wsgi:app` (wsgi.py calls `create_app()`)
- Dev: `python app.py` (the `__main__` block calls `create_app()` then `app.run`)
- Tests: `from app import app, create_app, _reset_state; create_app(start_janitor=False, run_boot_cleanup=False)` via fixture

### Branch protection
Ruleset `15582219` on `main`:
- Block direct push (deletion, non-fast-forward, requires PR)
- Squash or rebase merge only
- Required status checks: `Lint (ruff)`, `Import + module smoke test`, `pytest (...)`, `pip-audit (CVE scan)`
- Admin (Felipe) can bypass via `gh pr merge --admin <PR#>` for emergencies

---

## Critical context the next session must know

### Conventions (from `~/.claude/CLAUDE.md` global)
1. **Sole-author commits.** NEVER add `Co-Authored-By: Claude...` trailers.
2. **Use `uv add <pkg>`**, NEVER `pip install`. Dev deps go in `[dependency-groups] dev`.
3. **structlog kwargs only**: `logger.info("event_name", k=v)`, NEVER `logger.info(f"...{x}")`.
4. **Run `ruff check && ruff format --check`** before push. CI hard-gates on it.
5. **Run `pytest -q`** before push. CI runs the full suite.

### Project-specific (from `CLAUDE.md`)
1. New code lives in `kratos_clone/`. Don't touch `downloader.py`.
2. RFC 9110 §15.3.5: 204 responses MUST have empty body. Use `return ("", 204)`, NOT `return jsonify(...), 204`.
3. Browser logger MUST capture `_rawFetch = window.fetch.bind(window)` BEFORE wrapping fetch (feedback loop avoidance — caught by CodeRabbit in PR #1).
4. Generators (`scripts/generate_design_system_v{1,2}.py`) use `find_button_by_classes()` semantic lookup (Phase 2 fix). Don't reintroduce hardcoded indices.
5. Capture flags via `KCD_*` env vars (see `CaptureConfig` dataclass in `kratos_clone/capture.py`).

### Gotchas to remember
- **Flask-Limiter `MemoryStorage` spawns a thread on `init_app()`** with the default `memory://` URI. Lazy-init inside `create_app()` keeps `import app` side-effect-free (caught by smoke test in PR #5).
- **`cloneNode(true)` does NOT copy shadow roots** per HTML spec. Patch D's earlier impl was a no-op for months. Now walks live DOM (Phase 2).
- **Playwright async event handlers are fire-and-forget**: `page.on("response", async_handler)` does NOT await. Tracked via `asyncio.create_task` + `asyncio.gather` before `context.close()` (Phase 2 P1-B).
- **Adversarial review caught a "security theater" claim**: P1-I server-side `_strip_query()` doesn't actually close the leak (URL traverses network with query). The real fix is client-side (`templates/index.html:_safeUrl`). Lesson: always question whether a fix actually closes the threat at the right layer.

---

## Phase 4 — what's next (DO NOT START WITHOUT EXPLICIT APPROVAL)

**Personalization MVP** — first real OpenAI integration in the repo. ~8h. Spec lives at `docs/PERSONALIZATION.md` (which is currently SPEC ONLY — not implemented).

Required before starting:
1. `OPENAI_API_KEY` configured (env var or `.env`, gitignored)
2. Cost budget (~$0.32/run forecast with 3 images; ~$0.05/run text-only as measured in Phase 4 live test 2026-04-27; $1 hard cap recommended in code)
3. Decision: where does brief intake live? (extending `templates/index.html` vs new `/personalize` route)

8 implementation steps from `docs/PERSONALIZATION.md`:
1. Brief intake (UI form: textarea + logo upload + optional brand color)
2. Brief structuring (gpt-5-mini, 1 call, ~$0.005)
3. User confirmation (UI editable form)
4. Slot extraction — extend `scripts/inventory.py` to emit `slots[]` with `{id, selector, type, max_chars, structure?}` per personalizable element (~80 lines)
5. Personalize call (gpt-5-mini Vision + `text.format: json_schema strict=True`)
6. Image generation (gpt-image-1 medium, parallel, with style reference)
7. Apply patches (BeautifulSoup + regex on Tailwind color classes)
8. Output `personalized.html` + zipped delivery

**Security must-have at implementation time** (audit P2-11):
- Sanitize brief fields BEFORE LLM interpolation (use structured input, not f-strings)
- DOM-parse + strip `<script>`, `on*=`, `javascript:` from LLM HTML output before write
- Verify image magic bytes (PNG/JPEG only, NEVER SVG due to embedded XSS)
- Strip EXIF from uploaded logos
- NO synthetic faces for testimonials (EU AI Act + OpenAI usage policies)

---

## Quick-start for next session

```bash
# 1. Activate
cd /home/fbmoulin/Website-Downloader
source .venv/bin/activate  # or use `uv run` for everything

# 2. Verify state
git status                    # should be clean on main
git log --oneline -5          # latest is 9f4c453 Phase 3
uv run pytest -q              # 74 passed in <1s

# 3. Run anything
uv run python -m kratos_clone https://example.com --output-dir ./capture
uv run python app.py          # dev server :5001
gunicorn wsgi:app             # production simulation

# 4. New feature work — follow PR pattern
git checkout -b feat/your-thing
# ... edits + tests ...
uv run ruff check + format
uv run pytest -q
git commit -m "..."           # NO Co-Authored-By
git push -u origin feat/your-thing
gh api -X POST repos/fbmoulin/kratos-clone/pulls -f title=... -f head=... -f base=main -f body=...
gh pr checks <N> --watch
gh pr merge <N> --squash --delete-branch
```

---

## Memory locations

- **This handoff**: `docs/HANDOFF.md` (in repo, persisted across sessions)
- **Auto-memory mirror**: `~/.claude/projects/-home-fbmoulin/memory/handoff_kratos-clone_2026-04-27.md` (loaded by Claude on session start)
- **Audit findings**: `docs/AUDIT.md`
- **Phased plan**: `ROADMAP.md` (7 phases)
- **Active backlog**: `TODO.md`
- **Project guidance**: `CLAUDE.md`
- **Architecture specs**: `docs/PROMPT_v2.md`, `docs/WORKFLOW.md`, `docs/PERSONALIZATION.md`

---

## Multi-agent review log (for posterity)

PR #1 (observability): CodeRabbit + Gemini caught 8 issues — feedback-loop bug, AttributeError on list-body, structlog logger name lost, RFC 9110 violation, level whitelist gap. All addressed before merge.

PR #5 (Phase 3): security-reviewer caught **P1: ProxyFix needed** (rate limit defeated by reverse proxy). adversarial-critic caught **P1: P1-I "RESOLVED" was security theater** (server-side strip too late) + asset_write_failed silent + first-drop warning missing. All 6 legitimate findings fixed before merge. 1 informational deferred (C1 control char extension).

**Lesson**: bot reviewers + parallel specialized agents catch real bugs. Always run them before merging non-trivial changes.

---

## Pending non-Phase questions for next session

1. Tag a `v0.1.0` release? Phase 3 closing all P1 is a natural milestone.
2. Implement Stage 6 `validate.py` (visual diff + DTCG scorecard from data, not literal) — Phase 5 work.
3. Recharge `OPENAI_API_KEY` budget before Phase 4 (~$1-5 for testing).
4. Document `KCD_*` env vars in README table (P3 polish, ~15 min).
5. Consider Dependabot grouped weekly updates config.
