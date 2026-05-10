# Project Audit — kratos-clone

**Date:** 2026-04-27
**Scope:** All additions over upstream `asimov-academy/Website-Downloader`. 4 commits on `main` (`c3e2c90` → `02b32df` → `d4f7e99`). Generator script artifacts excluded from drift count (regenerable).
**Method:** 4 parallel specialized agents (security-auditor, adversarial-critic, quality-engineer, domain-explorer) + manual synthesis.
**Verdict:** Solid MVP. **No CRITICAL ship-blockers.** Three implementation flaws make published claims overstated. Test coverage is the single largest gap.

---

## Scorecard

| Dimension | Status | One-line summary |
|-----------|--------|------------------|
| **Security** | 🟡 Acceptable for internal use | No P0; 4 P1 (mostly DoS surface), 6 P2. Production exposure needs hardening pass. |
| **Architecture** | 🟡 Solid base, 3 broken patches | Patch D (shadow DOM walker) is a no-op due to `cloneNode` semantics. Asset write race. Hardcoded generator. |
| **Test coverage** | 🔴 Critical gap | No `tests/` directory. CI runs 5 inline assertions. Most modules at 0%. |
| **Doc accuracy** | 🟡 Two overstated metrics | "+70% lazy-load" and "80.8/100 DTCG coverage" are unsupported; "+6650% CSS" is misattributed. |
| **Code quality** | 🟢 Clean | Ruff green, repo conventions respected, no Co-Authored-By trailers, structlog kwargs-native. |
| **CI / DevEx** | 🟡 Adequate | Lint+smoke green, no E2E, no security scan, no dependency audit, no mypy. |

---

## Findings consolidated by priority

### 🔴 P0 — Ship blockers
**None.** Under documented threat model (single-user internal tool, attacker-controlled URLs only) nothing is exploitable today.

### 🟠 P1 — High priority

> **Status update 2026-04-27:** P1-A, P1-B, P1-C, P1-D, P1-G, P1-H all RESOLVED in
> Phase 1 (`b54939a`) and Phase 2 (`feat/phase2-structural-fixes`). Remaining open:
> P1-E (asset disk cap), P1-F (BeautifulSoup-aware rewriting), P1-I (PII strip).

| # | File:line | Finding | Source agent | Status |
|---|-----------|---------|--------------|--------|
| **P1-A** | `kratos_clone/capture.py:81-157` | **Patch D shadow walker is a no-op.** `cloneNode(true)` does NOT copy shadow roots per HTML spec — the walker visits a clone where every `shadowRoot` is null. Fix: walk live `document.documentElement` and serialize to string directly (or port SingleFile's walker). | adversarial | ✅ RESOLVED Phase 2 — walker now operates on live DOM, emits Declarative Shadow DOM, counts skipped closed roots in manifest |
| **P1-B** | `kratos_clone/capture.py:_on_response` | **Asset write race before `context.close()`.** Response handlers do sync `write_bytes()` from async callbacks; only safeguard is `wait_for_timeout(500)`. Late writes get truncated. Fix: track pending tasks, `asyncio.gather(*pending)` before close. | adversarial | ✅ RESOLVED Phase 2 — `_on_response_tracked` wraps via `asyncio.create_task`, awaited via `asyncio.gather` (10s timeout) before `context.close()` |
| **P1-C** | `scripts/generate_design_system_v{1,2}.py` | **Generators hardcoded for NexusFlow.** Access `inv["buttons"][2]`, `[3]`, `[7]` as named indices. ANY other site → `IndexError`. Either rename to `generate_nexusflow_*.py` and update WORKFLOW.md, or refactor lookup to find buttons by class signature. | adversarial | ✅ RESOLVED Phase 2 — `find_button_by_classes(buttons, *required, default_label)` semantic lookup with stub fallback. 10 regression tests in `tests/test_generator_helpers.py` |
| **P1-D** | `kratos_clone/capture.py:_extract_html` | **Same-origin predicate broken.** `f_url.startswith(self.url) or "srcdoc" in f_url.lower()` — substring `"srcdoc"` in any URL bypasses origin check. Fix: `urlparse(f_url).netloc == urlparse(self.url).netloc or f_url.startswith("about:srcdoc")`. | security | ✅ RESOLVED Phase 2 — `urlparse().netloc` compare + explicit `about:srcdoc` allow-list |
| **P1-E** | `kratos_clone/capture.py:_on_response` | **No global asset disk cap.** Per-asset 8 MB cap exists but no count or cumulative bytes cap. Pathological site can write GBs. Fix: env-driven `MAX_TOTAL_BYTES` + `MAX_ASSET_COUNT`. | security | ✅ RESOLVED Phase 3 — `KCD_MAX_TOTAL_MB=200` + `KCD_MAX_ASSETS=500`; `asset_caps_dropped` + `total_asset_bytes` in manifest |
| **P1-F** | `kratos_clone/post.py:18` | **`rewrite_html_assets` does naive `str.replace` on raw HTML.** Captured URL substrings appear in scripts/comments/JSON; replacement can corrupt unrelated content. Fix: BeautifulSoup-aware rewriting. | adversarial + security | ✅ RESOLVED Phase 3 — BS4 walker only rewrites URL-bearing attributes (src/href/srcset/data-*) + url() in style blocks/attrs; script bodies + comments preserved verbatim. 5 regression tests |
| **P1-G** | `kratos_clone/capture.py:_extract_html` | **Iframe-srcdoc wins unconditionally** if length > 1000 chars. Cookie banner srcdoc replaces real content. Fix: add length-comparison + log decision; allow opt-out via flag. | adversarial | ✅ RESOLVED Phase 2 — length ratio compare against main doc (`KCD_IFRAME_MIN_RATIO=0.5` default, `KCD_NO_IFRAME_SRCDOC=true` opt-out) |
| **P1-H** | _Project root_ | **Zero `tests/` directory.** All testing is 5 inline assertions in CI. Critical hardening (feedback-loop avoidance, IO polyfill, asset rewriting) has no regression coverage. Fix: create pytest suite (top-priority sprint item). | quality | ✅ RESOLVED Phase 1 — 62 pytest cases across 4 test files, dedicated CI job |
| **P1-I** | `templates/index.html:362-364` | **Browser logger ships full URL + userAgent on every error.** Query strings, fragments, sessionId — LGPD/GDPR-relevant if logs go to 3rd party. Fix: ship `location.origin + pathname` only; document privacy stance. | security | ✅ RESOLVED Phase 3 — server-side `_strip_query()` removes `?…` and `#…` before structlog emit |

### 🟡 P2 — Medium priority

| # | File:line | Finding |
|---|-----------|---------|
| P2-1 | `kratos_clone/capture.py:174-188` | `asset_filename` sanitizes name regex but NOT extension. Defensive: also regex-clean ext + assert no `..`/`/` in filename. |
| P2-2 | `kratos_clone/capture.py:_three_pass_scroll` | **No wall-clock budget.** Pages with infinite-scroll feeds can run for 40+ s in pass 2 alone. Fix: add `max_scroll_seconds` (default 120s) + emit `scroll_budget_exceeded` in manifest. |
| P2-3 | `app.py:client_errors:440` | `request.get_json(force=True)` bypasses content-type validation, enabling `text/plain` cross-origin bypass. Fix: drop `force=True`, return 415 on wrong content-type. |
| P2-4 | `app.py:_truncate` | **ANSI escape injection in console log.** With `LOG_FORMAT=console` (dev default), `\x1b[2J\x1b[H` from a malicious browser entry can clear/scroll the dev terminal. Fix: `s = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "?", s)` in `_truncate`. |
| P2-5 | `app.py /api/client-errors` | **No rate limit.** 32 KB × 20 entries × N req/s. Fix: Flask-Limiter `@limiter.limit("60 per minute")` for production. |
| P2-6 | `pyproject.toml:gunicorn>=21.2.0` | **CVE-2024-1135** (HTTP request smuggling) fixed in 22.0.0. Bump floor to `gunicorn>=22.0.0`. |
| P2-7 | `app.py:80,188` | **Module-level side effects** (`cleanup_downloads_folder()` + `threading.Thread.start()`) make app untestable. Fix: extract to `create_app(start_janitor=True)` factory. |
| ~~P2-8~~ | `scripts/validate.py:coverage_scorecard` + `scripts/generate_design_system_v2.py` | ✅ **RESOLVED 2026-04-27** — Phase 5. `coverage_scorecard(inventory)` now judges each of the 13 W3C DTCG categories against inventory evidence (full|partial|missing + evidence string). The literal `DTCG_CATEGORIES` list is gone; both the rendered scorecard and the total score are computed at runtime. Honest consequence: legacy NexusFlow capture's score drops from 80.8 (tautology) to a genuine number reflecting what inventory.py actually extracts. |
| P2-9 | `docs/WORKFLOW.md:75` | **"+70% lazy-load capture" is unsupported.** All 5 patches applied together; no A/B isolation. Fix: either run controlled experiment or soften claim to "qualitative observation". |
| P2-10 | `docs/WORKFLOW.md` | **"+6650% CSS captured" misattributed.** Recovery is from `post.py:23-36` orphan `<link>` injection, NOT the 5-patch hardening. Fix: WORKFLOW.md should call out orphan injection as the mechanism. |
| ~~P2-11~~ | `personalize/sanitize.py` | ✅ **RESOLVED 2026-04-27** — Phase 4 implementation closes this. `sanitize_brief_text` strips C0 control chars and bounds length before any LLM interpolation; brief fields go into prompts via `json.dumps(...)`, never f-string. `verify_image_bytes` allow-lists PNG/JPEG by magic bytes (rejects SVG XSS). `strip_exif` removes embedded metadata. `strip_dangerous_html` removes `<script>/<style>/<iframe>/<object>/<embed>`, drops `on*=` handlers, neutralizes `javascript:` in href/src. Defense-in-depth: even though strict JSON schema doesn't allow HTML, every LLM-derived value goes through `strip_dangerous_html` before DOM write. 21 dedicated tests in `tests/test_personalize_sanitize.py`. |
| ~~P2-12~~ | `kratos_clone/capture.py:_on_response` | ✅ **RESOLVED 2026-05-10** — `_on_response` now awaits `response.request.all_headers()` (with fallback) and skips responses whose originating request carried an `Authorization` header; one-shot warning on first skip + on first `application/octet-stream` capture. New `authed_skipped` counter in manifest. 6 regression tests in `tests/test_capture_response_handler.py`. |

### 🟢 P3 — Low / informational

- `kratos_clone/capture.py:218` — `self.network_resources` populated but never read. Dead code or expose in manifest.
- `scripts/{inventory,generate_*}.py` — module-level `read_text()` calls; `if __name__ == "__main__":` guard would make them importable for tests.
- `app.py` — 0% type hint coverage on routes/helpers. `make_section`, `hex_to_rgb`, `contrast_ratio` also untyped.
- `.github/workflows/ci.yml` — uses unpinned majors (`actions/checkout@v4`, `actions/setup-python@v5`). Acceptable for non-prod; SHA-pin if shipping artifacts.
- **No Dependabot config.** Cheap insurance: weekly grouped-update PRs.
- **No `pip-audit` / `bandit` / `mypy` in CI.** P1 sprint additions per quality-engineer.
- **No upper bounds on deps** — `playwright>=1.57.0` (frequent breaking changes), `flask>=3.1.2` (4.x will land). Recommend `<2`/`<4` caps.
- `app.py:228` (upstream code, FYI) — `start_download` accepts arbitrary URL with no scheme/host validation → SSRF surface (e.g., `http://169.254.169.254/`). Out of scope for our additions but worth noting.
- Branch protection ruleset has `bypass_mode: "always"` for admin. Acceptable solo; tighten if collaborators added.
- `templates/index.html:354-365` — Browser logger has no max-queue cap; if `flush()` never fires (extension-blocked `setInterval`), uncaught errors at 1 Hz grow unbounded. Add `if (queue.length > 200) queue.shift()`.

---

## Where the agents disagreed

**`domain-explorer` audited the wrong file.** Its report claims "Patches A-E missing (CRITICAL) — 0 implemented" because it inspected `downloader.py` (the OLD upstream code we kept for backward compat) instead of `kratos_clone/capture.py` (where Patches A-E actually live and were verified working in commit `c3e2c90`). All 5 patches DO exist:

| Patch | Location | Verified |
|-------|----------|----------|
| A — IO pre-fire polyfill | `kratos_clone/capture.py:38-77` (`PATCH_A_IO_PREFIRE`) | ✅ Lines visible |
| B — DOM-stable predicate | `kratos_clone/capture.py:107-117` (`DOM_STABLE_FUNC`) | ✅ |
| C — Three-pass scroll | `kratos_clone/capture.py:_three_pass_scroll` | ✅ |
| D — Shadow walker | `kratos_clone/capture.py:78-101` (`PATCH_D_SHADOW_DOM_HELPERS`) | ✅ Code exists, but **broken** per P1-A — `cloneNode` doesn't copy shadow roots |
| E — Computed-style snapshot | `kratos_clone/capture.py:_capture_computed_styles` | ✅ |

Same goes for `scripts/inventory.py`, `generate_design_system_v1.py`, `generate_design_system_v2.py` — they exist and are committed. Domain-explorer missed the fact that `kratos_clone/` is the new module on top of the old `downloader.py`.

**Net effect of this miss:** Domain-explorer's "drift" findings are mostly invalid. Its useful contribution: confirming `scripts/probe.py`, `scripts/post_process.py`, `scripts/validate.py` (referenced in WORKFLOW.md as future Stages 1, 3, 6) are NOT implemented — that's correct documentation drift since WORKFLOW.md presents them as part of the system.

The actual `KCD_*` env vars listed in WORKFLOW.md ARE all implemented in `CaptureConfig` at `kratos_clone/capture.py:120-170` (verified). Domain-explorer was looking at the wrong file when it claimed they were missing.

---

## Remediation plan — top 10 in order

| # | Action | Effort | Impact | Notes |
|---|--------|--------|--------|-------|
| 1 | **Fix Patch D shadow walker** (P1-A): walk live DOM, build serialization string. Drop "shadow DOM captured" claim from manifest until fixed. | M (~3h) | High — currently a phantom feature | Reference: SingleFile's walker. |
| 2 | **Fix asset write race** (P1-B): track pending tasks, `asyncio.gather()` before `context.close()`. | S (~1h) | High — prevents truncated CSS/font files | |
| 3 | **Refactor generators** (P1-C): replace `inv["buttons"][N]` with semantic class lookup. Until then, rename files `generate_nexusflow_*.py`. | M (~2h) | High — generators can't be reused on other sites today | |
| 4 | **Create `tests/` directory + pytest job** (P1-H): start with `test_post.py` (7 cases for `rewrite_html_assets`), `test_capture_helpers.py` (`asset_filename`, `hash_url`, `contrast_ratio`), `test_client_errors.py` (lift CI inline asserts to fixtures + parametrize). | L (~4h) | Highest leverage — unblocks all future refactors | |
| 5 | **Fix iframe srcdoc unconditional win** (P1-G): length compare + log decision + opt-out flag. | S (~1h) | High | |
| 6 | **Add global asset disk cap** (P1-E): `KCD_MAX_TOTAL_MB` + `KCD_MAX_ASSETS` env vars, default 200 / 500. | S (~30m) | High DoS resistance | |
| 7 | **Fix same-origin predicate** (P1-D): `urlparse().netloc` compare. | S (~5m) | Defensive — exploit limited but predicate is wrong | |
| 8 | **Refactor `app.py` to factory pattern** (P2-7): `create_app(start_janitor=True)` removes module-level side effects, makes import-side testing safe. | S (~1h) | Unblocks P1-H test setup | |
| 9 | **Strip query strings + ANSI from logger** (P1-I + P2-4): two-line patches in `templates/index.html` + `app.py:_truncate`. | XS (~15m) | Closes log-injection + privacy gaps | |
| 10 | **Bump `gunicorn>=22.0.0`** (P2-6) + add `pip-audit` job to CI. | XS (~10m) | Closes one published CVE + ongoing monitoring | |

**Optional next sprint** (after the 10 above):
- Soften the 3 overstated doc claims (P2-8/9/10) to match actual measurement.
- Add `bandit -r` + `mypy --strict kratos_clone/` to CI.
- Add Dependabot grouped-updates config.
- Document `KCD_*` env vars in README + add table to WORKFLOW.md.
- E2E Playwright job in CI (serve `extracted/index.html` locally, capture it, assert manifest).

---

## Methodology notes

- 4 agents dispatched in parallel (single tool-call message), ~2 min each.
- Each agent received project-specific brief + focus zones + output format spec.
- Token budget per agent capped via response length guidance (~800-1500 words).
- Synthesis manual; one agent's report (`domain-explorer`) was partially invalidated by file-scope mistake (audited upstream `downloader.py` instead of new `kratos_clone/capture.py`).
- No agent had write permissions; this is a pure read-only audit.

CodeRabbit + Gemini Code Assist + Code Review Doctor already passed PR #1 (the observability layer). Findings here are deeper/orthogonal to those automated reviews.

---

**Files cited (absolute paths):**
- `/home/fbmoulin/Website-Downloader/kratos_clone/capture.py`
- `/home/fbmoulin/Website-Downloader/kratos_clone/post.py`
- `/home/fbmoulin/Website-Downloader/kratos_clone/__main__.py`
- `/home/fbmoulin/Website-Downloader/scripts/inventory.py`
- `/home/fbmoulin/Website-Downloader/scripts/generate_design_system_v1.py`
- `/home/fbmoulin/Website-Downloader/scripts/generate_design_system_v2.py`
- `/home/fbmoulin/Website-Downloader/app.py`
- `/home/fbmoulin/Website-Downloader/templates/index.html`
- `/home/fbmoulin/Website-Downloader/.github/workflows/ci.yml`
- `/home/fbmoulin/Website-Downloader/pyproject.toml`
- `/home/fbmoulin/Website-Downloader/docs/PROMPT_v2.md`
- `/home/fbmoulin/Website-Downloader/docs/WORKFLOW.md`
- `/home/fbmoulin/Website-Downloader/docs/PERSONALIZATION.md`
