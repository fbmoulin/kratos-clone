# CLAUDE.md — kratos-clone

Guidance for Claude Code (and any other AI agent) working on this repo.
This file complements (does NOT replace) the user's global `~/.claude/CLAUDE.md`.

---

## Project at a glance

**kratos-clone** is a fork of `asimov-academy/Website-Downloader`. The fork adds:
1. A hardened Playwright capture module (`kratos_clone/`) with 5 SPA-recall patches
2. A design-system extraction pipeline (`scripts/`) that produces self-contained
   `design-system.html` showcases with embedded DTCG token JSON
3. An observability layer (`structlog` + browser logger + `/api/client-errors`)
4. Architecture specs for a 6-stage pipeline + OpenAI-driven personalization

The original Flask UI (`app.py` + `downloader.py`) is preserved and still functional.

> **Critical orientation:** when auditing or modifying capture logic, the
> **new code lives in `kratos_clone/capture.py`**. The legacy `downloader.py` is
> the original upstream module, kept for backward compat with the Flask UI.
> Don't waste cycles auditing legacy code unless explicitly asked.

---

## Reading order for new sessions

1. **`docs/AUDIT.md`** — current state, P1/P2 findings, where the body is buried
2. **`ROADMAP.md`** — phased plan
3. **`TODO.md`** — actionable next-sprint items
4. **This file** — conventions + commands
5. **`docs/WORKFLOW.md`** — target architecture (note: Stages 1, 6 aspirational)

---

## Commands

### Capture a site (CLI — new hardened path)
```bash
uv run python -m kratos_clone <url> --output-dir ./capture
# Knobs: --passes {1,2,3} --viewport WxH --headed --no-styles --no-shadow --no-io-polyfill
# Env vars: KCD_VIEWPORT_WIDTH, KCD_NAV_TIMEOUT, KCD_DOM_STABLE_MS, KCD_SCROLL_PASSES,
#           KCD_HEADED, KCD_CAPTURE_COMPUTED_STYLES, KCD_IO_POLYFILL, KCD_SHADOW_WALKER,
#           KCD_BLOCK_ANALYTICS, LOG_LEVEL, LOG_FORMAT
```

### Generate a design system from a capture
```bash
cd ./capture
cp ../scripts/inventory.py . && cp ../scripts/generate_design_system_v2.py .
python inventory.py > _inventory.json
python generate_design_system_v2.py
# Open ./design-system.html
```

### Run the legacy Flask UI
```bash
uv run python app.py            # http://localhost:5001
LOG_FORMAT=json uv run python app.py     # JSON logs for prod
```

### Lint + format (must pass before push)
```bash
uv run ruff check kratos_clone/ scripts/ app.py
uv run ruff format --check kratos_clone/ scripts/ app.py
```

### Tests (Phase 1 — not yet implemented)
```bash
uv run pytest -q
```

### CI status check
```bash
gh pr checks <PR#> -R fbmoulin/kratos-clone --watch
gh run list --limit 5
```

---

## Conventions (project-specific, beyond global CLAUDE.md)

### Logging
- Always use `logger.info()`, `.warning()`, `.error()` from `structlog` — **never `print()`**.
- Always pass kwargs (`structured`), never f-string interpolation in log messages:
  ```python
  logger.warning("orphan_remove_failed", entry=entry, error=str(e))   # ✅
  logger.warning(f"failed: {entry} {e}")                              # ❌
  ```
- Event names are `snake_case_verb_noun` for greppability.

### Capture module (`kratos_clone/`)
- All tunables go through `CaptureConfig` dataclass with `KCD_*` env-var defaults.
- Init scripts (Patches A, D) are top-level constants `PATCH_A_*` / `PATCH_D_*`.
- Use `await page.add_init_script()` BEFORE `page.goto()` for any page-context script that must run before user JS.
- Network handlers (`_on_response`, `_route_handler`) must `try/except` so a single bad response doesn't crash the capture.
- Asset writes go to `assets/` subdir under output-dir, with hashed filenames via `asset_filename(url)`.

### Frontend (`templates/index.html`)
- Single inline `<script>` block at end of body — no separate JS files (preserves zero-build deploy).
- The browser logger MUST capture `_rawFetch = window.fetch.bind(window)` BEFORE wrapping fetch — otherwise `flush()` falls into a feedback loop with `/api/client-errors`. (Lesson from PR #1 review.)
- Any `fetch` to `/api/client-errors` MUST go through `_rawFetch`, NEVER through the wrapped `window.fetch`.
- All errors caught in the logger MUST also be `try/catch`-wrapped — the logger never throws to the page.

### Backend (`app.py`)
- Endpoints that accept user input check size BEFORE parsing JSON (defense against parser DoS).
- 1 MiB Flask-wide `MAX_CONTENT_LENGTH` is the chunked-transfer-resistant backstop.
- 204 responses MUST have empty body (RFC 9110 §15.3.5). Use `return ("", 204)`, NOT `return jsonify({...}), 204`.
- `request.get_json(silent=True)` (no `force=True`) — `force=True` allows `text/plain` content-type to bypass CORS preflight.

### Generators (`scripts/`)
- Currently single-script style: top-level execution at import. **Don't refactor to a library yet** unless adding tests (Phase 1) — the import-time cost is negligible and the script style is appropriate for one-shot use.
- ⚠️ **Generators have hardcoded NexusFlow indices** — they `IndexError` on arbitrary sites. Phase 2 fixes this. Don't claim they're "site-agnostic" until then.

---

## Known issues (Phase 2 fix targets)

| Bug | Location | Symptom |
|-----|----------|---------|
| **Patch D shadow walker is no-op** | `kratos_clone/capture.py:78-101` | Manifest reports "D_shadow_walker" applied; actually captures zero shadow DOM because `cloneNode(true)` doesn't copy shadow roots. |
| **Asset write race** | `kratos_clone/capture.py:319` | Late response handlers may be aborted mid-byte by `context.close()`. Truncated CSS/font files. |
| **Generators NexusFlow-tuned** | `scripts/generate_design_system_v{1,2}.py` | `inv["buttons"][2]` fails on sites with different button order. |
| **Iframe srcdoc unconditional win** | `kratos_clone/capture.py:490` | Cookie-banner srcdoc replaces real content if length > 1000 chars. |

---

## Patterns to follow

### When adding a new capture knob
1. Add field to `CaptureConfig` with `field(default_factory=lambda: ...)` reading the env var
2. Add `--your-knob` to `kratos_clone/__main__.py` argparse
3. Wire into `capture.py` logic
4. Document the `KCD_*` env var in README + this file's command table

### When adding a new section to design-system generator
1. Verify the data exists in `_inventory.json` (run `inventory.py` once on a fresh capture)
2. Add a `make_section("id", "NN", "Title", "lede")` block in `generate_design_system_v2.py`
3. Render content from inventory data — never hardcode site-specific values
4. Update `coverage` scorecard if the section corresponds to a new DTCG category

### When fixing an audit finding
1. Reference the audit ID in commit message (e.g., "fix: Patch D shadow walker (P1-A)")
2. Update `TODO.md` to check off the item
3. Update `docs/AUDIT.md` to mark the finding RESOLVED with commit SHA
4. Add a regression test (Phase 1 dependency — once tests exist)

---

## Workflow expectations

### Branching
- `main` is protected (squash/rebase merges only, requires CI green).
- Create `feat/X` or `fix/X` or `docs/X` branches; PR-based workflow.
- Felipe (admin) can `gh pr merge --admin` for emergencies — but the rule is PR + status checks for normal work.

### Commits
- **Sole-author by Felipe.** NEVER add `Co-Authored-By: Claude...` trailers.
- Commit messages: `<type>(<scope>): <imperative summary>` then HEREDOC body explaining why.
- Reference audit findings (P1-A, P2-3) when applicable.

### Reviews
- CodeRabbit, Gemini Code Assist, Code Review Doctor auto-review every PR.
- Treat their findings as legitimate signal — PR #1 had 3 Major-severity bugs they caught.

### CI gates
- `Lint (ruff)` — must be green
- `Import + module smoke test` — must be green
- Both are required-status-checks in the branch ruleset.

---

## Things to avoid

- Don't `pip install` anything — use `uv add <pkg>` so it lands in `pyproject.toml` + `uv.lock`.
- Don't add ESLint/Prettier — there's no JS bundle, only a single inline script.
- Don't extend `downloader.py` — that's legacy upstream code. New work goes in `kratos_clone/`.
- Don't claim a feature is "verified" without a test, and don't claim a measurement is "+N%" without an A/B run.
- Don't generate synthetic faces for testimonials in the personalization layer (EU AI Act + OpenAI usage policies).
- Don't write to `extracted/` or `extracted_v2/` directories — they're git-ignored regenerable outputs. Use `./capture` or other ad-hoc dirs for new captures.

---

## Pointers to global guidance

The user's global `~/.claude/CLAUDE.md` defines:
- Workflow complexity classification (Trivial / Simples / Média / Alta) and which to plan vs execute directly
- Stack defaults (Next.js + React + TS for new frontends, FastAPI for new Python services, Drizzle/SQLAlchemy ORMs)
- Memory hygiene (`/observe` for headless batches; `MEMORY.md` updates at session close)
- Auth + error retry patterns (~/.claude/runbooks/auth-errors.md)

Project-level rules in this file override defaults where they conflict — e.g., this is a
Flask project (not FastAPI) because it inherits from upstream.
