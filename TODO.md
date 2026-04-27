# TODO — kratos-clone

Short-term actionable items. For long-term phasing see `ROADMAP.md`. For audit context
see `docs/AUDIT.md`.

> **Convention:** check off items as `- [x]` when merged to `main`. Move to changelog
> after a Phase completes.

---

## 🔥 Now (Phase 1 — tests + factory)

- [ ] **Refactor `app.py` to factory pattern** — `create_app(start_janitor=True)` so
      `import app` has no side effects (kills `cleanup_downloads_folder()` and janitor
      thread on import). Unblocks all pytest work. (`app.py:80,188` — AUDIT P2-7, ~1h)
- [ ] **Create `tests/test_post.py`** — 7 cases for `rewrite_html_assets()`:
      empty captured set; single asset exact match; prefix-collision URL pair (`/a.png`
      vs `/a.png/v2.png`); percent-encoded URL in HTML, raw in dict; orphan CSS with
      `</head>` present; orphan CSS with no head, `<body>` only; orphan CSS with neither.
      Plus 3 cases for `strip_scroll_fix` (basic, uppercase TRUE, malformed-attribute).
      (~1.5h)
- [ ] **Create `tests/test_capture_helpers.py`** — `asset_filename` (8: trailing slash,
      query, fragment, unicode, double-ext, no-ext, `..`/spaces sanitization, length cap),
      `hash_url` (2: stable, distinct), `contrast_ratio` (4: black/white = 21, mid-grays
      = WCAG-cited values). (~1.5h)
- [ ] **Create `tests/test_client_errors.py`** — lift the 5 inline asserts from
      `.github/workflows/ci.yml` into pytest. Add: `level='invalid'` coerced to error,
      `level='__class__'` rejected, `_truncate` boundary at exactly `_FRONTEND_MAX_FIELD_LEN`,
      RFC 9110 enforcement (204 → empty body). (~1.5h)
- [ ] **Add pytest job to CI** — alongside ruff + smoke. `pytest -q --tb=short`.
      Keep smoke job for now as a defensive backup. (~30m)

---

## 🟠 Next (Phase 2 — fix structural bugs)

- [ ] **Fix Patch D shadow walker** — `kratos_clone/capture.py:78-101`. Replace
      `cloneNode(true)` walk with live-DOM walk that emits Declarative Shadow DOM.
      Reference: gildas-lormeau/SingleFile walker. Add `skipped_closed_shadow_roots`
      counter to `manifest.json`. (P1-A, ~3h)
- [ ] **Fix asset write race** — `kratos_clone/capture.py:319`. Track pending
      `asyncio.Task` handles from response handlers, `await asyncio.gather(*pending)`
      before `context.close()`. (P1-B, ~1h)
- [ ] **Refactor generators with semantic lookup** — replace `inv["buttons"][2]`
      with class-signature search (e.g., button whose classes contain
      `gradient-to-r from-orange`). Until done, rename files
      `generate_nexusflow_*.py` to honor scope. (P1-C, ~2h)
- [ ] **Fix iframe srcdoc unconditional win** — `kratos_clone/capture.py:490`.
      Length-compare main doc vs srcdoc; log decision; opt-out flag
      (`KCD_NO_IFRAME_SRCDOC`). (P1-G, ~1h)
- [ ] **Same-origin predicate** — `urlparse().netloc` compare instead of
      `"srcdoc" in f_url.lower()` substring check. (P1-D, ~5m)

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
