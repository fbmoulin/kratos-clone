# Spec — U1 elapsed timer + U5 captures dropdown

**Date:** 2026-05-14
**Status:** approved (skipping plan/review — Alta complexity but well-bounded)
**Closes:** TODO/audit P1 items **U1** and **U5**

## Objective

Reduce two operator-pain frictions identified in the UX audit (see PR #24
commit message and the `🟡 P1 — UX` table from session 2026-05-11):

- **U1**: during a `WebsiteDownloader.process()` run (30s–3min wall-clock),
  the UI only shows an indeterminate spinner + `"Processando…"`. Operator
  has no signal whether the job is alive or stuck.
- **U5**: `/personalize` step-1 asks for a `downloads/<dir>` name in a
  free-text input. Operator must remember or guess. There's no listing.

## Scope

### In

1. New backend endpoint `GET /api/captures` → JSON list of capture
   directories (subdirs of `DOWNLOAD_FOLDER` that aren't session UUIDs).
2. `/personalize` `<input id="html-dir">` swapped for an `<input
   list="captures-list">` + `<datalist>`. JS fetches `/api/captures` on
   page load and populates the datalist.
3. `/` (index.html) — wall-clock elapsed timer integrated into the button
   text during processing (`"Processando — 23s"`). 1s resolution.
   Cleared on `done` event or error.

### Out (deferred to other follow-ups)

- Step indicator (1/3, 2/3, 3/3) in `/personalize` (U6).
- SSE reconnect/timeout logic (P2).
- localStorage of last URL (U8).
- Server-Sent progress events that include % completion (would need
  `downloader.py` instrumentation — bigger lift).

## Architecture

### Backend: `GET /api/captures`

```python
@app.route("/api/captures", methods=["GET"])
def list_captures() -> Response:
    """List capture directories operator can target from /personalize."""
    captures: list[str] = []
    if os.path.isdir(DOWNLOAD_FOLDER):
        for entry in sorted(os.listdir(DOWNLOAD_FOLDER)):
            path = os.path.join(DOWNLOAD_FOLDER, entry)
            if not os.path.isdir(path):
                continue          # skip .zip files
            try:
                uuid.UUID(entry)  # raises if not a session-id dir
                continue          # skip session dirs (in-flight or post-fail)
            except ValueError:
                pass
            captures.append(entry)
    return jsonify({"captures": captures})
```

**Why no rate-limit:** read-only, no auth, low-cost. Matches `/health`
precedent.

**Why no auth:** the app is single-tenant operator-tool (per CLAUDE.md);
the `downloads/` listing has no PII or secret material beyond what the
operator already chose to capture.

**Why sort alphabetical:** deterministic = testable + predictable for
operator.

### Frontend (1): `/personalize` datalist

```html
<input list="captures-list" id="html-dir" placeholder="ex: site-A" autocomplete="off">
<datalist id="captures-list">
  <!-- populated by JS on page load -->
</datalist>
```

```js
fetch('/api/captures').then(r => r.json()).then(data => {
    var dl = document.getElementById('captures-list');
    (data.captures || []).forEach(name => {
        var opt = document.createElement('option');
        opt.value = name;
        dl.appendChild(opt);
    });
    if (!data.captures || !data.captures.length) {
        // soft hint, not blocking
        $('html-dir').placeholder = 'Nenhuma captura ainda — rode um download em /';
    }
});
```

**Why datalist (not select):** free-text preserved (operator can still
type a path that isn't on disk yet, useful for advanced flows). No
blocking on cold-start.

### Frontend (2): index.html elapsed timer

```js
let elapsedTimer = null;
let elapsedSeconds = 0;

function setLoading(loading) {
    // ... existing code ...
    if (loading) {
        elapsedSeconds = 0;
        elapsedTimer = setInterval(() => {
            elapsedSeconds += 1;
            btnText.textContent = 'Processando — ' + elapsedSeconds + 's';
        }, 1000);
        btnText.textContent = 'Processando — 0s';
    } else {
        if (elapsedTimer) { clearInterval(elapsedTimer); elapsedTimer = null; }
        btnText.textContent = 'Baixar Réplica';
    }
}
```

**Why 1s resolution:** below ~700ms updates feel jittery; above 2s feels
laggy. 1s is the standard human-perceptible interval.

**Why button text (not separate element):** zero new DOM, single source
of truth, testable. Trade-off: button width may shift mid-run; mitigated
by the icon-less, fixed-padding button style already in place.

## Task decomposition

| # | Task | Files | ~Time | Test |
|---|------|-------|-------|------|
| T1 | Backend: `/api/captures` + tests | `app.py`, `tests/test_captures_endpoint.py` (new) | 20m | empty dir, mixed UUIDs+real dirs, zip filter, sort order, no DOWNLOAD_FOLDER |
| T2 | Frontend: datalist + JS in `personalize.html` | `templates/personalize.html` | 15m | extend `test_template_a11y.py`: datalist exists, fetches /api/captures |
| T3 | Frontend: elapsed timer in `index.html` | `templates/index.html` | 15m | extend `test_template_a11y.py`: timer state present in JS source |
| T4 | Gate sweep + commit + PR | — | 10m | pytest, ruff, mypy, bandit |

## Dependencies

- None between T1/T2/T3 (independent), but T2 + T3 both touch templates
  so they share the regression-test extension in T4.

## Risks + plan B

| Risk | Plan B |
|------|--------|
| `os.listdir` race vs concurrent capture write | Acceptable in single-operator scale; tests use `tmp_path` so no race |
| Timer drift when tab backgrounded (browser throttle) | Acceptable — feedback only, not correctness-critical |
| Datalist not supported on older browsers | Falls back to plain input (free-text), which was the previous behavior |
| Empty `downloads/` on first run | Empty list + placeholder hint guides operator |

## Test strategy

- `tests/test_captures_endpoint.py` (new, ~6 cases): happy path, empty
  dir, missing dir, UUID skip, zip skip, sort order
- `tests/test_template_a11y.py` (extend, ~3 cases): datalist present,
  page-load fetch, timer JS present in index source

No live integration tests (no API calls; pure filesystem + DOM).

## Acceptance criteria

- [ ] `GET /api/captures` returns `{"captures": [...]}` JSON with only
      directory entries that are not valid UUIDs
- [ ] `/personalize` HTML contains `<datalist id="captures-list">`
- [ ] `/personalize` JS fetches `/api/captures` on page load
- [ ] `/` HTML JS contains elapsed-timer state variables (`elapsedTimer`,
      `elapsedSeconds`) and a `setInterval` invocation tied to loading
- [ ] All gates green: pytest, ruff, mypy, bandit MEDIUM
- [ ] Total tests: ≥ 242 (233 baseline + ~9 new cases)
- [ ] No regression in existing 233 tests
- [ ] No alteration of code outside scope (downloader.py, kratos_clone/,
      personalize/ Python untouched; only app.py + 2 templates + 2 test
      files)
