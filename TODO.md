# TODO — kratos-clone

Short-term actionable items. For long-term phasing see `ROADMAP.md`. For audit context
see `docs/AUDIT.md`.

> **Convention:** check off items as `- [x]` when merged to `main`. Move to changelog
> after a Phase completes.

---

## 🔥 Now — P2 cleanup pass

> Phases 1–6 shipped 2026-04-27. All 9 P1 audit items closed. All 12 P2
> closed as of 2026-05-10. mypy Stages A, B, C all shipped. Remaining:
> ~13 P3 in `docs/AUDIT.md`. No active phase header — picking off
> opportunistic wins.

- [ ] **mypy Stage D** — type `downloader.py` (legacy upstream, 46 mypy errors, zero test coverage on `download()` / `/download` route). Most errors (24/46) are `[no-untyped-def]` pure-annotation; 17 are `_as_str` clones from Stage B/C.1. Annotation-only — no behavior change. Decision: type directly (D-A) without test backstop; track follow-up smoke test as P3. (~2h)

---

## 🟢 Later

Phases 4–6 shipped 2026-04-27. Open work tracked as: ~13 P3 items in
`docs/AUDIT.md` (all P2 closed as of 2026-05-10). Other long-tail candidates
beyond the 🔥 Now list live in `docs/AUDIT.md` directly.

- [ ] **`HardenedCapture` structlog refactor** — replace the `LogCallback` /
  `self.log(f"⚠️  ...")` prose pattern (~10 call sites in
  `kratos_clone/capture.py`) with a bound `structlog` logger and snake_case
  event names + kwargs. Per CLAUDE.md "Logging" convention. Surfaced by
  CodeRabbit on PR #15; deferred from there because partial adoption would
  make the refactored lines stand out more than the convention violation.
  (~1.5h)

---

## Done ✅

- [x] **2026-05-10** — **mypy Stage C.2 + drive-by**: `scripts/generate_design_system_v2.py` (1151 LOC) added to strict mypy gate; `scripts/generate_design_system_v1.py` (826 LOC) deleted as dead code (zero callers, zero tests, last touched 2026-04-27, superseded by v2). 109 mypy errors in v2 fixed without `# type: ignore`: 63 `[arg-type]` from `**{"class":...}` keyword-unpack against `BeautifulSoup.new_tag` → `attrs={"class":...}` (32 sites rewritten; the multi-line `style=`/concat sites kept their structure); 32 `[union-attr]` on `Tag | None` from `find()` → 8 `assert ... is not None` blocks at one-time narrowing points (`new_head`, `new_body`, `orig_head`, `orig_body`, `_hero_src`, `h1`, `template`, `_clone_inner`); 7 `[no-untyped-def]` → annotated `make_section -> tuple[Tag, Tag]` and 3 utility helpers (`find_button_by_classes`, `hex_to_rgb`, `contrast_ratio`); 3 `[assignment]` resolved by renaming Tag-bindings (`label`/`name`/`title` → `_tag` suffix) so the loop var stays `str`; 1 `[var-annotated]` → `Counter[str] = Counter()`; 1 `[index]` auto-resolved by the hero narrowing. `_as_str` + `_classes_of` helpers copied verbatim from `inventory.py` per CLAUDE.md "scripts one-shot". Drive-by: `scripts/inventory.py:331` parens (`A or B or (C and D)` — style cleanup, NOT bug; predicate semantics unchanged) + TODO line-number typo (351 → 331). `pyproject.toml`: v2 added to strict overrides + `[tool.mypy] files`; both v1 and v2 removed from permissive override (only `wsgi`, `downloader` remain); ruff per-file-ignores narrowed `v*.py` → `v2.py`. README L128 v1 row removed. AUDIT.md historical refs annotated `(removed 2026-05-10)`. CI step renamed `mypy (Stage A+B+C — ...)`. 8 files / +124/-909 LOC (deletion-dominant). Zero behavior change. 210 tests still passing. Only Stage D (`downloader.py`) remains.
- [x] **2026-05-10** — **mypy Stage C.1**: 4 small scripts (`scripts/inventory.py`, `probe.py`, `validate.py`, `post_process.py`) added to mypy strict gate. 28 errors fixed without `# type: ignore`: 14 `[arg-type]` + 6 `[union-attr]` in `inventory.py` (BS4 `_AttributeValue` family — Stage B's `_as_str` plus a new `_classes_of(el: Tag) -> list[str]` helper for the 11 `el.get("class", [])` sites); 1 `[import-untyped]` in `probe.py` (install `types-requests` dev dep + CI `pip install` line); 2 `[arg-type]` + 1 `[call-overload]` in `validate.py` (`find_all(**{attr: True})` → `find_all(attrs={attr: True})`; style attr via `_as_str`); 1 `[call-overload]` + 1 `[index]` in `post_process.py` (helper signature `Iterable[tuple[object, ...]]` → `Iterable[tuple[Tag, ...]]`; same `find_all(attrs=...)` switch). Per CLAUDE.md "scripts intentionally one-shot, not a library", `_as_str` is copied into each script that needs it (3 copies) instead of a shared helper module. `pyproject.toml`: 4 strict-typed scripts added to `[tool.mypy] files`; new strict override block; permissive override narrowed to only `scripts.generate_design_system_v{1,2}` (the Stage C.2 deferral). CI step renamed `mypy (Stage A+B+C.1 — ...)`. 6 files / +133/-33 LOC. Zero behavior change. 210 tests still passing. Stage C.2 (generators) and Stage D (`downloader.py`) deferred.
- [x] **2026-05-10** — **mypy Stage B**: `kratos_clone/capture.py`, `post.py`, `__main__.py` added to mypy strict gate (alongside Stage A's `app.py` + `personalize/*` + `wsgi.py`). 15 mypy errors fixed without a single `# type: ignore`: 5 `[no-untyped-def]` → real annotations; 4 `[no-any-return]` from `await page.evaluate(...)` → `cast(str | dict[str, Any], ...)` at each call site; 4 `[arg-type]` + 1 `[union-attr]` in `post.py` → `_as_str` helper coerces `str | AttributeValueList`; 1 `[attr-defined]` → manifest comprehension pre-built as `patches: list[str]`; 1 `[unreachable]` from `warn_unreachable=true` → dead `isinstance(el, Tag)` guard removed (BS4 `find_all(True)` only returns Tags). `network_resources` + `_pending_writes` instance attrs tightened. `pyproject.toml`: `kratos_clone/` added to `[tool.mypy] files`; new strict override block. CI step renamed `mypy (Stage A+B — personalize/ + app.py + wsgi.py + kratos_clone/* strict)`. 5 files / +80/-50 LOC. Zero behavior change. 210 tests still passing. Stage C (`scripts/*` + `downloader.py`) deferred.
- [x] **2026-05-10** — **`🔥 Now` cleanup: inventory enrichment + bandit MEDIUM + mypy Stage A**. (a) `scripts/inventory.py` refactored from script to importable module-with-`main()`; +6 extractors (`font_families`, `font_weights`, `durations`, `shadows`, `gradients`, `borders`) wired into output. Keys match `validate.py` `_judge_category` exactly — DTCG scorecard now reflects genuine inventory evidence instead of always-`missing`. +12 tests in `tests/test_inventory.py` (197 → 209). (b) Bandit CI gate flipped HIGH → MEDIUM (`.github/workflows/ci.yml`); 0 MEDIUM findings — no code changes needed. (c) Mypy Stage A — `app.py` typed strictly (~25 functions annotated, 4 module-level dict annotations); `[[tool.mypy.overrides]]` adds `app` to the strict block; CI mypy step is now a HARD gate. `files = ["personalize", "app.py", "wsgi.py"]` defines the Stage A surface; `kratos_clone.*` and `scripts.*` deferred to Stage B / C. CI step renamed `mypy (Stage A — personalize/ + app.py + wsgi.py strict)`.
- [x] **2026-05-10** — **P2-1, P2-9, P2-10 closed + 6 housekeeping rows synced**. (a) `asset_filename` allow-lists ext via `^[A-Za-z0-9]{1,8}$` and raises `ValueError` on assembled fname containing `/`, `\`, `..`, or NUL; +5 tests (192 → 197 passing). (b) `docs/WORKFLOW.md` Quick-wins row for Patch A reworded from "+70% lazy-load capture" to qualitative observation (P2-9); new Stage 3 bullet credits `kratos_clone/post.py` orphan-link injection as the CSS-recovery mechanism (P2-10). (c) `docs/AUDIT.md` rows P2-1..P2-7, P2-9, P2-10 all struck through with file:line evidence — P2-2..P2-6 closed in Phase 3, P2-7 closed in Phase 1; this commit only documents them. **All 12 P2 audit items now closed.** Remaining open: ~13 P3 only.
- [x] **2026-05-10** — **P2-12 closed**: `_on_response` skips responses whose originating request carried an `Authorization` header (avoids JWT/API-key leakage when capturing authed views). One-shot warnings on first auth-skip + first `octet-stream` capture. New `authed_skipped` manifest counter. +6 tests in `tests/test_capture_response_handler.py` (183 → 192 passing). Also: TODO.md cleanup — stale Phase 3 "Now/Then" sections collapsed into a forward-looking P2 cleanup list; obsolete Gemini-PR-#7 bullet removed (closed by PR #14).
- [x] **2026-04-27** — **Phase 6 complete**: DevEx + observability polish. Dependabot weekly grouped pip + github-actions. ruff `[tool.ruff]` config (E/F/W/I/UP/B/C4/SIM rules) + mypy `[tool.mypy]` strict-on-personalize. New CI jobs: `mypy` (soft gate) + `bandit` (HARD gate on HIGH severity, currently 0 after annotating B324 MD5 with `usedforsecurity=False` and B201 debug=True with `# nosec` since it's `__main__`-only). New `X-Request-ID` middleware on `app.py` propagates UUID4 to structlog contextvars + response header (5 tests). Full `KCD_*` env-var reference table in `README.md`. +5 tests (178 → 183 passing). +21 files reformatted via auto-fix.
- [x] **2026-04-27** — **Phase 5 complete**: Pipeline completion. Three new pipeline-stage scripts (`scripts/probe.py` Stage 1 site recon, `scripts/post_process.py` Stage 3 asset audit + inline, `scripts/validate.py` Stage 6 quality gate with 4 checks: data-driven DTCG scorecard, asset-ref resolution, placeholder grep, WCAG contrast). Hardcoded `DTCG_CATEGORIES` literal removed from `generate_design_system_v2.py` — score is now genuine per-site. **Closes audit P2-8** (tautological scorecard). +39 tests (139 → 178 passing). Visual-diff via Playwright deferred to follow-on (keeps validation gate headless/CI-friendly).
- [x] **2026-04-27** — **Phase 4 complete**: Personalization MVP. New `personalize/` package (slots, sanitize, openai_client, patcher, pipeline, cli) + 3 Flask routes (`/personalize`, `/api/personalize/structure`, `/api/personalize/run`) + intake form template. Hard budget cap (default \$1.00) on `OpenAIBrandClient`; closed-enum strict JSON schema for patches+images (zero slot-id hallucination). Live-validated against gpt-5-mini Responses API (~\$0.105 spent during E2E test). Closes audit **P2-11** (LLM input/output hardening: control-char strip, magic-byte allow-list PNG/JPEG, EXIF strip, dangerous-HTML strip). +66 tests (74 → 139, +2 live gated). 8 PR commits.
- [x] **2026-04-27** — **Phase 3 complete**: production hardening — gunicorn 21.2→22.0 (CVE-2024-1135), content-type strict (force=True dropped → 415 on non-JSON), URL query/fragment stripped before logging (P1-I), ANSI/control-char sanitization in `_truncate` (P2-4), browser logger queue cap (200, drops oldest), three-pass scroll wall-clock budget (`KCD_MAX_SCROLL_S=120`, manifest flag), global asset disk caps (`KCD_MAX_TOTAL_MB=200`, `KCD_MAX_ASSETS=500`, drop counter), BS4-aware `rewrite_html_assets` (only URL-bearing attrs + style url() — script bodies preserved), Flask-Limiter on `/api/client-errors` (`60 per minute` per IP, configurable via `CLIENT_ERRORS_RATE_LIMIT` + `RATE_LIMIT_STORAGE_URI`), pip-audit job in CI (osv vuln service, soft gate). Tests 62 → 74 passing (+12). All 9 P1 audit items now closed.
- [x] **2026-04-27** — **Phase 2 complete**: 5 structural fixes — Patch D shadow walker now walks LIVE DOM (cloneNode bug fixed, emits Declarative Shadow DOM, counts skipped_closed_shadow_roots in manifest); asset write race resolved (asyncio.create_task + gather before context.close, 10s timeout); generators use semantic class-signature lookup (no more IndexError); iframe srcdoc length-compared against main doc (KCD_IFRAME_MIN_RATIO=0.5 default, KCD_NO_IFRAME_SRCDOC opt-out); same-origin via urlparse().netloc. +1 test file (test_generator_helpers.py, 10 cases). Total 62 pytest cases.
- [x] **2026-04-27** — **Phase 1 complete**: `app.py` refactored to factory (`create_app(start_janitor, run_boot_cleanup)`); `wsgi.py` for production gunicorn; `entrypoint.sh` updated to `wsgi:app`; 52 pytest cases across `test_post.py` (14), `test_capture_helpers.py` (16), `test_client_errors.py` (22); pytest job added to CI; `import app` confirmed side-effect-free (no janitor thread spawned).
- [x] **2026-04-27** — Multi-agent audit (`docs/AUDIT.md`).
- [x] **2026-04-27** — Doc honesty pass (this commit): README rewrite, soften 3 overstated claims, add status banners, create ROADMAP/TODO/CLAUDE.
- [x] **2026-04-27** — Branch protection ruleset (squash/rebase + status checks required, admin bypass allowed).
- [x] **2026-04-27** — Observability layer (PR #1 — structlog backend + browser logger + `/api/client-errors`).
- [x] **2026-04-26** — kratos_clone hardened capture module + 5 patches A-E (Patch D works partially, others verified).
- [x] **2026-04-26** — design-system v1 + v2 generators (NexusFlow-tuned).
- [x] **2026-04-26** — Architecture specs: PROMPT_v2, WORKFLOW, PERSONALIZATION.

---

## Notes

- Auto-review bots (CodeRabbit, Gemini Code Assist, Code Review Doctor) run on every PR. Don't ignore their comments — PR #1 had 3 legitimate Major-severity findings that we addressed before merge.
- All commits sole-authored by Felipe — never add Co-Authored-By trailers per `~/.claude/CLAUDE.md`.
- All Python work uses `uv`, never `pip`. JS-side stays bun-only when applicable.
- Run `ruff check && ruff format` before push. Ruff is in CI as a hard gate.
