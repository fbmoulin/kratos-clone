# Personalize Preview Modal — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a visual preview of personalize output — a modal with 3 tabs (Inspecionar iframe / Thumb screenshot / Antes-Depois split) — backed by two new Flask endpoints that securely serve captured files and render screenshots.

**Architecture:** Two new `app.py` routes (`personalize_preview` serves files into a sandboxed iframe; `personalize_screenshot` lazily renders PNGs via Playwright). A shared `_validate_html_dir` realpath-confinement helper guards all three personalize routes. Frontend is a single inline `<script>`+`<style>` in `templates/personalize.html` (zero-build contract). Security is defense-in-depth: routing-layer single-segment `html_dir`, extension allowlist, realpath confinement, `send_from_directory` native protection, `sandbox="allow-scripts"` opaque-origin iframe, and a per-response CSP header.

**Tech Stack:** Flask, Python 3.12, `uv`, `pytest`, Playwright (Chromium headless), structlog. Branch `feat/personalize-preview-modal`. Test baseline: 276 passing.

**Source of truth:** Design spec `docs/superpowers/specs/2026-05-16-personalize-preview-modal-design.md` (plan-review-cycle R1+R2 complete, validator exit 0). The full route/render code lives in the spec's **Architecture → Backend** section (`app.py` block, spec lines 63–266); this plan references it by line range rather than duplicating 200 lines, and gives **complete code for the R2 deltas** (the changes layered on top).

**R2 finding → task map (the change set this plan applies on top of the spec):**
| R2 finding | Applied in |
|---|---|
| R2-PRC004 CSP header on preview route | Task 1 |
| R2-PRC007 isolated `_block_external` unit test | Task 2 |
| R2-PRC008 render semaphore in `create_app()` | Task 2 |
| R2-PRC003 portable symlink test | Task 3 |
| R2-PRC006 cache-clear after pipeline success | Task 3 |
| R2-PRC009 verified test-file structure | Task 3 |
| R2-PRC005 deterministic SPA fixture | Task 7 |
| R2-PRC010 (Advisory, No Plan Change) | — |

**Pre-flight (do once before Task 1):**
- [ ] `git status` clean on `feat/personalize-preview-modal`; `uv run pytest -q` → confirm **276 passed** baseline.
- [ ] Read spec `docs/superpowers/specs/2026-05-16-personalize-preview-modal-design.md` Architecture → Backend (lines 63–266) and Frontend (line 282+). The route bodies below reference it.
- [ ] Read `app.py` to confirm: `DOWNLOAD_FOLDER` value (~line 54), the `create_app(...)` factory signature (conftest calls `create_app(start_janitor=False, run_boot_cleanup=False)`), and how routes are registered (module-level `app` vs factory). This determines the exact wiring for the semaphore in Task 2.

---

### Task 1: Backend — `personalize_preview` endpoint (+ R2-PRC004 CSP header)

**Files:**
- Create: `tests/test_preview_endpoint.py`
- Modify: `app.py` (add `_PREVIEW_ALLOWED_EXTS`, `personalize_preview` route — spec lines 105–158, **plus the CSP block below**)

> **Fixtures do not exist yet** (verified: no `tmp_capture`/`tmp_capture_with_svg` anywhere; `tests/test_preview_endpoint.py` does not exist). Create them in Step 0. They build a real capture dir under the app's `DOWNLOAD_FOLDER` so `_validate_html_dir` (realpath-confined to `DOWNLOAD_FOLDER`) accepts them — a bare `tmp_path` would be rejected as outside-base. The cleanest approach is to point `DOWNLOAD_FOLDER` at a tmp dir for the test.
>
> **⚠️ Put these in `tests/conftest.py`, NOT in `test_preview_endpoint.py`.** Task 3 Step 4's failure-path test lives in `test_personalize_app.py` and also consumes `tmp_capture` — pytest fixtures are only shared across files when defined in `conftest.py`. Defining them in one test file makes them invisible to the other.

- [ ] **Step 0: Add capture fixtures to `tests/conftest.py`** (so both `test_preview_endpoint.py` and `test_personalize_app.py` can use them). `import os` is needed at the top of conftest (currently only imports `pytest`):

```python
import os
import pytest

@pytest.fixture
def capture_root(tmp_path, monkeypatch):
    """Point the app's DOWNLOAD_FOLDER at a tmp dir so _validate_html_dir accepts
    dirs created under it (realpath confinement is relative to DOWNLOAD_FOLDER)."""
    import app as app_module
    root = tmp_path / "downloads"; root.mkdir()
    monkeypatch.setattr(app_module, "DOWNLOAD_FOLDER", str(root))
    return root

@pytest.fixture
def tmp_capture(capture_root):
    """A capture dir <root>/cap1 with index.html + personalized.html + a css asset.
    Returns the single-segment dir name (per route's <string:html_dir> contract)."""
    d = capture_root / "cap1"; (d / "assets").mkdir(parents=True)
    (d / "index.html").write_text("<!doctype html><title>orig</title>")
    (d / "personalized.html").write_text("<!doctype html><title>new</title>")
    (d / "assets" / "style.css").write_text("body{color:red}")
    return "cap1"

@pytest.fixture
def tmp_capture_with_svg(tmp_capture, capture_root):
    """tmp_capture plus a logo.svg containing an inline <script> (the XSS vector
    that CSP script-src 'none' neutralizes — R2-PRC004)."""
    (capture_root / tmp_capture / "logo.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
    )
    return tmp_capture
```

> The `client` fixture (already in conftest) builds the app per test via `create_app()`; since `capture_root` monkeypatches `DOWNLOAD_FOLDER` (a module global that `_validate_html_dir` reads at call time, `app.py:96-97`), order doesn't matter — the route reads the patched value during the request. Both `test_preview_endpoint.py` and `test_personalize_app.py` get these fixtures for free via conftest.

- [ ] **Step 1: Write the failing tests** — `tests/test_preview_endpoint.py::TestPersonalizePreview`, 13 cases per spec Task 1.1 (happy `.html/.css/.png/.svg` + `Cache-Control`; security rejections: extension allowlist, double-extension `foo.html.txt`, `../`, `%2E%2E%2F`, symlink escape, absolute-path injection, missing file, missing dir). **Add two R2-PRC004 cases:**

```python
def test_preview_response_has_csp_script_none(client, tmp_capture):
    # tmp_capture fixture creates downloads/<dir>/index.html (see conftest)
    r = client.get(f"/personalize/preview/{tmp_capture}/index.html")
    assert r.status_code == 200
    csp = r.headers.get("Content-Security-Policy", "")
    assert "script-src 'none'" in csp
    assert "sandbox" in csp
    assert r.headers.get("X-Content-Type-Options") == "nosniff"

def test_preview_svg_kept_in_allowlist_with_csp(client, tmp_capture_with_svg):
    # .svg stays allowed; the CSP header (script-src 'none') neutralizes the vector
    r = client.get(f"/personalize/preview/{tmp_capture_with_svg}/logo.svg")
    assert r.status_code == 200
    assert "script-src 'none'" in r.headers.get("Content-Security-Policy", "")
```

- [ ] **Step 2: Run to verify red** — `uv run pytest tests/test_preview_endpoint.py::TestPersonalizePreview -v` → FAIL (route undefined).

- [ ] **Step 3: Implement** `_PREVIEW_ALLOWED_EXTS` + `personalize_preview` exactly as spec lines 105–158, **then add the CSP + nosniff headers** to the success response (alongside the existing R2-PRC002 ACAO/Vary headers, before `return resp`):

```python
        # R2-PRC004 (approved 2026-05-30): defense-in-depth CSP served WITH the
        # file response. A document's own CSP stacks independently on the iframe
        # sandbox (most-restrictive wins), so script-src 'none' kills the
        # SVG-as-top-level-document inline-script vector even though the iframe
        # carries allow-scripts. <img>-referenced SVG still renders (script-inert).
        # Keep .svg in the allowlist. Residual in-iframe phishing risk is inherent
        # to previewing operator-captured content and is accepted under the trust model.
        resp.headers["Content-Security-Policy"] = (
            "default-src 'none'; img-src 'self' data:; "
            "style-src 'self' 'unsafe-inline'; font-src 'self'; "
            "script-src 'none'; sandbox"
        )
        resp.headers["X-Content-Type-Options"] = "nosniff"
```

- [ ] **Step 4: Run to verify green** — `uv run pytest tests/test_preview_endpoint.py::TestPersonalizePreview -v` → PASS (all 15).

- [ ] **Step 5: Commit**

```bash
git add tests/test_preview_endpoint.py app.py
git commit -m "feat(personalize): add preview file-serving endpoint with CSP hardening (R1-PRC001, R2-PRC004)"
```

---

### Task 2: Backend — `personalize_screenshot` + render (+ R2-PRC007 isolated test, R2-PRC008 semaphore in factory)

**Files:**
- Modify: `tests/test_preview_endpoint.py` (add `TestPersonalizeScreenshot`)
- Modify: `app.py` (add `RenderCapacityExhausted`, `_render_html_to_png`, `personalize_screenshot` — spec lines 77–266; **semaphore now lives in `create_app()`** per R2-PRC008)

- [ ] **Step 1: Write the failing tests** — `TestPersonalizeScreenshot`, 11 cases per spec Task 2.1, but with these two R2 adjustments:
  - **R2-PRC008 (capacity override via env):** do NOT use `importlib.reload(app)`. **Verified wiring:** `app = Flask(__name__)` is created at module level (`app.py:28`); routes are registered at module level via `@app.route` decorators (`app.py:248+`); `create_app()` (`app.py:218`) only initializes side-effecting parts (limiter storage, janitor, boot cleanup) and **returns that same module-level `app` singleton** (`return app`, line 245). So calling `create_app(...)` with a monkeypatched env re-runs the semaphore construction on the singleton's `config`. This is safe because conftest's `flask_app`/`client` fixtures are **function-scoped** (verified — no `scope=`) and already call `create_app(...)` per test.

```python
def test_capacity_override_via_env(monkeypatch):
    monkeypatch.setenv("KCD_MAX_CONCURRENT_RENDERS", "1")
    from app import create_app
    test_app = create_app(start_janitor=False, run_boot_cleanup=False)
    sem = test_app.config["RENDER_SEMAPHORE"]
    # Semaphore exposes its initial value via _value before any acquire
    assert sem._value == 1
```

  > **Executor verify:** confirm conftest fixtures are function-scoped (not `scope="session"`). If session-scoped, place this test LAST or add a fixture that restores the prior app, since re-calling `create_app()` mutates the shared global.

  - **R2-PRC007 (external network blocked):** test the handler in isolation — no real Playwright:

```python
import asyncio

def test_block_external_aborts_non_file_urls():
    from app import _block_external  # extracted to module level (see Step 3)
    aborted, continued = [], []

    class FakeRequest:
        def __init__(self, url): self.url = url
    class FakeRoute:
        def __init__(self, url): self.request = FakeRequest(url)
        async def abort(self): aborted.append(self.request.url)
        async def continue_(self): continued.append(self.request.url)

    asyncio.run(_block_external(FakeRoute("https://fonts.googleapis.com/x.css")))
    asyncio.run(_block_external(FakeRoute("file:///tmp/index.html")))
    assert aborted == ["https://fonts.googleapis.com/x.css"]
    assert continued == ["file:///tmp/index.html"]
```

  Keep the remaining spec cases (happy before/after + Cache-Control; invalid `which`; missing dir; path traversal; cache-hit no-render via mock-spy; atomic write under concurrency; bounded-concurrency 503). Mock Playwright via monkey-patch of `_render_html_to_png` for the route-level cases.

- [ ] **Step 2: Run to verify red** — `uv run pytest tests/test_preview_endpoint.py::TestPersonalizeScreenshot -v` → FAIL.

- [ ] **Step 3: Implement** per spec lines 77–266, with two structural changes:
  - **Extract `_block_external` to module level** (R2-PRC007) so it is unit-testable, and call it from inside `_render_html_to_png`:

```python
async def _block_external(route):
    """Abort non-file:// requests during screenshot render (R1-PRC002).
    Module-level so it is unit-testable without a live Playwright instance (R2-PRC007)."""
    if route.request.url.startswith("file:"):
        await route.continue_()
    else:
        await route.abort()
```

  - **Move the semaphore into `create_app()`** (R2-PRC008). Remove module-level `_MAX_CONCURRENT_RENDERS`/`_RENDER_SEMAPHORE`. Inside `create_app()`:

```python
    # R2-PRC008 (approved 2026-05-30): construct at app-build time so the test
    # factory + monkeypatch.setenv picks up overrides without importlib.reload.
    app.config["RENDER_SEMAPHORE"] = threading.Semaphore(
        int(os.getenv("KCD_MAX_CONCURRENT_RENDERS", "2"))
    )
```

  `_render_html_to_png` acquires `current_app.config["RENDER_SEMAPHORE"]` (import `from flask import current_app`). Keep `RenderCapacityExhausted`, the 15s acquire timeout, atomic `tempfile.mkstemp`+`os.replace`, and the `_block_external` route registration exactly as spec.

- [ ] **Step 4: Run to verify green** — `uv run pytest tests/test_preview_endpoint.py -v` → PASS (Task 1 + Task 2 classes).

- [ ] **Step 5: Commit**

```bash
git add tests/test_preview_endpoint.py app.py
git commit -m "feat(personalize): add screenshot render endpoint; semaphore in factory + testable network guard (R1-PRC002/3/4, R2-PRC007/008)"
```

---

### Task 3: Backend — `_validate_html_dir` + retrofit `personalize_run` (+ R2-PRC003 portable symlink test, R2-PRC006 cache ordering, R2-PRC009)

**Files:**
- Modify: `tests/test_preview_endpoint.py` (add `TestValidateHtmlDir`, 9 cases)
- Modify: `tests/test_personalize_app.py` (**verified: exists, 8 test functions** — R2-PRC009) — add run-response + cache-clear assertions
- Modify: `app.py` (`_validate_html_dir` per spec lines 81–102; `personalize_run` retrofit)

- [ ] **Step 1: Write `TestValidateHtmlDir`** — 8 platform-independent cases per spec Task 3.1 (`""`, `"."`, `"./"`, `"   "`, `"/etc"`, `"../etc"`, `"foo/../../etc"`, valid-dir→realpath). **Plus the R2-PRC003 portable symlink case:**

```python
import sys, os, pytest

@pytest.mark.skipif(sys.platform == "win32",
                    reason="os.symlink requires admin/Developer Mode on Windows")
def test_validate_html_dir_rejects_symlink_escape(tmp_path, monkeypatch):
    import app as app_module
    base = tmp_path / "downloads"; base.mkdir()
    outside = tmp_path / "outside"; outside.mkdir()
    (outside / "secret.html").write_text("x")
    os.symlink(outside, base / "evil")               # symlink inside base → outside
    monkeypatch.setattr(app_module, "DOWNLOAD_FOLDER", str(base))
    assert app_module._validate_html_dir("evil") is None   # realpath resolves outside → rejected
    # teardown: tmp_path auto-cleans; no manual unlink needed
```

- [ ] **Step 2: Run red** — `uv run pytest tests/test_preview_endpoint.py::TestValidateHtmlDir -v` → FAIL.
- [ ] **Step 3: Implement `_validate_html_dir`** exactly per spec lines 81–102. Run green.
- [ ] **Step 4: Extend `tests/test_personalize_app.py`** (R2-PRC009 — file confirmed present): (a) `/api/personalize/run` JSON includes `html_dir` matching the form field; (b) empty `html_dir` → 400; (c) **R2-PRC006 success path**: seed pre-existing `preview-before.png`+`preview-after.png`, mock pipeline to no-op success, invoke run, assert both PNGs deleted; (d) **R2-PRC006 failure path**:

```python
def test_run_pipeline_failure_does_not_clear_or_regenerate(client, tmp_capture, monkeypatch):
    # seed a stale preview, force pipeline to raise.
    # personalize_run does a function-local `from personalize.pipeline import run_pipeline`,
    # so patch the DEFINITION site (personalize.pipeline.run_pipeline) — the local import
    # re-resolves the attribute at call time and picks up the mock.
    stale = os.path.join(DOWNLOAD_FOLDER, tmp_capture, "preview-after.png")
    open(stale, "wb").close()
    def _raise(*a, **k):
        raise RuntimeError("pipeline boom")
    monkeypatch.setattr("personalize.pipeline.run_pipeline", _raise)
    r = client.post("/api/personalize/run", data={"html_dir": tmp_capture, ...})  # fill required form fields
    assert r.status_code >= 400          # route catches the exception → existing error response (400/502)
    # cache-clear is success-gated: it lives in the success branch AFTER run_pipeline returns.
    # On failure it never runs, so no stale-then-regenerated-as-current screenshot is produced.
    assert os.path.isfile(stale)         # stale preview untouched (not deleted, not regenerated as current)
```

> **Executor note:** the real pipeline symbol is `run_pipeline` in `personalize/pipeline.py` (NOT `run_personalize_pipeline`). The route imports it locally and catches all exceptions, returning 400/502 rather than re-raising.

- [ ] **Step 5: Run red** — `uv run pytest tests/test_personalize_app.py -v` → new cases FAIL.
- [ ] **Step 6: Modify `personalize_run`** — (a) use `_validate_html_dir` (replace inline confinement, spec lines 658–662 area); (b) **R2-PRC006: move the `glob('preview-*.png')`+unlink to AFTER the pipeline returns successfully** (inside the success branch, before building the JSON response — NOT before the pipeline call); on exception the delete does not run and the existing error response is returned; (c) include `html_dir` in the JSON response.
- [ ] **Step 7: Run green** — `uv run pytest tests/test_preview_endpoint.py tests/test_personalize_app.py -v` → PASS.
- [ ] **Step 8: Commit**

```bash
git add tests/test_preview_endpoint.py tests/test_personalize_app.py app.py
git commit -m "feat(personalize): shared path-validation helper + success-gated cache clear; portable symlink test (R1-PRC007, R2-PRC003/006/009)"
```

---

### Task 4: Frontend — modal HTML + CSS structure

**Files:** Modify `tests/test_template_a11y.py`; Modify `templates/personalize.html`.

- [ ] **Step 1:** a11y regression cases per spec Task 4.1: `#preview-modal` `role=dialog`+`aria-modal=true`+`aria-labelledby`+`hidden`; 3 `<button role=tab>` with `data-tab`, default `aria-selected=true` on `inspect`; `#result-card` with `#btn-open-preview`+`data-html-dir`; iframe `sandbox="allow-scripts"` **asserting `allow-same-origin` substring ABSENT**. Run red.
- [ ] **Step 2:** Replace `#output-summary` with `#result-card`; add modal markup at end of `<main>`; add CSS (glassmorphism, responsive, `prefers-reduced-motion` guard) extending existing `:root` tokens — **no new hex, no new fonts** (CLAUDE.md contract). Run green.
- [ ] **Step 3: Commit** — `git commit -m "feat(personalize): preview modal markup + styles (R1-PRC006)"`

---

### Task 5: Frontend — modal JS (open/close + tabs)

**Files:** Modify `tests/test_template_a11y.py`; Modify `templates/personalize.html`.

- [ ] **Step 1:** assert source contains `openPreviewModal`, `closePreviewModal`, `switchPreviewTab`, Esc handler, `.preview-modal__backdrop[data-close]`. Run red.
- [ ] **Step 2:** implement handlers inside the existing IIFE; wire `#btn-open-preview` → `openPreviewModal(htmlDir, outputPath)`. Run green.
- [ ] **Step 3: Commit** — `git commit -m "feat(personalize): modal open/close + tab switching"`

---

### Task 6: Frontend — lazy thumb + compare loaders

**Files:** Modify `tests/test_template_a11y.py`; Modify `templates/personalize.html`.

- [ ] **Step 1:** assert source contains `loadThumbForDir`, `loadCompareForDir`, `/api/personalize/screenshot/` fetch. Run red.
- [ ] **Step 2:** implement lazy loaders wired to tab activation. Run green.
- [ ] **Step 3: Commit** — `git commit -m "feat(personalize): lazy screenshot loaders for thumb + compare tabs"`

---

### Task 7: Playwright smoke (manual, pre-PR) (+ R2-PRC005 deterministic SPA fixture)

**Files:** Create `tests/fixtures/spa_sample.html`; run smoke manually.

- [ ] **Step 1: Create `tests/fixtures/spa_sample.html`** (R2-PRC005) — a single self-contained file, **no network calls**, with inline JS implementing (a) a click toggle and (b) a no-dependency carousel:

```html
<!doctype html><html><body>
<button id="toggle">Toggle</button><div id="panel" hidden>shown</div>
<div id="carousel"><span class="slide active">1</span><span class="slide">2</span></div>
<button id="next">Next</button>
<script>
  document.getElementById('toggle').onclick = () =>
    document.getElementById('panel').toggleAttribute('hidden');
  let i = 0; const s = [...document.querySelectorAll('.slide')];
  document.getElementById('next').onclick = () => {
    s[i].classList.remove('active'); i = (i+1) % s.length; s[i].classList.add('active');
  };
</script></body></html>
```

- [ ] **Step 2:** Start Flask (`uv run python app.py`), navigate `/personalize`, inject fake personalize success via `browser.evaluate()`, open preview, switch tabs, close. Screenshots → `/home/fbmoulin/preview-modal-smoke-*.png`.
- [ ] **Step 3: R2-PRC005 assertion** — load `spa_sample.html` in the Inspecionar iframe; via Playwright MCP assert the toggle flips `#panel` `hidden` on click and the carousel `.active` advances. This is the **verifiable** form of "SPA scripts work" (enabled by `sandbox=allow-scripts`). Note: captured SPAs making live API calls render their own error/empty states — faithful reproduction, out of scope.
- [ ] **Step 4: R2-PRC002 font check** — load a capture with self-hosted `@font-face` woff; `evaluate(() => getComputedStyle(document.body).fontFamily)` matches the captured font (not `sans-serif`). Confirms ACAO header.
- [ ] **Step 5: Commit** — `git add tests/fixtures/spa_sample.html && git commit -m "test(personalize): deterministic SPA fixture + Playwright smoke (R2-PRC005, R2-PRC002)"`

---

### Task 8: Gate sweep + PR

- [ ] `uv run pytest -q` → all pass (baseline 276 + new; verify delta via `git diff main -- tests/ | grep -c '^+.*def test_'`).
- [ ] `uv run ruff check kratos_clone/ scripts/ app.py && uv run ruff format --check kratos_clone/ scripts/ app.py` → clean.
- [ ] `uv run mypy app.py` → clean; `uv run bandit -r app.py --severity-level medium` → 0 findings.
- [ ] **Ask user before push** (push requires explicit approval per global CLAUDE.md): then `git push -u origin feat/personalize-preview-modal` && `gh pr create`.
- [ ] `gh pr checks <PR#> -R fbmoulin/kratos-clone --watch` → green. Ask user for merge approval.

---

## Notes for the executor
- **Spec is authoritative for bulk route code** (lines 63–266); this plan gives complete code only for the R2 deltas layered on top. Read both.
- **Do not** add a build pipeline, ESLint/Prettier, new fonts, or new hex colors (CLAUDE.md contracts). **Do not** add `Co-Authored-By` trailers. Use `uv add`, never `pip`.
- **R2-PRC008 wiring (verified):** `create_app()` does `global app; ...; return app` — one module-level singleton (line 59), routes registered inside the factory. Construct the semaphore in `create_app()` via `app.config["RENDER_SEMAPHORE"] = threading.Semaphore(int(os.getenv("KCD_MAX_CONCURRENT_RENDERS", "2")))`. `_render_html_to_png` reads it via `from flask import current_app` → `current_app.config["RENDER_SEMAPHORE"]` (runs inside a request context). Do NOT keep a module-level `_RENDER_SEMAPHORE` — that is the import-time-binding bug R2-PRC008 fixes.
- **Pipeline symbol (verified):** `personalize_run` calls `run_pipeline` (function-local `from personalize.pipeline import run_pipeline`) and catches all exceptions, returning 400/502. Patch `personalize.pipeline.run_pipeline` in tests.
- Mock OpenAI/Playwright in unit tests; live calls are gated (`RUN_OPENAI_LIVE=1`, real Playwright in smoke only).
