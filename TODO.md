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

## 🟢 Later (Phase 4-6 — personalization, pipeline completion, polish)

See `ROADMAP.md` for full breakdown.

---

## Done ✅

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
