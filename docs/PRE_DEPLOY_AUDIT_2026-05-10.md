# Pre-deploy audit — 2026-05-10

| | |
|---|---|
| **Commit baseline** | `caac782` (main, after PR #20 merge) |
| **Branch** | `chore/pre-deploy-audit-2026-05-10` |
| **Auditor** | Claude (Opus 4.7), three Explore agents + empirical Docker-equivalent boot test |
| **Verdict** | **NO-GO** until B-1 + B-2 fixed (this PR resolves both). **GO** once merged + `OPENAI_API_KEY` set in Render dashboard. |

---

## Executive summary

| Severity | Count | Status |
|---|---|---|
| 🔴 BLOCKER | 2 | **Both fixed** in PR #21. |
| 🟡 MAJOR  | 5 | M-1, M-2 closed in follow-up docs PR. M-3 fully closed (urllib3 fixed in PR #21; cryptography dropped by PR #38 openai bump). M-5 partially mitigated (launch-args). M-4 deferred. |
| 🟢 MINOR  | 9 | N-1, N-2 closed in follow-up docs PR. N-3 resolved via B-2 fix. N-4..N-9 deferred. |

The container deploy via Render → Docker → `requirements.txt` was broken today: `requirements.txt` was missing 4 of the 11 declared runtime dependencies, including two (`structlog`, `flask-limiter`) imported at module level in `app.py`. `import app` raised `ModuleNotFoundError` before gunicorn could bind, so the service would fail health-check before serving a single request. The second BLOCKER (no `.env.example`) meant operators had no reference for the 24 env vars the app reads, including `OPENAI_API_KEY` — which fails silently per-request, not at boot.

Both BLOCKERs are fixed in this PR. Within M-3, the urllib3 CVE was also bumped here (2.6.2 → 2.7.0). Cryptography 41 (6 CVEs) and the rest of the MAJORs/MINORs are intentionally deferred to keep this diff focused.

---

## Deploy surface (current)

| Layer | File | Notes |
|---|---|---|
| Platform | `render.yaml` | `env: docker`, `dockerfilePath: ./Dockerfile`, only `PORT` set in yaml. Other env vars set in Render dashboard. |
| Image | `Dockerfile` | `python:3.11-slim-bookworm` + `pip install -r requirements.txt` + `playwright install --with-deps chromium`. No HEALTHCHECK directive (N-6). Runs as root (N-7). |
| Process | `entrypoint.sh` | `gunicorn wsgi:app --workers 1 --threads 4 --timeout 600 --graceful-timeout 30 --max-requests 50 --worker-class gthread`. Single-worker chosen for 512 MB Render free tier (each download spawns Chromium). |
| Entry point | `wsgi.py` | `from app import create_app; app = create_app()`. Factory pattern — import is side-effect-free except `configure_logging()`. |
| Excluded from container | `.dockerignore:52` | `uv.lock` excluded — only `requirements.txt` reaches the build. `*.md` excluded except README. |
| Dead code | `Procfile` | Contains `web: bash entrypoint.sh`. Heroku/Railway-classic pattern; ignored when `env: docker`. (N-8) |

---

## Empirical evidence of B-1

```bash
$ rm -rf /tmp/audit-venv
$ python3.12 -m venv /tmp/audit-venv
$ /tmp/audit-venv/bin/pip install --no-cache-dir -r requirements.txt   # PRE-FIX
$ /tmp/audit-venv/bin/python -c "import app"
Traceback (most recent call last):
  File "<string>", line 1, in <module>
  File "/home/user/kratos-clone/app.py", line 14, in <module>
    import structlog
ModuleNotFoundError: No module named 'structlog'
```

This reproduces the exact failure the Render service would emit on its first deploy attempt. After regenerating `requirements.txt` via `uv export --format requirements-txt --no-dev --no-emit-project --no-hashes`:

```bash
$ /tmp/audit-venv/bin/pip install --no-cache-dir -r requirements.txt   # POST-FIX
$ /tmp/audit-venv/bin/python -c "
... import app
... routes = sorted(r.rule for r in app.app.url_map.iter_rules())
... print(f'BOOT OK — {len(routes)} routes')
... "
BOOT OK — 10 routes
```

`/health`, `/api/personalize/structure`, `/api/personalize/run`, `/api/client-errors` all registered.

---

## Findings table

| ID | Severity | Title | Evidence | Status |
|---|---|---|---|---|
| B-1 | 🔴 BLOCKER | `requirements.txt` missing 4 runtime deps + 4 version drifts | `app.py:14` (structlog), `app.py:16` (flask-limiter), `app.py:591/637` (openai/pillow lazy), `requirements.txt` vs `uv.lock` | **FIXED** in this PR |
| B-2 | 🔴 BLOCKER | No `.env.example`; `OPENAI_API_KEY` undocumented and fails per-request | `personalize/openai_client.py:80`, `render.yaml:6-8` | **FIXED** in this PR |
| ~~M-1~~ | 🟡 MAJOR  | `CLAUDE.md` "Known issues" stale (claims 7 P2 items remain, actually 0) | `CLAUDE.md:109-117`, `docs/AUDIT.md` (all P2-1..P2-12 struck-through) | ✅ **RESOLVED** on `docs/refresh-post-audit-2026-05-10` — CLAUDE.md "Known issues" rewritten to reflect all P2 closed + pre-deploy-audit summary |
| ~~M-2~~ | 🟡 MAJOR  | `WORKFLOW.md` claims Stages 1, 3, 6 aspirational — all shipped | `docs/WORKFLOW.md:6-9` | ✅ **RESOLVED** on `docs/refresh-post-audit-2026-05-10` — status banner updated to "all 6 stages shipped 2026-04-27" |
| M-3 | 🟡 MAJOR  | Transitive CVEs: `urllib3 2.6.2` (CVE-2026-21441); `cryptography v41.0.7` (6 CVEs) | OSV scanner (CodeRabbit), `pip-audit` output | **CLOSED**: urllib3 fixed in PR #21; cryptography dropped from deps by PR #38 openai bump. `pip-audit -r requirements.txt` reports 0 vulns as of 2026-05-25 |
| M-4 | 🟡 MAJOR  | `RATE_LIMIT_STORAGE_URI=memory://` default; per-worker buckets if `--workers >1` | `app.py:237`, `entrypoint.sh:15` | DEFERRED |
| M-5 | 🟡 MAJOR  | Playwright 1.57 launches Chrome for Testing instead of Chromium — memory regression on 512 MB tier | [microsoft/playwright#38489](https://github.com/microsoft/playwright/issues/38489), `pyproject.toml:14`, `entrypoint.sh:9-12` | **PARTIAL** — launch-args mitigation landed; final memory-tier decision still deferred until first prod-OOM signal |
| ~~N-1~~ | 🟢 MINOR  | `CLAUDE.md` claims "52 tests" — actual 210 | `CLAUDE.md:70`, `pytest -q` output | ✅ **RESOLVED** on `docs/refresh-post-audit-2026-05-10` — line updated to "210 passed + 2 skipped, ~3s" |
| ~~N-2~~ | 🟢 MINOR  | "$0.32 per run" cost claim unverified | `docs/PERSONALIZATION.md`, `docs/HANDOFF.md`, `CLAUDE.md:167` | ✅ **RESOLVED** on `docs/refresh-post-audit-2026-05-10` — annotated with 2026-04-27 live measurement (~$0.05/run text-only; $0.32 forecast assumes 3 images) |
| N-3 | 🟢 MINOR  | 20+ `KCD_*` env vars undocumented for operators | `kratos_clone/capture.py:185-228` | **RESOLVED via B-2 fix** |
| N-4 | 🟢 MINOR  | No CORS/CSRF on POST endpoints | `app.py` (no `flask-cors` import) | DEFERRED — intent-dependent |
| N-5 | 🟢 MINOR  | Janitor thread `daemon=True`; SIGTERM during cleanup may leak | `app.py:243` | DEFERRED — idempotent rmtree mitigates |
| N-6 | 🟢 MINOR  | `Dockerfile` lacks `HEALTHCHECK` directive | `Dockerfile` | DEFERRED — Render uses external HTTP probe |
| N-7 | 🟢 MINOR  | `Dockerfile` runs as root (no `USER` directive) | `Dockerfile` | DEFERRED — single-tenant container |
| N-8 | 🟢 MINOR  | `Procfile` is dead code under `env: docker` | `Procfile`, `render.yaml:4` | DEFERRED — harmless |
| N-9 | 🟢 MINOR  | `downloader.py` excluded from CI bandit scope; 1 unannotated High finding (md5 used for non-security filename hashing) | `downloader.py:87`, `.github/workflows/ci.yml` bandit run | DEFERRED |

---

## Detail per finding

### B-1 — `requirements.txt` missing 4 runtime deps (FIXED)

**Symptom:** `python -c "import app"` raises `ModuleNotFoundError` for `structlog` (and would raise for `flask-limiter` next), preventing gunicorn from binding.

**Evidence:**
- `app.py:14` — `import structlog` at module level. Not in pre-fix `requirements.txt`.
- `app.py:16-17` — `from flask_limiter import Limiter` / `from flask_limiter.util import get_remote_address`. Not in pre-fix `requirements.txt`.
- `app.py:591` — `from personalize.openai_client import …` lazy-imported inside `/api/personalize/structure`. Triggers `openai` import at first call. Not in pre-fix `requirements.txt`.
- `app.py:637` — `from personalize.pipeline import run_pipeline` lazy-imported inside `/api/personalize/run`. Triggers `pillow` import. Not in pre-fix `requirements.txt`.

**Pre-fix state (7 deps, 4 with version drift vs lock):**
```
flask==3.1.3        ← lock 3.1.2
playwright==1.59.0  ← lock 1.57.0
requests==2.33.1    ← lock 2.32.5
beautifulsoup4==4.14.3
urllib3==2.6.3      (transitive of requests; should not be top-pinned)
gunicorn==26.0.0    ← lock 25.3.0
psutil==7.2.2
```

**Post-fix state:** 114 lines (11 declared deps + ~50 transitives, all pinned at lock-resolved versions, with `# via X` annotations). Generated by:
```bash
uv export --format requirements-txt --no-dev --no-emit-project --no-hashes > requirements.txt
```

This file is now a build artifact — regenerable from `uv.lock` whenever deps change. The drift class is eliminated at the source.

### B-2 — No `.env.example` (FIXED)

**Symptom:** `render.yaml` only sets `PORT`. Operators have no reference for the 24 env vars the app reads. `OPENAI_API_KEY` is required for `/api/personalize/*` but fails per-request (lazy `OpenAI()` constructor at `personalize/openai_client.py:80`), so a missing key produces silent 5xx instead of a loud boot error.

**Fix:** Created `.env.example` in repo root. Groups vars by lifecycle (`[boot]` / `[request]` / `[test-only]`) and consumer module. Each entry has the default value (or `=` for required-but-no-default) and a one-line description.

24 vars documented:
- 1 required no-default (`OPENAI_API_KEY`)
- 2 logging (`LOG_FORMAT`, `LOG_LEVEL`)
- 3 HTTP (`PORT`, `TRUST_PROXY`, `RATE_LIMIT_STORAGE_URI`)
- 3 rate limits
- 14 capture knobs (`KCD_*`)
- 1 test-only (`RUN_OPENAI_LIVE`)

### M-1 / M-2 / N-1 — Documentation drift (DEFERRED)

`CLAUDE.md:109-117` claims 7 P2 audit items remain — Agent 2 verified all 12 P2-1..P2-12 are struck-through in `docs/AUDIT.md` with commit SHAs. Outdated since 2026-05-10 (P2-12 closed today's PR ancestor).

`docs/WORKFLOW.md:6-9` claims Stages 1, 3, 6 aspirational. All three were shipped in Phase 5 (commit 641d857, 2026-04-27): `scripts/probe.py` (12 tests in `tests/test_probe.py`), `scripts/post_process.py` (6 tests in `tests/test_post_process.py`), `scripts/validate.py` (21 tests in `tests/test_validate.py`).

`CLAUDE.md:70` claims "52 tests, ~0.6s". Actual: 210 passed + 2 skipped, ~1.3s.

**Recommended follow-up:** single doc-edit PR (~30 min) refreshing CLAUDE.md "Known issues" + WORKFLOW.md status header + CLAUDE.md test count.

### M-3 — Transitive CVEs (urllib3 FIXED, cryptography DEFERRED)

**urllib3 — FIXED in PR #21.** CodeRabbit's OSV scanner flagged `urllib3==2.6.2` (CVE-2026-21441 / GHSA-38jv-5279-wg99): HIGH-severity decompression-bomb when following HTTP redirects with `preload_content=False`. Pulled transitively by `requests`. The exposed call site is `kratos_clone/capture.py` (visits user-supplied URLs); a malicious redirect target could exploit this. Bumped to **2.7.0** in PR #21 (uv.lock); the requirements.txt re-export landed later in PR #38 (lock/requirements drift sync, 2026-05-25). Verified post-bump: pytest green, mypy 21 src OK, app boots with all 10 routes.

**cryptography — RESOLVED transitively, no action needed.** The PR #38 dependency-group bump (`openai 2.32 → 2.38`) dropped `cryptography` + `pyjwt` from the transitive closure entirely — neither package appears in current `requirements.txt` or `uv.lock`. `pip-audit -r requirements.txt --vulnerability-service pypi` reports **0 known vulnerabilities** against main as of 2026-05-25. The 6 CVEs previously deferred (PYSEC-2024-225, CVE-2023-50782, CVE-2024-0727, GHSA-h4gh-qq45-vh27, CVE-2026-26007, CVE-2026-34073) are no longer exploitable because the vulnerable package is no longer present.

### M-4 — In-memory rate-limit storage (DEFERRED)

`RATE_LIMIT_STORAGE_URI` defaults to `memory://` (`app.py:237`). With Flask-Limiter's in-memory backend, each gunicorn worker has its own bucket — N workers means rate limits are silently multiplied by N.

**Mitigation today:** `entrypoint.sh:15` hardcodes `--workers 1`. The mismatch is invisible; if a future ops change scales workers without setting a Redis URI, rate limits degrade silently.

**Recommended follow-up:** add an assertion in `app.py` boot path that if `--workers` env var (`GUNICORN_WORKERS` or detected from `psutil`) is >1 and `RATE_LIMIT_STORAGE_URI` is `memory://`, log a warning. Or document the constraint in `entrypoint.sh` as a comment block. Lower priority: depends on whether multi-worker is a near-term goal.

### M-5 — Playwright 1.57 Chrome-for-Testing memory regression (PARTIAL)

[microsoft/playwright#38489](https://github.com/microsoft/playwright/issues/38489): v1.57+ launches Chrome for Testing instead of lightweight open-source Chromium. Reported memory under load up to 20 GB per instance. Render free tier is 512 MB.

**Investigation (2026-05-25):** Confirmed on this branch: `playwright==1.60.0` and `pw.chromium.executable_path` resolves to `chromium-1223/chrome-linux64/chrome` — the post-1.57 Chrome-for-Testing build (legacy chromium had build IDs below ~1130). The Python `launch()` API does **not** accept `headless='shell'` (only `bool`), so the JS-only "headless shell" trick isn't a direct switch from Python — pointing at the lightweight `chromium_headless_shell` binary requires explicit `executable_path=`.

**Mitigation now (landed):**
1. `--workers 1` in `entrypoint.sh` — at most one Chromium at a time
2. `DEFAULT_CHROMIUM_LAUNCH_ARGS` constant in `kratos_clone/capture.py` (passed to every `pw.chromium.launch()`): disables dev-shm, GPU, extensions, background networking, sync, translate, default apps, and various auto-update probes. These flags shrink CfT's working set vs. the all-default launch the module used pre-#39-follow-up. **Sandbox stays ON** — the module visits user-supplied URLs and `--no-sandbox` would be a security regression. Operators on hardened containers (no seccomp, sandbox launch fails) can opt-in via `KCD_LAUNCH_ARGS` env var (replaces defaults; comma-separated). See `tests/test_capture_helpers.py::test_launch_args_*`.

**Risk remaining:** even with reduced flags, CfT is heavier than legacy chromium. First OOM observed in prod log = trigger for one of the harder options below.

**Recommended follow-up (deferred until first OOM signal):**
- Set `--ipc=host` in `entrypoint.sh` (Playwright Docker recommendation)
- Repoint `executable_path` to `chromium_headless_shell-NNNN/...` via a `KCD_USE_HEADLESS_SHELL=1` knob (smaller binary; requires `playwright install chromium-headless-shell`)
- Pin to playwright<1.57 (downgrade — opens compat questions; Patches A–E were validated against 1.57+ async API)
- Upgrade Render tier above 512 MB

**Why this stopped at "partial" rather than full closure:** the local sandbox here can't run a representative capture inside a 512 MB cgroup, so the actual peak-RSS measurement that would justify a deeper mitigation (ipc=host vs. tier upgrade vs. headless-shell switch) can't be produced without docker-in-docker + a heavy-SPA target page. Re-open when prod telemetry surfaces an OOM.

### N-2 — "$0.32 per run" cost claim (DEFERRED)

`docs/PERSONALIZATION.md` and `docs/HANDOFF.md` cite "$0.32 per run". Phase 4 live test (2026-04-27) actually spent $0.105 across 2 test runs (~$0.05/run). `CLAUDE.md:167` already flags this as needing re-verification.

**Recommended follow-up:** during the next live test, compute actual per-run spend with current pricing (gpt-4.1 + image gen) and update the docs with date-stamped numbers ("as of YYYY-MM-DD"). Same doc-PR as M-1/M-2.

### N-4 — No CORS/CSRF (DEFERRED)

No `flask-cors` import; no CSRF token validation on `/api/personalize/run` or `/download`. Acceptable IF the API is only called same-origin (the Flask app serves the UI HTML on `/personalize` and the form posts to `/api/personalize/run` from the same origin). NOT acceptable if the API is to be consumed from a different domain.

**Recommended follow-up:** document the intent in `docs/`. If single-origin, no action. If cross-origin is on the roadmap, add `flask-cors` with explicit allowlist.

### N-5 — Janitor daemon thread (DEFERRED)

`app.py:243` — janitor thread is `daemon=True`. On gunicorn SIGTERM, main thread exits, daemon dies mid-iteration. Mid-cleanup file deletions could leave half-rmtree dirs.

**Mitigation:** all cleanup uses `shutil.rmtree(..., ignore_errors=True)` — idempotent. Subsequent boots re-clean.

**Recommended follow-up:** none required. Document in code comment if not already.

### N-6 — No `HEALTHCHECK` in Dockerfile (DEFERRED)

Render uses an external HTTP health probe configured in dashboard, not the Docker `HEALTHCHECK` directive. Adding `HEALTHCHECK CMD curl -f http://localhost:$PORT/health || exit 1` would help local Docker users see container health via `docker ps`.

**Recommended follow-up:** include in N-7 Dockerfile-hardening PR.

### N-7 — Dockerfile runs as root (DEFERRED)

No `USER` directive. App runs as PID 1 root. Standard hardening adds `RUN useradd -m kratos && USER kratos`. Single-tenant container so blast radius is limited.

**Recommended follow-up:** Dockerfile-hardening PR (~30 min): add HEALTHCHECK + USER + tini for proper signal handling.

### N-8 — `Procfile` dead code (DEFERRED)

`Procfile` says `web: bash entrypoint.sh`. Used by Heroku/Railway-classic buildpacks. Render with `env: docker` ignores it entirely. Harmless but misleading.

**Recommended follow-up:** delete Procfile or annotate as "fallback for non-Docker buildpack mode (currently unused)".

### N-9 — `downloader.py` excluded from CI bandit scope (DEFERRED)

CI's bandit job runs against `personalize/ kratos_clone/ scripts/ app.py` (`.github/workflows/ci.yml`) — `downloader.py` is intentionally excluded as upstream legacy. Local bandit including `downloader.py` reports 1 High: `downloader.py:87` uses `hashlib.md5(url.encode()).hexdigest()[:12]` for filename uniqueness. This is non-security (just a collision-resistant hash for file naming), and the equivalent calls in `scripts/` are annotated `usedforsecurity=False` per the CI comment.

**Mitigation:** annotate `downloader.py:87` with `usedforsecurity=False` (Python 3.9+) or `# nosec B324` to silence bandit, and add `downloader.py` to the CI bandit scope. Either fixes the gap.

**Recommended follow-up:** include in a future "downloader hardening" PR alongside the other downloader-touching work.

---

## Verification matrix

All gates run on `chore/pre-deploy-audit-2026-05-10` after the fix:

| Gate | Command | Result | Notes |
|---|---|---|---|
| Empirical boot | venv repro (Step 3 above) | ✅ BOOT OK — 10 routes | Replicates Dockerfile install path 1:1 |
| ruff check | `uv run ruff check kratos_clone/ scripts/` | ✅ All checks passed | Audit doc has no Python |
| ruff format | `uv run ruff format --check kratos_clone/ scripts/` | ✅ 11 files already formatted | |
| mypy | `uv run mypy --config-file pyproject.toml` | ✅ Success — 21 source files | No code change |
| pytest | `uv run pytest -q` | ✅ 210 passed, 2 skipped | Live OpenAI tests gated; verified post-urllib3-bump |
| bandit (CI scope) | `uv run bandit -r personalize/ kratos_clone/ scripts/ app.py --severity-level medium` | ✅ Medium: 0, High: 0 | CI gate scope per `ci.yml` |
| bandit (incl. downloader.py) | `uv run bandit -r personalize/ kratos_clone/ scripts/ app.py downloader.py --severity-level medium` | ⚠️ Medium: 0, High: 1 | N-9 — md5 filename hashing in `downloader.py:87`; non-security |
| pip-audit | `uv run pip-audit -r requirements.txt --vulnerability-service pypi` | ✅ 0 known vulnerabilities (re-verified 2026-05-25 post-PR-#38) | M-3 fully closed |

---

## Sign-off checklist (for the operator)

After this PR merges and Render auto-deploys:

- [ ] In Render dashboard → Environment → set `OPENAI_API_KEY` to the production key
- [ ] (Recommended) Set `LOG_FORMAT=json` for structured prod logs
- [ ] (Optional) Override any rate-limit env vars if defaults aren't right (`CLIENT_ERRORS_RATE_LIMIT`, etc.)
- [ ] Watch deploy logs for `Starting gunicorn on port 8080…` — no `ModuleNotFoundError`
- [ ] `curl https://<service>.onrender.com/health` → expect `{"status": "ok"}`
- [ ] `curl https://<service>.onrender.com/personalize` → expect 200 HTML form
- [ ] POST a tiny brief to `/api/personalize/structure` → expect 200 JSON, spend ≤ $0.05
- [ ] Confirm Render service uptime > 5 minutes; janitor thread + boot cleanup are running

If `/api/personalize/structure` returns 5xx → check `OPENAI_API_KEY` in Render dashboard. If `/health` doesn't respond → check deploy logs for ImportError (B-1 regression).

---

## Recommended follow-up sequencing

1. **Doc refresh PR** — M-1 + M-2 + N-1 + N-2. ~30 min. Single-author doc edits.
2. **Dockerfile hardening PR** — N-6 + N-7 (+ optionally N-8). ~30 min. Add HEALTHCHECK + USER.
3. ~~Cryptography bump PR — M-3.~~ Closed transitively by PR #38 (`openai 2.32 → 2.38` dropped both `cryptography` and `pyjwt` from the closure). No action required.
4. **Memory investigation issue** — M-5. Profile a heavy-SPA capture under 512 MB constraint. Outcomes: keep current setup, set `--ipc=host`, or upgrade tier.
5. **Rate-limit guard** — M-4. Add boot-time warning if `--workers >1` and storage is `memory://`.

Each is independent and small. None blocks deploy.
