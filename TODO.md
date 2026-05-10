# TODO — kratos-clone

Short-term actionable items. For long-term phasing see `ROADMAP.md`. For audit context
see `docs/AUDIT.md`.

> **Convention:** check off items as `- [x]` when merged to `main`. Move to changelog
> after a Phase completes.

---

## 🔥 Now — P2 cleanup pass

> Phases 1–6 shipped 2026-04-27. All 9 P1 audit items closed. Remaining: 7 P2
> + ~13 P3 in `docs/AUDIT.md`. No active phase header — picking off P2 items
> as opportunistic wins.

- [ ] **P2-1** — `asset_filename` regex-clean the extension too + assert no `..` / `/` in filename. defense-in-depth on filesystem write. (`kratos_clone/capture.py:174-188`, ~15m)
- [ ] enrich `scripts/inventory.py` with font-family, durations, shadow extractors. lifts the Phase 5 DTCG scorecard from ~30–50 → genuine high-coverage. (~2h)
- [ ] tighten mypy from soft to hard gate after typing `app.py` + `kratos_clone/`. (~3h, gradual)
- [ ] bump bandit gate from HIGH-only to MEDIUM. triage the new findings before flipping. (~1h)

---

## 🟢 Later

Phases 4–6 shipped 2026-04-27. Open work tracked as: 7 P2 items + ~13 P3 in
`docs/AUDIT.md`. Other long-tail candidates beyond the 🔥 Now list live in
`docs/AUDIT.md` directly.

---

## Done ✅

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
