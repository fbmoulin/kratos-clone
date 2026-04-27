# TODO — kratos-clone

Short-term actionable items. For long-term phasing see `ROADMAP.md`. For audit context
see `docs/AUDIT.md`.

> **Convention:** check off items as `- [x]` when merged to `main`. Move to changelog
> after a Phase completes.

---

## 🔥 Now (Phase 3 — production hardening)

> Phase 1 (factory + tests) shipped 2026-04-27 (PR #3, b54939a).
> Phase 2 (structural bug fixes) shipped 2026-04-27 (`feat/phase2-structural-fixes`).
> All 5 P1 items from audit closed. 62 tests, pytest green. See "Done" log below.

---

## 🟡 Then (Phase 3 — production hardening)

- [ ] Global asset disk cap — `KCD_MAX_TOTAL_MB=200`, `KCD_MAX_ASSETS=500` env vars + cumulative tracking in `_on_response`. (P1-E)
- [ ] Three-pass scroll wall-clock budget — `KCD_MAX_SCROLL_S=120`. Emit `scroll_budget_exceeded` flag in manifest. (P2-2)
- [ ] Strip query strings from `location.href` in browser logger; ANSI-strip in `app.py:_truncate`. (P1-I + P2-4, ~15m)
- [ ] Drop `force=True` in `request.get_json()`; return 415 on wrong content-type. (P2-3, ~5m)
- [ ] Rate-limit `/api/client-errors` via Flask-Limiter. (P2-5, ~30m)
- [ ] Bump `gunicorn>=22.0.0` (CVE-2024-1135) + `pip-audit` job. (P2-6, ~15m)
- [ ] Browser logger queue cap (`if (queue.length > 200) queue.shift()`). (~5m)
- [ ] BeautifulSoup-aware HTML rewriting in `post.py` (replace raw `str.replace`). (P1-F, ~1.5h)

---

## 🟢 Later (Phase 6 — polish)

See `ROADMAP.md` for full breakdown. Phase 4 (personalization MVP) and
Phase 5 (pipeline completion + P2-8 closure) shipped 2026-04-27.

---

## Done ✅

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
