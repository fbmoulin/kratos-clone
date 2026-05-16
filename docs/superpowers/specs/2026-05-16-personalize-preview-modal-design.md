# Personalize preview modal — design spec

**Date:** 2026-05-16
**Status:** approved by user (brainstorming session 2026-05-16)
**Closes:** user request — "na personalização queria algo visual para ver o resultado"

## Objective

Today, after `/api/personalize/run` succeeds on `/personalize`, the UI shows
only `Saída: <code>downloads/site-A/personalized.html</code>` as plain text.
The operator has to open the file manually in another browser to see what the
LLM produced. This design adds an inline visual preview with three modes
(iframe inspection, screenshot thumb, side-by-side before/after) accessible
via a single click after personalization succeeds.

## Scope

### In

1. Result card on `/personalize` (replaces current `output-summary` text-only
   block): shows `Saída: <code>` AND an orange CTA button "Abrir preview →".
2. New modal `#preview-modal` — fullscreen overlay, 3 tabs:
   - **Inspecionar** (default) — iframe rendering `personalized.html` directly.
   - **Thumb** — 1280×800 screenshot of `personalized.html`, lazy-generated.
   - **Antes / Depois** — split 50/50 static, both `index.html` and
     `personalized.html` screenshots, lazy-generated as a pair.
3. Two new Flask endpoints:
   - `GET /personalize/preview/<dir>/<file>` — serves
     `downloads/<dir>/<file>` (HTML only, path-validated).
   - `GET /api/personalize/screenshot/<dir>?which={before|after}` — generates
     PNG via Playwright headless, caches to
     `downloads/<dir>/preview-{before,after}.png`. Returns cached bytes on
     subsequent calls.
4. Path security: both endpoints reuse the realpath-confinement pattern from
   `personalize_run` (rejects `..`, symlinks pointing outside
   `DOWNLOAD_FOLDER`).
5. WCAG-essential a11y on modal: `role="dialog"`, `aria-modal="true"`,
   `aria-labelledby`, focus trap, Esc + backdrop + X close, focus restoration
   to trigger button.
6. Regression tests for: 2 new endpoints (happy + 4 path-security + invalid
   params + cache), modal a11y structure, default-tab contract, JS hooks
   present.
7. Playwright smoke pre-PR: trigger personalize success (mocked
   `WebsiteDownloader.process` style) → click "Abrir preview" → switch tabs
   → close.

### Out (deferred)

- Auto-open modal after personalize success (chose manual click — operator
  retains form context).
- Sidebar with structured brief metadata (`empresa`, `tagline`, `tone`,
  `palette`) inside the modal — YAGNI; user said "ver o resultado", not
  "ver o resultado + context".
- Download screenshots as ZIP.
- Public/shareable preview URLs (single-tenant operator-tool).
- Diff highlighting between original HTML and personalized HTML.
- Auto-regeneration when underlying files change (manual re-personalize is
  the existing trigger).

## Architecture

### Backend

**New file: none.** Both endpoints added to `app.py`.

```python
@app.route("/personalize/preview/<path:html_dir>/<path:filename>", methods=["GET"])
def personalize_preview(html_dir: str, filename: str) -> Response:
    """Serve a file from inside downloads/<html_dir>/ for iframe rendering.

    Path security: realpath confinement to DOWNLOAD_FOLDER. Only HTML files
    served (security defense — won't accidentally serve a logo or zip as
    text/html via misconfigured MIME).
    """
    if not filename.endswith(".html"):
        return ("Only .html files served", 400)
    target = os.path.realpath(os.path.join(DOWNLOAD_FOLDER, html_dir, filename))
    base = os.path.realpath(DOWNLOAD_FOLDER)
    if not target.startswith(base + os.sep):
        return ("Path traversal rejected", 400)
    if not os.path.isfile(target):
        return ("Not found", 404)
    return send_file(target, mimetype="text/html")


@app.route("/api/personalize/screenshot/<path:html_dir>", methods=["GET"])
def personalize_screenshot(html_dir: str) -> Response:
    """Generate (or fetch cached) PNG screenshot of before|after HTML.

    Query: ?which=before|after.
    Cache: downloads/<html_dir>/preview-{before,after}.png.
    Sync (Flask worker thread blocks ~2-3s on first call; instant on cache hit).
    """
    which = request.args.get("which")
    if which not in ("before", "after"):
        return jsonify({"error": "which must be 'before' or 'after'"}), 400

    base = os.path.realpath(DOWNLOAD_FOLDER)
    dir_path = os.path.realpath(os.path.join(DOWNLOAD_FOLDER, html_dir))
    if not dir_path.startswith(base + os.sep):
        return jsonify({"error": "Path traversal rejected"}), 400
    if not os.path.isdir(dir_path):
        return jsonify({"error": "Directory not found"}), 404

    src_filename = "index.html" if which == "before" else "personalized.html"
    src_path = os.path.join(dir_path, src_filename)
    if not os.path.isfile(src_path):
        return jsonify({"error": f"{src_filename} not found in {html_dir}"}), 404

    cache_path = os.path.join(dir_path, f"preview-{which}.png")
    if not os.path.isfile(cache_path):
        # Lazy generate via Playwright; reuse existing kratos_clone playwright deps
        _render_html_to_png(src_path, cache_path)

    return send_file(cache_path, mimetype="image/png")


def _render_html_to_png(src_html_path: str, out_png_path: str) -> None:
    """Render a local HTML file to a 1280×800 PNG via Playwright headless.

    Sync wrapper around async Playwright API. Caller is responsible for
    holding a Flask worker thread for ~2-3s. Failure modes (Playwright
    not installed, headless chromium missing, render crash) propagate as
    RuntimeError to the route, which logs + returns 500.
    """
    import asyncio
    from playwright.async_api import async_playwright

    async def _render() -> None:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                ctx = await browser.new_context(viewport={"width": 1280, "height": 800})
                page = await ctx.new_page()
                await page.goto(f"file://{src_html_path}", wait_until="networkidle", timeout=15000)
                await page.screenshot(path=out_png_path, full_page=False)
            finally:
                await browser.close()

    asyncio.run(_render())
```

**Why `send_file` for the preview HTML, not `render_template`:**
The personalized HTML lives outside the Flask `templates/` directory. We're
serving a static-but-dynamically-generated file. `send_file` is the right
primitive — Flask handles ETags, range requests, MIME headers, and
attachment-vs-inline disposition automatically.

**Why sync Playwright (asyncio.run) in a sync Flask route:**
Flask's default WSGI threading model already gives us one OS thread per
request. Wrapping the async Playwright API in `asyncio.run` creates a fresh
event loop scoped to that thread, then tears it down. Trade-off vs starting a
background worker queue: simpler, no new infrastructure, acceptable latency
(~2-3s on cache miss, instant on hit). Cap concurrency via gunicorn worker
count if it becomes a bottleneck.

### Frontend (`templates/personalize.html`)

**Replace `#output-summary` block (currently writes
`Saída: <code>{output_path}</code>` via `textContent + createElement`)
with a `result-card`:**

```html
<div class="result-card" id="result-card">
  <div class="result-card__meta">
    <span class="result-card__label">Saída</span>
    <code id="output-path-display"></code>
  </div>
  <button type="button" id="btn-open-preview" class="btn-primary" data-html-dir="">
    Abrir preview <span aria-hidden="true">→</span>
  </button>
</div>
```

**Add modal at end of `<main>` (or as last child of `<body>` before scripts):**

```html
<div id="preview-modal" class="preview-modal" hidden role="dialog"
     aria-modal="true" aria-labelledby="preview-modal-title">
  <div class="preview-modal__backdrop" data-close></div>
  <div class="preview-modal__panel">
    <header class="preview-modal__header">
      <h2 id="preview-modal-title">Preview do resultado</h2>
      <nav class="preview-modal__tabs" role="tablist" aria-label="Modos de preview">
        <button role="tab" data-tab="inspect" aria-selected="true"
                aria-controls="preview-pane-inspect" id="preview-tab-inspect">
          Inspecionar
        </button>
        <button role="tab" data-tab="thumb" aria-selected="false"
                aria-controls="preview-pane-thumb" id="preview-tab-thumb" tabindex="-1">
          Thumb
        </button>
        <button role="tab" data-tab="compare" aria-selected="false"
                aria-controls="preview-pane-compare" id="preview-tab-compare" tabindex="-1">
          Antes / Depois
        </button>
      </nav>
      <button type="button" data-close class="preview-modal__close" aria-label="Fechar preview">×</button>
    </header>
    <div class="preview-modal__body">
      <div role="tabpanel" id="preview-pane-inspect"
           aria-labelledby="preview-tab-inspect" class="preview-pane preview-pane--active">
        <iframe id="preview-iframe" title="Preview do site personalizado" sandbox="allow-same-origin"></iframe>
      </div>
      <div role="tabpanel" id="preview-pane-thumb"
           aria-labelledby="preview-tab-thumb" class="preview-pane" hidden>
        <div class="preview-thumb" id="preview-thumb-loading">Gerando thumb…</div>
        <img id="preview-thumb-img" alt="Thumb do site personalizado" hidden />
      </div>
      <div role="tabpanel" id="preview-pane-compare"
           aria-labelledby="preview-tab-compare" class="preview-pane" hidden>
        <div class="preview-compare" id="preview-compare-loading">Gerando antes/depois…</div>
        <div class="preview-compare__split" id="preview-compare-split" hidden>
          <div class="preview-compare__before">
            <span class="preview-compare__badge">ANTES</span>
            <img id="preview-compare-before-img" alt="Site original" />
          </div>
          <div class="preview-compare__after">
            <span class="preview-compare__badge preview-compare__badge--accent">DEPOIS</span>
            <img id="preview-compare-after-img" alt="Site personalizado" />
          </div>
        </div>
      </div>
    </div>
  </div>
</div>
```

**New JS module (inside existing IIFE in `personalize.html`):**

- `openPreviewModal(htmlDir, outputPath)` — populates result-card, sets
  iframe `src`, shows modal, traps focus, listens Esc + backdrop click.
- `closePreviewModal()` — hides modal, restores focus to `#btn-open-preview`.
- `switchPreviewTab(tabName)` — updates `aria-selected` + `tabindex`, shows
  matching pane, lazy-triggers `loadThumbForDir(htmlDir)` or
  `loadCompareForDir(htmlDir)` on first activation.
- `loadThumbForDir(htmlDir)` — fetches
  `/api/personalize/screenshot/<dir>?which=after`, sets img src, swaps
  loading state.
- `loadCompareForDir(htmlDir)` — `Promise.all` fetches before+after, sets
  both img srcs, swaps loading state.

**Modify existing `runBtn` success handler** to call
`openPreviewModal(htmlDir, output_path)` instead of just writing
`output-summary`. Requires `/api/personalize/run` to return `html_dir` in
the JSON response (currently only returns `output_path` per the existing
handler).

**Modify `personalize_run` route in `app.py`** to include `html_dir` in the
success JSON:

```python
# Existing:
return jsonify({"output_path": str(output_path)}), 200
# Becomes:
return jsonify({"output_path": str(output_path), "html_dir": html_dir_str}), 200
```

`html_dir_str` is the operator-provided form field, already validated for
traversal in the existing route.

### Data flow

1. Operator fills brief + uploads logo + picks `html_dir` → clicks
   "Personalizar site" (existing flow).
2. `/api/personalize/run` succeeds → returns
   `{output_path, html_dir}`.
3. Frontend handler:
   - Populates `#output-path-display` with output path.
   - Sets `#btn-open-preview` `data-html-dir` attribute.
   - Reveals result-card (was `#step-out` hidden).
   - Fires existing `markStepComplete(2)` + `markStepComplete(3)`.
4. Operator clicks "Abrir preview →".
5. `openPreviewModal(htmlDir, outputPath)`:
   - `#preview-modal` hidden=false.
   - `#preview-iframe` src=`/personalize/preview/<htmlDir>/personalized.html`.
   - Default tab = Inspecionar (already aria-selected).
   - Focus moves to first tab (`#preview-tab-inspect`).
   - Body scroll-lock applied (`overflow:hidden` on `<body>`).
6. Operator clicks "Thumb":
   - `switchPreviewTab('thumb')` updates aria + visibility.
   - If `#preview-thumb-img` has no `src` (first activation),
     `loadThumbForDir(htmlDir)`:
     - `fetch /api/personalize/screenshot/<dir>?which=after`.
     - Backend: cache miss → Playwright render (~2-3s) → cache write →
       return PNG. Cache hit → return PNG (~50ms).
     - Set `#preview-thumb-img src=` blob URL of response, hide loading.
7. Operator clicks "Antes / Depois":
   - `switchPreviewTab('compare')`.
   - If images not loaded, `loadCompareForDir(htmlDir)`:
     - `Promise.all([fetch ?which=before, fetch ?which=after])`.
     - Set both img srcs in parallel, hide loading state.
8. Operator closes:
   - Esc / backdrop click / X button → `closePreviewModal()`.
   - Modal hidden, focus restored to `#btn-open-preview`, body scroll-lock
     released.

### Error handling

| Failure | UX | Backend |
|---|---|---|
| Iframe load error (network, 404, CSP) | Pane shows "Falha ao carregar preview. <a target=_blank>Abrir em nova aba</a>" | Backend returns 4xx; iframe `onerror` listener catches |
| Screenshot Playwright crash | Pane shows "Falha ao gerar preview. <button>Tentar novamente</button>" | Route returns 500, structlog `screenshot_failed` event with `which` + `html_dir` |
| Path traversal attempt | Backend returns 400 + structlog `path_traversal_attempt` | Frontend treats as iframe load error |
| `html_dir` missing | Backend returns 404 | Frontend treats as fetch failure, shows error in pane |
| `index.html` missing (no original capture) | Compare tab shows "Sem captura original disponível neste diretório" for the before slot only; after still loads | Backend returns 404 on `?which=before` |
| Cache write fails (disk full) | Generation succeeds but next call regenerates; tax operator with extra latency | structlog `cache_write_failed` warning |
| Concurrent screenshot requests for same dir | Both Playwright instances run; last write wins on cache; not racy | Accept the duplication; not worth a lock for human-scale operator tool |

### Testing strategy

**Backend (`tests/test_preview_endpoint.py`, NEW):**
- `GET /personalize/preview/<dir>/<file>` happy path: serves valid HTML +
  correct `Content-Type: text/html`.
- Path traversal via `../`: returns 400.
- Path traversal via symlink: returns 400.
- File outside DOWNLOAD_FOLDER absolute path: returns 400.
- Non-HTML file requested: returns 400.
- Missing file: returns 404.
- `GET /api/personalize/screenshot/<dir>?which=after` happy path (mock
  Playwright + monkey-patch `_render_html_to_png` to write fake PNG):
  returns 200 + `Content-Type: image/png`.
- `?which=before` happy path: same.
- `?which=invalid`: returns 400.
- `?which` missing entirely: returns 400.
- Missing directory: returns 404.
- Cache hit: second call doesn't invoke the render function (mock-spy
  confirms zero calls on second request).
- Path traversal on screenshot endpoint: returns 400.

**Frontend regression (`tests/test_template_a11y.py`, EXTEND):**
- `#preview-modal` element present with `role="dialog"` +
  `aria-modal="true"` + `aria-labelledby="preview-modal-title"` + initial
  `hidden`.
- Exactly 3 `<button role="tab">` with `data-tab="inspect|thumb|compare"`.
- Default tab `aria-selected="true"` is `#preview-tab-inspect`.
- Result card `#result-card` with `#btn-open-preview` carrying
  `data-html-dir` attribute.
- JS functions present in source: `openPreviewModal`, `closePreviewModal`,
  `switchPreviewTab`, `loadThumbForDir`, `loadCompareForDir`.
- Esc key handler present in source.
- `iframe sandbox="allow-same-origin"` attribute present (security
  defense).
- `/api/personalize/run` response includes `html_dir` key (extend
  `tests/test_personalize_app.py` if such a test exists, else add minimal
  one).

**Playwright smoke pre-PR (manual, screenshots to `~/`):**
- Load `/personalize`, fill stub brief (skip API call by monkey-patching),
  inject a fake `output_path` + `html_dir` directly via `evaluate()` →
  click "Abrir preview" → iframe loads → click Thumb (mock screenshot
  endpoint via fixture) → click Antes/Depois → Esc → focus on button.
- Verify visual: modal centered, dark backdrop, glassmorphism on panel,
  3 tabs styled correctly, iframe scrollable, screenshots fit pane.

### Acceptance criteria

- [ ] `/personalize` shows result-card with "Abrir preview" button on
      personalize success.
- [ ] Modal opens on button click, default tab Inspecionar shows iframe
      rendering `personalized.html`.
- [ ] Thumb tab lazy-loads screenshot on first click; subsequent visits
      instant from cache.
- [ ] Antes/Depois tab lazy-loads both screenshots; split 50/50 layout
      with PT-BR badges.
- [ ] Esc + backdrop click + X close modal; focus restored to trigger
      button.
- [ ] WCAG: `role="dialog"`, `aria-modal="true"`, `aria-labelledby`,
      `aria-selected` on active tab, `tabindex="-1"` on inactive tabs.
- [ ] Backend path traversal rejected (test confirms).
- [ ] Backend invalid `which` rejected (test confirms).
- [ ] Cache hit on second screenshot request (mock-spy confirms).
- [ ] All gates green: pytest, ruff, mypy, bandit MEDIUM.
- [ ] Test count: 274 + ~14 new = ~288 passing.
- [ ] No regression in existing 274 tests.
- [ ] Playwright smoke screenshots show modal in all 3 tab states.

## Risks + plan B

| Risk | Plan B |
|---|---|
| Playwright headless not installed in production (CI/Docker image) | Add Playwright deps to `Dockerfile`; on render failure, return 500 with explicit "Playwright not available" message + log; UI shows retry |
| Iframe sandboxing blocks scripts in personalized.html | `sandbox="allow-same-origin"` permits CSS + same-origin XHR but blocks scripts by default. If operator complains, relax to `allow-same-origin allow-scripts` (security review required) |
| Personalized HTML references external CDN assets that fail under sandbox | Use existing `kratos_clone/post.py` `rewrite_html_assets` to ensure assets are local before personalize starts (already part of capture pipeline) |
| Modal layout breaks on narrow viewports | Modal panel max-width 95vw, fallback to vertical stacked tabs + smaller body on `< 720px` |
| Two operators concurrent on same dir generate dueling screenshots | Acceptable — last write wins on cache; both succeed |
| Disk fills up with cached PNGs from many runs | Each capture dir holds ≤ 2 PNGs (≤ ~1 MB total); manual cleanup is current operator workflow for `downloads/` |

## Out of scope (intentionally)

- Auto-regeneration of screenshots when `personalized.html` mtime changes
  (operator re-runs personalize manually → cache overwritten naturally).
- WebSocket push of preview updates.
- Visual diff highlighting between before and after.
- Mobile-specific layout for the modal.
- Print/export of the comparison.

## File map

- `app.py` — 2 new routes (~60 LOC), 1 helper, +`html_dir` in run response.
- `templates/personalize.html` — replace `#output-summary` (~5 LOC) with
  result-card (~12 LOC), add modal HTML at bottom (~50 LOC), add CSS
  (~140 LOC), add JS (~90 LOC).
- `tests/test_preview_endpoint.py` — NEW (~14 cases, ~200 LOC).
- `tests/test_template_a11y.py` — EXTEND (~9 new assertions).
- `docs/superpowers/specs/2026-05-16-personalize-preview-modal-design.md` —
  this file (NEW).
- `.gitignore` — `.superpowers/` line added.
