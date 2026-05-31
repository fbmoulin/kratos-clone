# RESUME — feat/personalize-preview-modal (2026-05-31)

Branch `feat/personalize-preview-modal`, NOT pushed. Plan:
`docs/superpowers/plans/2026-05-30-personalize-preview-modal.md`.

## Done & committed (through ~8b3a8f1)
- Tasks 1-3 (backend): preview route + content-type-aware CSP (.svg only),
  screenshot render + semaphore-in-create_app + isolated `_block_external`,
  `_validate_html_dir` + success-gated cache clear + html_dir in run JSON.
  Each passed two-stage review.
- Tasks 4-6 (frontend, by-hand in templates/personalize.html): result-card +
  3-tab ARIA modal + glassmorphism CSS + modal JS (open/close/Esc/backdrop,
  focus trap, lazy thumb/compare loaders, screenshot cache-bust). +5 a11y tests.
- Code-review fixes applied: I2 focus trap + I3 cache-bust (commit c0c7e4e),
  then I1 tablist ArrowLeft/Right/Home/End nav + M1 iframe about:blank + M2 tab
  width:auto (commit ~8b3a8f1). All code-review must-fixes now CLOSED.
- Suite: 318 passed + 2 skipped. ruff clean. Inline JS parses (bun).

## REMAINING (next session)
1. **VERIFY HEAD first**: `git log --oneline -3`. Confirm the I1/M1/M2 commit
   (~8b3a8f1) landed and `tests/fixtures/spa_sample.html` is tracked
   (`git ls-files tests/fixtures/spa_sample.html`). If the fixture is untracked,
   commit it.
2. **Task 7 — redo Playwright smoke CORRECTLY** (the earlier one was INVALID:
   `python app.py` runs create_app(run_boot_cleanup=True) which WIPES
   downloads/ on boot, so the scratch capture 404'd). Fix: start server FIRST,
   THEN create the capture dir:
   `LOG_FORMAT=json uv run python app.py &` ; sleep 4 ;
   `mkdir -p downloads/smoke-test && cp tests/fixtures/spa_sample.html
   downloads/smoke-test/personalized.html && printf '<!doctype html><h1>ORIG</h1>'
   > downloads/smoke-test/index.html`. Then drive Playwright MCP: SPA scripts
   run in iframe (toggle+carousel), modal opens, thumb tab polls
   img.naturalWidth>0 (~3s real render), compare tab both imgs, arrow keys move
   tabs, Esc closes + focus returns to #btn-open-preview, console 0 errors.
   Then `pkill -f 'python app.py'; rm -rf downloads/smoke-test`.
   Add `tests/test_spa_fixture.py` guard (exists/interactive/no-network).
   Commit Task 7.
3. **Task 8 — gate sweep**: pytest, ruff check, ruff format --check,
   mypy app.py, bandit -r app.py --severity-level medium. Then update CLAUDE.md
   "Active WIP" section → feature complete (currently STALE: says 274 tests /
   no code shipped). Commit.
4. **Push/PR**: needs EXPLICIT user approval. Branch is ~10 commits ahead of
   origin. `gh` repo: fbmoulin/kratos-clone, base main.

## Known limitation (accepted, document in app.py if not already)
INT-1: self-hosted @font-face falls back to system fonts in the Inspecionar
iframe — opaque(null) origin's CORS font fetch won't match same-host ACAO;
widening to "*" would re-open R2-PRC002. Cosmetic, single-operator.

## Deferred nice-to-haves
- optional os.path.isdir->404 guard in personalize_run (noted inline).
