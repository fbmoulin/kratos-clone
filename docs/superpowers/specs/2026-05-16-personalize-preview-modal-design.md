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
- Auto-regeneration when underlying files change OUTSIDE of re-personalize
  (re-personalize itself clears stale cache per R1-PRC008; other external
  modifications of `personalized.html` are outside scope).

## Architecture

### Backend

**New file: none.** Both endpoints added to `app.py`.

```python
# R1-PRC004 (Round 1, approved 2026-05-16): bound Playwright concurrency at the
# process level so simultaneous render requests don't OOM the VPS. Chromium
# headless-shell (Playwright 1.57+ default) is ~150MB resident at idle and
# ~706MB peak during render. Default cap of 2 → 1.4GB peak; sized for VPS ≥ 2GB.
# Override via env var KCD_MAX_CONCURRENT_RENDERS.
_MAX_CONCURRENT_RENDERS = int(os.getenv("KCD_MAX_CONCURRENT_RENDERS", "2"))
_RENDER_SEMAPHORE = threading.Semaphore(_MAX_CONCURRENT_RENDERS)


class RenderCapacityExhausted(Exception):
    """Raised when _RENDER_SEMAPHORE.acquire times out (R1-PRC004)."""


def _validate_html_dir(html_dir_str: str) -> str | None:
    """Resolve html_dir_str to an absolute path confined to DOWNLOAD_FOLDER.

    R1-PRC007 (approved 2026-05-16): single source of truth for path security
    policy. Shared by personalize_run + personalize_preview + personalize_screenshot
    to prevent divergence-bug-of-a-single-time. Returns realpath if safe, None if
    rejected.

    Rejections:
      - empty / whitespace-only / "." / "./"  (would resolve to DOWNLOAD_FOLDER itself)
      - absolute paths or traversal escaping DOWNLOAD_FOLDER
      - symlinks pointing outside DOWNLOAD_FOLDER
    """
    if not html_dir_str or html_dir_str.strip() in ("", ".", "./"):
        return None
    target = os.path.realpath(os.path.join(DOWNLOAD_FOLDER, html_dir_str))
    base = os.path.realpath(DOWNLOAD_FOLDER)
    if target == base:
        return None  # resolves to DOWNLOAD_FOLDER itself, not a subdir
    if not target.startswith(base + os.sep):
        return None  # escapes DOWNLOAD_FOLDER
    return target


# R1-PRC001 (Round 1, approved 2026-05-16): allowlist extensions matching the
# capture pipeline output (index.html, assets/*.{png,css,js,...}, styles.json).
# send_from_directory has native path-traversal protection + auto MIME via
# mimetypes.guess_type + ETag/Cache-Control. <path:asset_path> accepts "/" so
# subdir requests like assets/foo.png route correctly.
_PREVIEW_ALLOWED_EXTS = frozenset({
    ".html", ".css", ".js", ".png", ".jpg", ".jpeg", ".gif", ".svg",
    ".webp", ".woff", ".woff2", ".ttf", ".eot", ".ico", ".json",
    ".mp3", ".mp4", ".webm",
})

@app.route("/personalize/preview/<path:html_dir>/<path:asset_path>", methods=["GET"])
def personalize_preview(html_dir: str, asset_path: str) -> Response:
    """Serve a file from inside downloads/<html_dir>/ for iframe rendering.

    Security layers:
    1. Extension allowlist (defends against double-extension bypass like foo.html.txt)
    2. realpath confinement on html_dir (defends against ../, absolute paths)
    3. send_from_directory native path-traversal protection on asset_path
    """
    from flask import send_from_directory
    from werkzeug.exceptions import NotFound

    ext = os.path.splitext(asset_path)[1].lower()
    if ext not in _PREVIEW_ALLOWED_EXTS:
        return (f"Extension {ext!r} not allowed", 400)
    # R1-PRC007: use shared _validate_html_dir helper for path security policy.
    dir_path = _validate_html_dir(html_dir)
    if dir_path is None:
        return ("html_dir invalid or outside downloads/", 400)
    if not os.path.isdir(dir_path):
        return ("Directory not found", 404)
    try:
        return send_from_directory(dir_path, asset_path, max_age=3600)
    except (FileNotFoundError, NotFound):
        return ("Not found", 404)


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

    # R1-PRC007: use shared _validate_html_dir helper for path security policy.
    dir_path = _validate_html_dir(html_dir)
    if dir_path is None:
        return jsonify({"error": "html_dir invalid or outside downloads/"}), 400
    if not os.path.isdir(dir_path):
        return jsonify({"error": "Directory not found"}), 404

    src_filename = "index.html" if which == "before" else "personalized.html"
    src_path = os.path.join(dir_path, src_filename)
    if not os.path.isfile(src_path):
        return jsonify({"error": f"{src_filename} not found in {html_dir}"}), 404

    cache_path = os.path.join(dir_path, f"preview-{which}.png")
    if not os.path.isfile(cache_path):
        # Lazy generate via Playwright; reuse existing kratos_clone playwright deps
        try:
            _render_html_to_png(src_path, cache_path)
        except RenderCapacityExhausted:
            # R1-PRC004: bounded concurrency triggered. Tell client to retry.
            resp = jsonify({"error": "render capacity exhausted, try again in a moment"})
            resp.headers["Retry-After"] = "30"
            return resp, 503

    return send_file(cache_path, mimetype="image/png")


def _render_html_to_png(src_html_path: str, out_png_path: str) -> None:
    """Render a local HTML file to a 1280×800 PNG via Playwright headless.

    Concurrency-bounded (R1-PRC004, approved 2026-05-16): acquires
    _RENDER_SEMAPHORE with 15s timeout. On timeout, raises
    RenderCapacityExhausted → route returns 503 + Retry-After: 30 header.

    Atomic write pattern (R1-PRC003, approved 2026-05-16): renders to
    tempfile.mkstemp() in the SAME directory as out_png_path so os.replace
    is genuinely atomic (cross-filesystem would degrade to copy+delete).
    On success: atomically replaces out_png_path. On failure: temp file
    cleaned up, out_png_path untouched (next request regenerates).

    No os.fsync before replace — cache is regenerable; +50-200ms not worth
    it for non-crash-critical data.
    """
    import asyncio
    import tempfile
    from playwright.async_api import async_playwright

    if not _RENDER_SEMAPHORE.acquire(timeout=15):
        raise RenderCapacityExhausted()

    try:
        out_dir = os.path.dirname(out_png_path)
        tmp_fd, tmp_path = tempfile.mkstemp(suffix=".png.tmp", dir=out_dir)
        os.close(tmp_fd)  # Playwright opens the path itself

        try:
            async def _render() -> None:
                async with async_playwright() as p:
                    browser = await p.chromium.launch(headless=True)
                    try:
                        ctx = await browser.new_context(viewport={"width": 1280, "height": 800})
                        page = await ctx.new_page()

                        # R1-PRC002 (approved 2026-05-16): abort all non-file:// requests
                        # to avoid hanging on slow/dead external CDN refs (Google Fonts,
                        # analytics). Trade-off: external fonts render as system fallback
                        # in the screenshot. Iframe preview (Inspecionar tab) is unaffected
                        # — browser fetches external normally there.
                        async def _block_external(route):
                            if route.request.url.startswith("file:"):
                                await route.continue_()
                            else:
                                await route.abort()
                        await page.route("**/*", _block_external)

                        await page.goto(f"file://{src_html_path}", wait_until="load", timeout=8000)
                        await page.screenshot(path=tmp_path, full_page=False)
                    finally:
                        await browser.close()

            asyncio.run(_render())
            os.replace(tmp_path, out_png_path)  # atomic on POSIX + Windows
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
    finally:
        _RENDER_SEMAPHORE.release()
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
        <iframe id="preview-iframe" title="Preview do site personalizado" sandbox="allow-scripts"></iframe>
        <p class="preview-pane__note">Preview executa scripts em origem isolada — chamadas de API, cookies e storage da página original não funcionam aqui.</p>
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

**Modify `personalize_run` route in `app.py`** (three changes per R1-PRC007 + R1-PRC008):

1. Replace inline realpath confinement with the shared `_validate_html_dir` helper.
2. Before invoking the pipeline, clear stale preview cache files:

```python
# R1-PRC008 (approved 2026-05-16): clear stale preview cache before re-personalizing.
# Cache is keyed by (html_dir, which) without content hash; re-personalize would
# otherwise serve the previous run's screenshots. Best-effort delete; failures are
# tolerable because the next render replaces atomically via R1-PRC003 pattern.
import glob
for stale in glob.glob(os.path.join(dir_path, "preview-*.png")):
    try:
        os.unlink(stale)
    except OSError:
        pass
```

3. Include `html_dir` in the success JSON response:

```python
# Existing:
return jsonify({"output_path": str(output_path)}), 200
# Becomes:
return jsonify({"output_path": str(output_path), "html_dir": html_dir_str}), 200
```

`html_dir_str` is the operator-provided form field; security validation is
performed by `_validate_html_dir(html_dir_str)` per R1-PRC007.

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
| Concurrent screenshot requests for same dir | **R1-PRC003 (approved 2026-05-16):** Both Playwright instances render to unique `tempfile.mkstemp()` temps in the same directory; `os.replace` atomically swaps cache file. Last write wins on cache file; `send_file` never sees a truncated PNG (replace is atomic). On crash mid-render: temp file leaked but cache file unaffected; next request regenerates. | atomic write pattern in `_render_html_to_png` |
| Render concurrency exceeds cap (OOM risk) | **R1-PRC004 (approved 2026-05-16):** `_RENDER_SEMAPHORE` (default 2 slots, overridable via `KCD_MAX_CONCURRENT_RENDERS` env var) bounds simultaneous Playwright launches. On `acquire(timeout=15)` failure → raises `RenderCapacityExhausted` → route returns 503 + `Retry-After: 30` header. Memory expectation documented (~1.4GB peak at default cap). | semaphore wrapping `_render_html_to_png`; 503 in `personalize_screenshot` route |
| Preview cache stale after re-personalize | **R1-PRC008 (approved 2026-05-16):** `personalize_run` deletes `preview-*.png` files in target dir BEFORE invoking pipeline. Cache is keyed by `(html_dir, which)` without content hash; without explicit clear, operator would see previous run's screenshot. Best-effort `try/except OSError` (next render replaces atomically via R1-PRC003). | glob delete in `personalize_run` |

### Testing strategy

**Backend (`tests/test_preview_endpoint.py`, NEW):**

`/personalize/preview/<dir>/<asset_path>` — happy paths:
- `.html` at root (personalized.html): 200 + `Content-Type: text/html; charset=utf-8`
- `.css` at root: 200 + `Content-Type: text/css`
- `.png` in `assets/` subdir: 200 + `Content-Type: image/png`
- `.svg` in `assets/`: 200 + `Content-Type: image/svg+xml`
- `Cache-Control: max-age=3600` header present

`/personalize/preview/<dir>/<asset_path>` — security rejections (R1-PRC001):
- Extension not in allowlist (`.exe`, `.sh`, `.php`): 400
- Double-extension bypass (`foo.html.txt`): 400 (`.txt` not allowed)
- Path traversal via `../`: 400
- Path traversal via URL-encoded `%2E%2E%2F`: 400 (Flask decodes before routing)
- Path traversal via symlink escape: 400
- `html_dir` absolute path injection (`html_dir="/etc"`): 400
- Missing file in valid dir: 404
- Missing dir: 404
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
- **Atomic write under concurrency (R1-PRC003):** mock Playwright to write
  a known-sized fake PNG with `time.sleep(0.5)` between open/close. Fire
  2 threads calling `_render_html_to_png(src, same_target)` simultaneously.
  Assert: `os.path.getsize(target) == fake_size` (never truncated). Assert:
  polling `os.path.exists(target)` every 50ms during the race shows either
  absent OR full size, never partial bytes.
- **Bounded concurrency (R1-PRC004):** patch `_MAX_CONCURRENT_RENDERS=2`,
  mock Playwright to `time.sleep(20)` per render. Fire 3 parallel calls to
  `_render_html_to_png` (different targets). Assert: first 2 acquire
  semaphore + render; 3rd raises `RenderCapacityExhausted` within ~15s of
  start (semaphore timeout). Route-level: 3rd request via test client
  returns 503 + `Retry-After: 30` header + JSON error body.
- **Capacity override via env (R1-PRC004):** monkey-patch
  `KCD_MAX_CONCURRENT_RENDERS=1`, reload module, assert
  `_MAX_CONCURRENT_RENDERS == 1`.
- **External network blocked at render (R1-PRC002):** HTML referencing
  `<img src="https://nonexistent.example.com/foo.png">` AND
  `<link href="https://fonts.googleapis.com/...">` renders within < 3s
  (not hung waiting for 8s timeout). Spy on `_block_external` confirms
  abort() called for non-file:// URLs and continue_() for file:// URLs.

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
- `iframe sandbox="allow-scripts"` attribute present (security defense per
  R1-PRC006). Assertion checks both: `sandbox="allow-scripts"` literal
  present AND `allow-same-origin` substring ABSENT (to prevent regression
  to the forbidden combo).
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
      rendering `personalized.html` **with CSS + images loaded from `assets/`
      subdir under the same path-confined route** (R1-PRC001) **and SPA
      scripts running in opaque origin (R1-PRC006) — animations, carousels,
      hover/click handlers all work**.
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
- [ ] Backend bounds render concurrency at `_MAX_CONCURRENT_RENDERS` (default 2).
      Excess concurrent requests get 503 + `Retry-After: 30` (R1-PRC004).
- [ ] Single `_validate_html_dir` helper enforces path security policy across
      all 3 routes (personalize_run + personalize_preview + personalize_screenshot),
      with dedicated 9-case test class (R1-PRC007).
- [ ] Re-personalizing same `html_dir` invalidates stale preview cache
      (R1-PRC008) — operator never sees previous run's screenshot.
- [ ] Screenshots render with system-fallback fonts when capture references
      external CDN fonts (R1-PRC002). Iframe (Inspecionar tab) loads external
      fonts normally — both modes preview-only with different fidelity trade-offs.
- [ ] All gates green: pytest, ruff, mypy, bandit MEDIUM.
- [ ] **R1-PRC009 (approved 2026-05-16):** +~32 net new tests across
      `tests/test_preview_endpoint.py` (~22 cases: 13 `TestPersonalizePreview`
      + 11 `TestPersonalizeScreenshot` + 9 `TestValidateHtmlDir`; actual count
      varies with parameterize) and `tests/test_template_a11y.py` (~10 modal
      a11y cases). Net delta verifiable via
      `git diff main -- tests/ | grep '^+.*def test_'` — checkable under any
      baseline shift.
- [ ] All pre-existing tests still pass (no regression).
- [ ] Playwright smoke screenshots show modal in all 3 tab states.

## Risks + plan B

| Risk | Plan B |
|---|---|
| Playwright headless not installed in production (CI/Docker image) | Add Playwright deps to `Dockerfile`; on render failure, return 500 with explicit "Playwright not available" message + log; UI shows retry |
| Iframe sandboxing blocks scripts in personalized.html | **R1-PRC006 (Round 1, approved 2026-05-16):** Use `sandbox="allow-scripts"` (NOT `allow-same-origin`). SPAs run in opaque-origin context — scripts execute (animations, hover/click, carousels work) but can't access parent window, can't fetch our `/api/*` (same-origin block), can't read cookies. The combo `allow-scripts allow-same-origin` is forbidden by MDN/web.dev guidance because framed page can remove sandbox attribute, fully negating it. Trade-off: AJAX from inside the captured site fails — but those calls target the original (now-gone) backend, so they'd fail anyway. Visual preview is intact. |
| Personalized HTML references external CDN assets that fail under sandbox | Use existing `kratos_clone/post.py` `rewrite_html_assets` to ensure assets are local before personalize starts (already part of capture pipeline) |
| External CDN refs cause Playwright `wait_until="load"` to hang on slow trackers | **R1-PRC002 (approved 2026-05-16):** `page.route("**/*", _block_external)` aborts all non-file:// requests at the network layer. Render completes in local-only time (~1-2s) regardless of external network state. Timeout reduced from 15s → 8s. Trade-off: screenshots render external fonts as system fallback; iframe preview is unaffected (uses browser's normal fetch). |
| Modal layout breaks on narrow viewports | Modal panel max-width 95vw, fallback to vertical stacked tabs + smaller body on `< 720px` |
| Two operators concurrent on same dir generate dueling screenshots | Acceptable — last write wins on cache; both succeed |
| Disk fills up with cached PNGs from many runs | Each capture dir holds ≤ 2 PNGs (≤ ~1 MB total); manual cleanup is current operator workflow for `downloads/` |

## Execution order (TDD-first)

**R1-PRC005 (approved 2026-05-16):** Each task = write tests (red) →
implement minimal code (green) → commit. Backend tasks ship before
frontend so endpoints exist when frontend JS first runs. Reading the
plan top-to-bottom in this order ensures tests are NEVER written
after the code they cover.

**Task 1 — Backend: `personalize_preview` endpoint (R1-PRC001 + R1-PRC007)**
1. Write 13 cases in `tests/test_preview_endpoint.py::TestPersonalizePreview`
   (happy paths .html/.css/.png/.svg + Cache-Control; security rejections:
   extension allowlist, double-extension, `../`, `%2E%2E%2F`, symlink escape,
   absolute path injection, missing file/dir). Run: **red**.
2. Implement `_PREVIEW_ALLOWED_EXTS` constant + `personalize_preview` route
   in `app.py`. Run: **green**.
3. Commit.

**Task 2 — Backend: `personalize_screenshot` endpoint (R1-PRC002 + R1-PRC003 + R1-PRC004)**
1. Write 11 cases in `tests/test_preview_endpoint.py::TestPersonalizeScreenshot`
   (happy paths before/after + Cache-Control; invalid `which`; missing dir;
   path traversal; cache hit no-render via mock-spy; atomic write under
   concurrency; bounded concurrency 503; env var override; external network
   blocked). Mock Playwright via dependency injection or monkey-patch.
   Run: **red**.
2. Implement `_MAX_CONCURRENT_RENDERS` + `_RENDER_SEMAPHORE` +
   `RenderCapacityExhausted` + `_render_html_to_png` (with atomic write +
   route abort + 8s timeout) + `personalize_screenshot` route. Run: **green**.
3. Commit.

**Task 3 — Backend: `_validate_html_dir` helper + retrofit `personalize_run` (R1-PRC007)**
1. Write 9 cases in `tests/test_preview_endpoint.py::TestValidateHtmlDir`:
   `""` → None; `"."` → None; `"./"` → None; `"   "` → None;
   `"/etc"` → None (absolute escape); `"../etc"` → None (traversal);
   `"foo/../../etc"` → None (mid-path traversal); `"valid-dir"` → realpath
   when dir exists; symlink-out → None (use `os.symlink` in fixture).
   Run: **red**.
2. Implement `_validate_html_dir` in `app.py` (module-level). Run: **green**.
3. Extend `tests/test_personalize_app.py`: (a) assert
   `/api/personalize/run` JSON response includes `html_dir` key matching
   the form field; (b) assert empty `html_dir` form field returns 400
   (was previously coupled to the missing-field check);
   (c) **R1-PRC008**: setup pre-existing `preview-after.png` +
   `preview-before.png` in target dir, mock pipeline to no-op, invoke
   personalize_run, assert both PNG files were deleted. Run: **red**.
4. Modify `personalize_run` to (a) use `_validate_html_dir` instead of
   inline realpath confinement, (b) glob+delete `preview-*.png` files
   in target dir before invoking pipeline (R1-PRC008), (c) include
   `html_dir` in JSON response. Run: **green**.
5. Commit.

**Task 4 — Frontend: modal HTML + CSS structure (R1-PRC006)**
1. Write a11y regression cases in `tests/test_template_a11y.py`:
   `#preview-modal` exists with `role=dialog` + `aria-modal=true` +
   `aria-labelledby` + `hidden` initial; 3 `<button role=tab>` with
   `data-tab` + default `aria-selected=true` on `inspect`;
   `#result-card` with `#btn-open-preview` + `data-html-dir`;
   iframe has `sandbox="allow-scripts"` (asserts `allow-same-origin`
   substring ABSENT). Run: **red**.
2. Replace `#output-summary` with `#result-card` markup. Add modal markup
   at end of `<main>`. Add CSS for modal + glassmorphism + responsive +
   reduced-motion guard. Run: **green** (HTML asserts pass; visual
   verification deferred to Task 7).
3. Commit.

**Task 5 — Frontend: modal JS — open/close + tab switching**
1. Extend `test_template_a11y.py`: assert source contains
   `openPreviewModal`, `closePreviewModal`, `switchPreviewTab`,
   Esc key handler, `.preview-modal__backdrop[data-close]`. Run: **red**.
2. Implement JS handlers inside existing IIFE. Wire `#btn-open-preview`
   click → `openPreviewModal(htmlDir, outputPath)`. Run: **green**.
3. Commit.

**Task 6 — Frontend: lazy thumb + compare loaders**
1. Extend `test_template_a11y.py`: assert source contains
   `loadThumbForDir`, `loadCompareForDir`, `/api/personalize/screenshot/`
   fetch. Run: **red**.
2. Implement lazy-load functions; wire to tab activation. Run: **green**.
3. Commit.

**Task 7 — Playwright smoke test pre-PR (manual, not in CI)**
1. Start local Flask, navigate `/personalize`, inject fake personalize
   success via `browser.evaluate()`, click "Abrir preview", switch tabs,
   close. Capture screenshots to `/home/fbmoulin/preview-modal-smoke-*.png`.
2. Visual verification: modal centered, dark backdrop, glassmorphism on
   panel, 3 tabs styled correctly, iframe scrollable, screenshots fit pane,
   SPA scripts run (R1-PRC006), CSS + images load (R1-PRC001).
3. If anything visual is wrong, fix CSS + re-run smoke.
4. Final commit.

**Task 8 — Gate sweep + PR**
- `pytest -q` (all pass), `ruff check + format` (clean), `mypy` (clean),
  `bandit --severity-level medium` (0 findings).
- `git push -u origin feat/personalize-preview-modal`.
- `gh pr create`.
- Watch CI green, ask user for merge approval.

---

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
- `.gitignore` — `.superpowers/` line added (R1-PRC010 (approved 2026-05-16):
  this brainstorming session used the visual-companion server, which writes
  mockup files to `.superpowers/brainstorm/<session-id>/`; ignoring prevents
  pollution of feature commits with throwaway scratch files. Bundled in the
  spec commit because coupling is direct — the gitignore line exists
  precisely because this spec was authored via the brainstorming workflow).

## Plan Review Log

### Review Round 1

reviewer_model: claude-opus-4-7
reviewer_prompt: code-plan-reviewer@v0.4
date: 2026-05-16
spec_reviewed: docs/superpowers/specs/2026-05-16-personalize-preview-modal-design.md
plan_reviewed: docs/superpowers/specs/2026-05-16-personalize-preview-modal-design.md
diverse_critics: false

#### Findings

##### Finding R1-PRC001: iframe src cross-origin / asset resolution will fail

status: Resolved
severity: Critical
location: Architecture → Backend, personalize_preview route; Data flow step 5; Risks row "external CDN assets"

reviewer_concern: |
  iframe set to src=/personalize/preview/<htmlDir>/personalized.html. Flask send_file returns only that one HTML byte stream. Relative asset URLs inside personalized.html (./assets/foo.png, ./css/site.css) resolve against iframe doc URL, browser requests /personalize/preview/<htmlDir>/assets/foo.png. Route only accepts files ending in .html (if not filename.endswith(".html"): return 400). Every asset request will 400 and iframe renders unstyled/broken.

why_it_matters: |
  Inspecionar tab is default + primary value. Operator clicks "Abrir preview", sees broken naked-DOM page on the headline path.

decision: Accept reviewer suggestion (a) — switch to send_from_directory + extension allowlist, route parameter changed to <path:asset_path> to accept subdirs like assets/foo.png. Allowlist covers capture pipeline output: html/css/js/png/jpg/jpeg/gif/svg/webp/woff/woff2/ttf/eot/ico/json/mp3/mp4/webm. SVG kept in allowlist despite XSS risk because trust model = operator-captured assets (same boundary as R1-PRC006 sandbox decision).

plan_changes_made: |
  1. Architecture → Backend section: replaced personalize_preview implementation. New code uses send_from_directory with native traversal protection + auto MIME + Cache-Control max-age=3600. Added module-level constant _PREVIEW_ALLOWED_EXTS frozenset. Route signature changed from <path:filename> to <path:asset_path>. Triple-layered security: extension allowlist + realpath confinement on html_dir + send_from_directory protection on asset_path.
  2. Testing strategy → Backend tests section: expanded from 6 vague cases to 13 cases. Happy paths now cover .html/.css/.png/.svg + Cache-Control header. Security rejections enumerate: extension not in allowlist, double-extension bypass (foo.html.txt), ../ traversal, URL-encoded %2E%2E%2F, symlink escape, html_dir absolute path injection (/etc), missing file (404), missing dir (404).
  3. Acceptance criteria: bullet for modal default tab now requires "iframe renders styled (CSS + images loaded from assets/ subdir under same path-confined route)".

no_change_rationale: |

human_approver: Felipe
approval_status: Approved
approval_date: 2026-05-16

##### Finding R1-PRC002: Playwright networkidle + 15s timeout unreliable on external CDN assets

status: Resolved
severity: Major
location: Architecture → Backend, _render_html_to_png helper

reviewer_concern: |
  await page.goto(file://..., wait_until="networkidle", timeout=15000). For file:// pages referencing external CDN (fonts.googleapis.com, analytics) in sandboxed/no-internet env, goto spins until 15s timeout → 500. Risks table acknowledges external-CDN risk but doesn't connect to Playwright behavior or specify fallback.

why_it_matters: |
  Screenshot tab failure rate non-trivial whenever capture has one external font/analytics. Operator sees "Falha ao gerar preview" + Tentar novamente that fails identically. Silently shifts burden to operators.

decision: Accept reviewer concern; partial fix already in R1-PRC003 commit (networkidle → load). Adding complete fix per Playwright 2026 best practices research: page.route() abort handler for non-file:// URLs. wait_until="load" is correct primitive (CSS + images needed for screenshot; domcontentloaded would screenshot text-only). External CDN abort prevents slow trackers from blocking load event. Timeout dropped 15s → 8s since render is now local-only. Trade-off: screenshots render external fonts as system fallback (acceptable for preview purpose); iframe Inspecionar tab unaffected.

plan_changes_made: |
  1. _render_html_to_png helper: added async _block_external route handler that aborts non-file:// requests and continues file:// requests. await page.route("**/*", _block_external) installed before page.goto. Timeout reduced 15000 → 8000 (8s).
  2. Error handling table: added "External CDN refs cause Playwright wait_until='load' to hang" row documenting the route.abort solution + trade-off (system-fallback fonts in screenshot, iframe unaffected).
  3. Testing strategy → Backend tests: added test for HTML referencing 2 external assets (img + link to fonts.googleapis.com) — renders in < 3s with route blocking active. Spy confirms abort() for non-file:// and continue_() for file://.
  4. Acceptance criteria: added bullet documenting fallback-font behavior in screenshots vs iframe (preview-only with different fidelity).

no_change_rationale: |

human_approver: Felipe
approval_status: Approved
approval_date: 2026-05-16

##### Finding R1-PRC003: Concurrent screenshot requests corrupt cache file mid-write

status: Resolved
severity: Major
location: Architecture → Backend, screenshot route + _render_html_to_png; Error handling row "Concurrent"

reviewer_concern: |
  Two simultaneous requests for same ?which=after both miss cache, both spawn Playwright, both call page.screenshot(path=out_png_path). send_file can serve truncated/0-byte response if it opens between writer's open(..., "w") and rename. Plan dismisses as "last write wins" but cache check is os.path.isfile, so broken PNG is cached forever.

why_it_matters: |
  Operator clicks Thumb in two tabs in quick succession (or refreshes modal during render), gets broken-image icon cached as result. Cache-poisoning failure mode plan documented as "acceptable" without recognizing it.

decision: Accept. Atomic write pattern via tempfile.mkstemp() + os.replace() — Python stdlib idiomatic, atomic on POSIX + Windows. Temp file in SAME directory as out_png_path so os.replace is genuinely atomic (cross-FS would degrade to copy+delete). On render success: atomic swap. On render failure: temp leaked, cache_path untouched. No os.fsync — cache is regenerable, +50-200ms not worth it for non-crash-critical data. Concurrent renders just race to swap; last write wins atomically; send_file never sees truncated bytes.

plan_changes_made: |
  1. Architecture → Backend section: rewrote _render_html_to_png. New code: tempfile.mkstemp(suffix=".png.tmp", dir=out_dir) → close fd → Playwright writes to tmp_path → on success os.replace(tmp_path, out_png_path) (atomic) → on exception os.unlink(tmp_path) cleanup. Also switched wait_until from "networkidle" to "load" (partial R1-PRC002 fix; full timeout strategy still pending in that finding).
  2. Error handling table, "Concurrent screenshot requests" row: rewrote from "Accept the duplication; not worth a lock" to document the atomic write pattern explicitly with reference to _render_html_to_png implementation.
  3. Testing strategy → Backend tests: added concurrent atomic-write test. Mocks Playwright to write known-sized fake PNG with time.sleep(0.5) between open/close, fires 2 threads simultaneously, asserts cache file is either absent OR full size (never partial bytes) via 50ms polling during the race.

no_change_rationale: |

human_approver: Felipe
approval_status: Approved
approval_date: 2026-05-16

##### Finding R1-PRC004: No concurrency cap on Playwright launches — memory OOM risk

status: Resolved
severity: Major
location: Architecture → Backend, "Why sync Playwright" rationale

reviewer_concern: |
  Plan says "Cap concurrency via gunicorn worker count if it becomes a bottleneck" but adds no process-level semaphore. Chromium headless ~150-300MB per instance. Compare tab Promise.all spawns 2 Chromiums per click. Three concurrent operators (or single operator's Compare action) can blow past 1GB RAM on small VPS.

why_it_matters: |
  Acceptance criteria don't include concurrency/memory bound. Implementer following plan literally has no signal there's a ceiling. OOM-killer can take down Flask itself, not just the render.

decision: Accept. Web research (datawookie 2025, Rendershot) measured Chromium-headless-shell at ~150MB resident idle and ~706MB peak per render — reviewer estimate was conservative. Pattern: threading.Semaphore(N) module-level + 503 + Retry-After. Chose simple per-request browser launch (Option A) over shared-browser-pool (Option B) — operator-tool has low concurrency (1 op, max 2 simultaneous via Compare tab Promise.all); Option B adds singleton/thread-safety/leak-risk complexity for marginal latency gain. Default cap 2 → 1.4GB peak; sized for VPS ≥ 2GB. Overridable via env var KCD_MAX_CONCURRENT_RENDERS (follows KCD_* pattern documented in README). Playwright 1.57+ confirmed in pyproject.toml — chromium-headless-shell is the default headless binary (lower footprint than full Chrome).

plan_changes_made: |
  1. Architecture → Backend section: added module-level _MAX_CONCURRENT_RENDERS constant (reads KCD_MAX_CONCURRENT_RENDERS env var, default 2), _RENDER_SEMAPHORE threading.Semaphore, and RenderCapacityExhausted exception class. Documented memory footprint expectation in comment.
  2. _render_html_to_png helper: wrapped existing render+atomic-write logic with _RENDER_SEMAPHORE.acquire(timeout=15) / release(). On acquire timeout raises RenderCapacityExhausted.
  3. personalize_screenshot route: catches RenderCapacityExhausted → returns 503 + Retry-After: 30 header + JSON error body.
  4. Error handling table: added "Render concurrency exceeds cap" row documenting the semaphore behavior + env var override.
  5. Testing strategy → Backend tests: added 2 cases — (a) bounded concurrency (3 parallel renders, 3rd gets RenderCapacityExhausted or route 503 within ~15s), (b) env var override test (KCD_MAX_CONCURRENT_RENDERS=1 monkey-patch).
  6. Acceptance criteria: added bullet "Backend bounds render concurrency at _MAX_CONCURRENT_RENDERS (default 2). Excess concurrent requests get 503 + Retry-After: 30".

no_change_rationale: |

human_approver: Felipe
approval_status: Approved
approval_date: 2026-05-16

##### Finding R1-PRC005: No explicit TDD ordering in tasks

status: Resolved
severity: Major
location: Testing strategy + Acceptance criteria

reviewer_concern: |
  User constraint says TDD is project mode for new behavior. Plan presents architecture/backend implementation in app.py first, then testing strategy, then acceptance criteria. No task ordering, no enumerated step-by-step sequence. Implementer reading top-to-bottom writes route first then bolts tests on after.

why_it_matters: |
  Test-after for security-sensitive code (path traversal, MIME forcing) is exactly where TDD pays off. Without explicit ordering, R1-PRC001 iframe-asset gap becomes test-after fire-fighting.

decision: Accept. Added explicit "Execution order (TDD-first)" section before "Out of scope" with 8 numbered tasks. Each task = write tests (red) → implement minimal code (green) → commit. Backend tasks (1-3) ship before frontend (4-6) so endpoints exist when frontend JS first runs. Playwright smoke (7) is the visual verification gate before final commit. Task 8 = gate sweep + PR. The implementer reading top-to-bottom in this order has the correct red-before-green discipline locked in by structure.

plan_changes_made: |
  1. Added new top-level section "Execution order (TDD-first)" between "Acceptance criteria" and "Out of scope (intentionally)". Contains 8 numbered tasks, each with explicit (1) write tests (red), (2) implement (green), (3) commit substeps.
  2. Task 1 covers personalize_preview endpoint (R1-PRC001 + R1-PRC007 tests).
  3. Task 2 covers personalize_screenshot endpoint (R1-PRC002 + R1-PRC003 + R1-PRC004 tests).
  4. Task 3 covers extending personalize_run to return html_dir.
  5. Tasks 4-6 cover frontend (modal HTML/CSS, modal JS, lazy loaders).
  6. Task 7 covers Playwright smoke (visual verification gate).
  7. Task 8 covers gate sweep + PR open.

no_change_rationale: |

human_approver: Felipe
approval_status: Approved
approval_date: 2026-05-16

##### Finding R1-PRC006: iframe sandbox="allow-same-origin" strips scripts but SPAs need them

status: Resolved
severity: Major
location: Frontend HTML, <iframe sandbox=...>; Risks row "iframe sandboxing"

reviewer_concern: |
  Plan ships sandbox="allow-same-origin" as default, says "If operator complains, relax to allow-scripts". Default preview renders ALL JS disabled. Every captured SPA (project's stated focus per CLAUDE.md "5 SPA-recall patches") displays loading skeleton or empty containers.

why_it_matters: |
  Same critical-path failure as R1-PRC001 but different reason. Inspecionar is default tab + primary UX value. Shipping default-broken preview for ~all SPA captures is misalignment between security default and the actual content. "Relax if operator complains" — but operator IS the only user.

decision: Accept the SPIRIT of reviewer suggestion (enable scripts) but REJECT the literal proposal (allow-scripts allow-same-origin). Web research confirms that combo is a documented anti-pattern (MDN/web.dev/Mozilla addons rule explicitly forbid it because framed page can remove sandbox attribute from parent, fully negating sandboxing). Correct choice is sandbox="allow-scripts" ALONE — scripts execute in opaque-origin context. SPAs render visually (animations, hover, carousels) while iframe cannot access parent window, fetch our /api/*, or read cookies. AJAX inside captured site fails — but those calls target original (now-gone) backend, so they'd fail anyway.

plan_changes_made: |
  1. Frontend HTML, modal section: changed iframe sandbox attribute from sandbox="allow-same-origin" to sandbox="allow-scripts". Added <p class="preview-pane__note"> below iframe explaining "Preview executa scripts em origem isolada — chamadas de API, cookies e storage da página original não funcionam aqui."
  2. Risks table, iframe sandboxing row: rewrote to document the choice + cite the security research + explain the trade-off (visual preview intact; only original-backend AJAX calls fail, which they would anyway).
  3. Testing strategy → Frontend regression: tightened assertion. Now requires BOTH sandbox="allow-scripts" literal present AND allow-same-origin substring ABSENT (locks against regression to the forbidden combo).
  4. Acceptance criteria: bullet for modal default tab now requires "SPA scripts running in opaque origin (R1-PRC006) — animations, carousels, hover/click handlers all work".

no_change_rationale: |

human_approver: Felipe
approval_status: Approved
approval_date: 2026-05-16

##### Finding R1-PRC007: html_dir validation gaps not exhaustively tested

status: Resolved
severity: Major
location: Architecture → Frontend "Modify personalize_run"; Data flow step 2

reviewer_concern: |
  Plan claims "html_dir_str already validated for traversal in existing route" without quoting the validation. Flask path converter accepts /, so html_dir could be foo/../bar. New endpoints DO realpath-confine (double-layered) but test matrix doesn't enumerate: URL-encoded ..%2F, mixed separators, html_dir starting with / (absolute path injection into os.path.join — os.path.join("/downloads", "/etc") returns "/etc").

why_it_matters: |
  If existing personalize_run validation has been weakened in refactor or never matched spec, plan inherits bug silently. Security gaps in path handling.

decision: Accept. Direct inspection of personalize_run validation in app.py confirmed it IS sound for security cases (absolute paths, ../, URL-encoded already decoded by Flask). But: (a) plan duplicated the same realpath confinement pattern in 3 routes — DRY violation creating bug-of-a-single-time risk if any endpoint diverges; (b) edge cases like "" and "." passed security but caused 500 downstream with unclear messages. Refactor: factor into single _validate_html_dir(html_dir_str) -> str | None helper, used by all 3 routes. Single source of truth for path security policy + cleaner UX errors for edge cases.

plan_changes_made: |
  1. Architecture → Backend section: added _validate_html_dir helper function between RenderCapacityExhausted and _PREVIEW_ALLOWED_EXTS. Rejects: empty/whitespace, ".", "./", absolute paths, traversal, symlink escape. Returns realpath if safe.
  2. personalize_preview route: replaced inline realpath confinement with dir_path = _validate_html_dir(html_dir); if dir_path is None: return 400.
  3. personalize_screenshot route: same replacement.
  4. Execution order Task 3: expanded from 3 substeps to 5. Now: (1) write 9 cases for TestValidateHtmlDir (red), (2) implement helper (green), (3) extend test_personalize_app.py for html_dir in response + empty-string 400 (red), (4) modify personalize_run to use helper + include html_dir in JSON response (green), (5) commit.
  5. Acceptance criteria: added bullet noting single helper enforces policy across all 3 routes with 9-case dedicated test class.

no_change_rationale: |

human_approver: Felipe
approval_status: Approved
approval_date: 2026-05-16

##### Finding R1-PRC008: Stale preview cache after re-personalize

status: Resolved
severity: Minor
location: Architecture → Backend, screenshot route

reviewer_concern: |
  Cache keyed by (html_dir, which) with no version/hash. If operator re-personalizes same html_dir (overwriting personalized.html), cached PNG is stale. Plan dismisses in Out-of-scope as "cache overwritten naturally" but cache file is preview-after.png, NOT personalized.html — nothing in personalize pipeline knows about preview artifacts.

why_it_matters: |
  Operator re-personalizes, opens preview, sees OLD screenshot. No signal what they see is from previous run.

decision: Accept reviewer's Option B (delete stale PNGs in personalize_run before invoking pipeline). Chosen over Option A (hash-based cache key) for simplicity and bounded disk usage. Option A would compute SHA256 on every screenshot request, accumulate historical PNGs needing cleanup, and require endpoint signature change. Option B is a 4-line glob+unlink in personalize_run, proportional side effect (route already creates personalized.html in same dir), no disk accumulation (always 2 PNGs max per dir).

plan_changes_made: |
  1. Architecture → Frontend section, "Modify personalize_run route" subsection: expanded from 1 change (include html_dir) to 3 changes — (a) use _validate_html_dir per R1-PRC007, (b) glob+delete preview-*.png files BEFORE invoking pipeline per R1-PRC008, (c) include html_dir in JSON response. Code snippet shows glob.glob + try/except OSError best-effort delete (next render replaces atomically via R1-PRC003).
  2. Error handling table: added "Preview cache stale after re-personalize" row documenting the glob delete pattern.
  3. Out of scope section: tightened bullet about auto-regeneration to exclude re-personalize case (now handled) — only external modifications of personalized.html remain out of scope.
  4. Execution order Task 3 substep 3: added (c) — setup pre-existing preview-*.png files in target dir, assert personalize_run deleted them. Substep 4: added (b) — glob+delete in implementation.
  5. Acceptance criteria: added bullet "Re-personalizing same html_dir invalidates stale preview cache".

no_change_rationale: |

human_approver: Felipe
approval_status: Approved
approval_date: 2026-05-16

##### Finding R1-PRC009: Test count "274 + ~14 = ~288" fragile

status: Resolved
severity: Advisory
location: Acceptance criteria

reviewer_concern: |
  Pinning exact passing test count couples PR to current snapshot. If any unrelated PR lands first, baseline shifts. Acceptance bullet becomes tripwire saying nothing about whether THIS plan's tests passed.

why_it_matters: |
  Fragile assertion; advisory only.

decision: Accept. Replaced absolute-count phrasing with delta-based phrasing verifiable via `git diff main -- tests/ | grep '^+.*def test_'`. Also bumped estimate from "~14" to "~32" to reflect the expanded test scope from findings R1-PRC001 (13 personalize_preview cases), R1-PRC002+3+4 (added concurrency + atomic write + external network cases), R1-PRC007 (9-case TestValidateHtmlDir), R1-PRC008 (cache cleanup case). Honest sizing > round-number tripwire.

plan_changes_made: |
  1. Acceptance criteria: removed "Test count: 274 + ~14 new = ~288 passing" bullet. Added new bullet citing per-file breakdown (~22 backend cases across 3 test classes + ~10 frontend a11y cases) and the git diff verification command. Kept "no regression in pre-existing tests" as a separate substantive bullet.

no_change_rationale: |

human_approver: Felipe
approval_status: Approved
approval_date: 2026-05-16

##### Finding R1-PRC010: .gitignore .superpowers/ scope creep without rationale

status: Resolved
severity: Advisory
location: File map last bullet

reviewer_concern: |
  File map includes .gitignore — .superpowers/ line added but nothing in plan body explains what .superpowers/ is or why it appears now. Looks like incidental tooling artifact in PR.

why_it_matters: |
  Minor PR hygiene concern; advisory only.

decision: Accept reviewer's documentation concern; reject the split-commit suggestion. Bundling .gitignore + spec commit is justified because the coupling is direct — `.superpowers/brainstorm/` was created PRECISELY by the brainstorming workflow that produced this spec, in the same session. Adding a docstring to the file map removes the "scope creep" appearance without the refactor cost of unwinding and re-committing.

plan_changes_made: |
  1. File map: replaced terse ".gitignore — .superpowers/ line added" with rationale-rich docstring naming the visual-companion server, the brainstorming-session-id subdir convention, and the coupling justification for bundling in the spec commit.

no_change_rationale: |

human_approver: Felipe
approval_status: Approved
approval_date: 2026-05-16
