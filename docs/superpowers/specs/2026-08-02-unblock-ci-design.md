# SPEC v2 — Unblock kratos-clone CI

**Supersedes** `SPEC-unblock-ci-2026-08-02.md`, which received verdict **REWORK** from
`.premortems/PREMORTEM-2026-08-02T04-48-33Z.md` (5 high / 9 medium / 2 low). v1 is kept
for the record; do not implement it.

**Status:** PROPOSED — not implemented. Nothing in the repo has been modified except the
unarchive (operator-authorised, 2026-08-01).
**Target repo:** `fbmoulin/kratos-clone` — PUBLIC, unarchived. `main` @ `7587cd3`.
**Delivery:** three PRs in sequence, not one. See §Sequence.

---

## What changed from v1, and why

| # | v1 said | v2 says | Premortem finding |
|---|---|---|---|
| 1 | `uv sync --frozen` | **`uv sync --locked`** | F1 — `--frozen` exits 0 on a drifted pyproject and installs a version violating the declared floor (measured) |
| 2 | `uv run <tool>` | **`uv run --frozen <tool>`** | F1 — a bare `uv run` **rewrites `uv.lock` mid-job** (md5 changed, measured) |
| 3 | — | **never set `UV_FROZEN` globally** | measured: `UV_FROZEN=1` + `--locked` → `exit 2: the argument --locked cannot be used with UV_FROZEN`. The premortem's two hardening suggestions are mutually exclusive; only this combination works. |
| 4 | pin `pip-audit` job | **add `pip-audit` to `[dependency-groups] dev` first** | F2 — `pip-audit` is in no dependency group; `uv run pip-audit` → `Failed to spawn`, exit 2, swallowed by `\|\| true` ⇒ security gate silently deleted |
| 5 | `find_all(None, {K: True})` | **`find_all(name=None, attrs={K: True})`** | F6 — same overload, same runtime (measured on both bs4 versions), but bound by *name* not *position*; bs4 deleted a positional param in a minor release once already |
| 6 | fix `dependabot.yml` only | **fix `dependabot.yml:19` AND `ci.yml:64`** | F3 — the command the operator actually sees is the `::error::` annotation, not the comment |
| 7 | `uv lock --upgrade` | **`uv lock --upgrade-package <name>`** | F4 — `--upgrade` moved **24 packages** on the real lock, incl. `mypy 2.1→2.3`, `ruff 0.15→0.16`, `structlog 25→26` |
| 8 | one branch, one PR | **three PRs** | F14 — the ruleset allows only squash/rebase; a squashed revert of the CI change would revert the type fix too |
| 9 | merge #63 last | **merge #64 FIRST, #66 last** | F8 + CURRENT BUG 1 — #63/#60/#58 were closed by the unarchive; #64 rewrites the exact `ci.yml` lines this change rewrites |
| 10 | required checks out of scope | **in scope, as an explicit decision** | F5 — the ruleset requires only `Lint (ruff)` + `Import + module smoke test`; mypy/pytest gate nothing, so pinning buys reproducibility with no enforcement |

## Premises (declared, with evidence status)

- **P1 — SURVIVED refutation.** A fix exists that type-checks under both `beautifulsoup4`
  4.14.3 and 4.15.0 with identical runtime behaviour. Verified by the types lens across
  10 case classes × 3 parsers × 2 bs4 versions: zero divergences. Re-measured by the
  orchestrator for the keyword form specifically.
- **P3 — SURVIVED.** No application runtime behaviour changes. `{KEY: True}` means
  *presence*, not truthiness, on both versions (`<div style="">` matches).
- **P2 — REVISED.** v1 claimed "pinning makes CI reproducible, so a green run means
  something." Split into two claims, because the premortem showed the second does not
  follow from the first:
  - **P2a** pinning makes a run *reproducible* — true, with the corrected flags (§Change 3).
  - **P2b** a green run *gates anything* — **false today** and not fixed by pinning.
    Requires §Change 5. Stated separately so it is decided, not assumed.

---

## Change 1 — repo settings (no diff)

```bash
gh api repos/fbmoulin/kratos-clone/vulnerability-alerts -X PUT
```

**F9 correction:** this enables *alerts* only. `automated-security-fixes` is a **separate
endpoint** and stays off — measured: `{"enabled":false,"paused":false}`, and
`dependabot_security_updates: disabled`. While it is off, the `security` group at
`.github/dependabot.yml:35-37` (`applies-to: security-updates`) is inert.

**Decision required from the operator:** enable `automated-security-fixes` too, or accept
that advisories are visible-but-unactioned. Do not leave it implicit.

```bash
# only if the operator wants the security group to actually fire:
gh api repos/fbmoulin/kratos-clone/automated-security-fixes -X PUT
```

⚠️ **This change has no durable copy.** Archiving the repo revokes it silently — measured
this session in the other direction (`secret_scanning_push_protection` flipped
`disabled`→`enabled` on unarchive, with nobody enabling it). If the repo will be
re-archived, skip Change 1 entirely rather than leaving a setting that reads enabled in
the plan and disabled in reality.

---

## Change 2 — the 5 `find_all` sites (PR A, standalone)

Transform, applied identically at all 5 sites:

```diff
- soup.find_all(attrs={KEY: True})
+ soup.find_all(name=None, attrs={KEY: True})
```

Sites (verified on `main` @ `7587cd3`):

    downloader.py:307            {"style": True}
    downloader.py:1013           {"style": True}
    downloader.py:1048           {"data-background": True}
    scripts/validate.py:163      {attr: True}          # attr is a loop variable
    scripts/post_process.py:74   {attr: True}          # attr is a loop variable

**Why `name=None` by keyword, not positionally.** bs4 4.15's dict-attrs overload declares
`name: None` with no default, so a call omitting `name` matches no variant. Both the
positional and keyword forms satisfy it — measured identical on mypy --strict and at
runtime, on 4.14.3 and 4.15.0. The keyword form binds by parameter *name*; bs4 deleted
`_stacklevel` from position 6 in a minor release, so positional coupling is a demonstrated
risk, not a hypothetical one (F6).

**Required comment at the first site** (F6 hardening 2), so a future reader does not
"clean it up":

```python
# name=None is required by bs4 >=4.15: the dict-attrs overload declares
# `name: None` with no default. Do not drop it back to attrs=... only.
```

**Exhaustiveness is established, not assumed** (types lens, Dropped finding 13): every file
containing a bs4 query is inside mypy's `files` list (`pyproject.toml:76-86`), so the
5-error run is the complete classification. `tests/` contains zero bs4 *query* calls, so the
mypy `exclude` of `tests/` hides no runtime break.

### Change 2b — remove the `KeyError` trap (same PR, separate commit)

F13: the `{KEY: True}` filter is the *only* thing making the next line's subscript safe, and
these are exactly the lines the next editor will be looking at. `_as_str` already handles
`None` correctly; `Tag.__getitem__` raises rather than returning `None` (measured on both
bs4 versions), so the existing `None` arm is dead.

```diff
- style = _as_str(elem["style"])
+ style = _as_str(elem.get("style"))
```

at `downloader.py:308`, `downloader.py:1014`, and `elem.get("data-background")` at
`downloader.py:1049`. Zero behavioural cost: an element matched by the filter always has the
attribute.

**Separate commit so it can be reverted independently of Change 2.** If the operator judges
this out of scope, drop the commit — Change 2 stands alone.

**Acceptance for PR A:** mypy green under bs4 4.14.3 *and* 4.15.0; `pytest` unchanged from
the measured baseline. Re-measure the baseline on the branch rather than quoting v1's
"337 passed" (see §Sequence step 5 — #66 also bumps playwright).

---

## Change 3 — pin the CI jobs (PR B)

### 3a — prerequisites inside `pyproject.toml` (F2, F10)

```diff
 [dependency-groups]
 dev = [
     "bandit>=1.9.4",
     "mypy>=1.20.2",
+    "pip-audit>=2.9",
     "pytest>=9.0.3",
     "pytest-asyncio>=1.3.0",
     "ruff>=0.15.12",
     "types-requests>=2.32",
 ]
+
+[tool.uv]
+# CI installs with `uv sync --locked`, which must NOT try to build this project:
+# the modules are top-level (app.py, downloader.py) and the distribution name
+# `10-website-downloader` is not a valid module name. Adding a [build-system]
+# table would break all pinned jobs at the install step.
+package = false
```

then `uv lock` and commit the resulting `uv.lock` diff. **This PR owns that diff** — v1 did
not claim it, which is what made F2 possible.

### 3b — the two lines per job

For `lint`, `smoke`, `pytest`, `render-live`, `pip-audit`, `mypy`, `bandit`:

```diff
- run: pip install <bare package names>
+ run: uv sync --locked --group dev

- run: <tool> ...
+ run: uv run --frozen <tool> ...
```

**Both flags are load-bearing and were measured:**

| Command | Consistent tree | Drifted `pyproject` | Mutates `uv.lock`? |
|---|---|---|---|
| `uv sync --frozen` | exit 0 | **exit 0, installs the wrong version** | no |
| `uv sync --locked` | exit 0 | **exit 1, actionable message** | no |
| `uv run <tool>` | ok | ok | 🔴 **rewrites the lock mid-job** |
| `uv run --frozen <tool>` | ok | ok | no |
| `UV_FROZEN=1` + `--locked` | **exit 2** | **exit 2** | — |

⚠️ **Do not set `UV_FROZEN` at workflow level.** It is mutually exclusive with `--locked`
(`error: the argument --locked cannot be used with UV_FROZEN`). The premortem proposed both;
only this combination works.

Execution sites to rewrite (`ci.yml` line numbers on `main` @ `7587cd3` — **re-derive after
#64 merges**, since #64 shifts them):

    :33   ruff check ...                     :193  pytest -v tests/test_render_live.py
    :36   ruff format --check ...            :216  pip-audit ... || true
    :98   python -m kratos_clone --help      :242  mypy --config-file pyproject.toml
    :163  pytest -v tests/                   :265  bandit -r ...
    :188  python -m playwright install --with-deps chromium

`requirements-lock-sync` (`ci.yml:38-66`) is **not** pinned — it validates the lock rather
than consuming it. But it gets two fixes:

- `uv export --locked` instead of bare `uv export` (CURRENT BUG 3: `uv export` re-locks
  silently, so the guard currently compares against a *fresh resolution*, not the committed
  lock — measured, md5 of `uv.lock` changed during the guard's own run).
- a new `uv lock --check` step — the only measured command that detects pyproject↔lock drift
  (F1). Neither `uv sync --frozen` nor the existing guard catches it.

### 3c — pin `uv` itself (F11)

`uv` is currently installed unpinned at `ci.yml:58` and would be added unpinned to 7 more
jobs — the one unpinned thing in a change whose purpose is pinning. `uv.lock:1-2` declares
`version = 1` / `revision = 3`, a compatibility contract nothing on the reading side pins.

Use `astral-sh/setup-uv` pinned to a commit SHA with an explicit `version:` input, defined
once and referenced by all 8 jobs.

**Pin to `uv 0.10.12`** — measured, and it is the version that produced every `uv`
measurement in this spec and in the premortem. Pinning to anything else would mean the
evidence base was gathered on a version CI does not run. Bump it later as a deliberate,
separately-reviewed change.

### 3d — forward-compatibility canary (F7)

Pinning removes the only thing that ever exercised bs4 4.15. After PR B, a revert of
Change 2 — or a new `attrs={...}` copied from the surviving idiom at
`scripts/validate.py:244` — passes green.

Add one **non-blocking** job:

```yaml
  forward-compat:
    name: forward-compat canary (unpinned, informational)
    continue-on-error: true
    steps:
      - run: pip install mypy beautifulsoup4        # deliberately unpinned
      - run: mypy --config-file pyproject.toml
```

It surfaces incompatibility as a yellow annotation on the PR that introduces it, instead of
as a red build months later on an unrelated PR.

### 3e — cleanup while in the file

Drop `cache: pip` (`ci.yml:55,79,151,182,228`) — after 3b nothing installs via pip, so the
cache key is a silent no-op.

---

## Change 4 — the remediation command, in both places (PR B)

Two copies exist. v1 fixed the one nobody reads.

**`.github/dependabot.yml:16-19`** — correct the comment: `requirements.txt` ends up **ahead
of** `uv.lock`, not stale behind it (measured on the #63 branch: lock moved 4 packages,
requirements.txt moved 14).

**`.github/workflows/ci.yml:64`** — the `::error::` annotation GitHub renders on the Checks
tab, which is what the operator actually copies. Must carry the same corrected command.

Corrected command, **scoped** (F4 — the unscoped form moved 24 packages):

```
uv lock --upgrade-package <name> && \
  uv export --locked --format requirements-txt --no-dev --no-emit-project --no-hashes -o requirements.txt
```

**Preferred hardening (F3-2):** extract to `scripts/relock.sh` taking the package name as an
argument, and have both sites point at the path. One implementation, two pointers — the two
copies are otherwise unenforced and will drift again.

---

## Change 5 — required status checks (NEW, decision required)

Measured: the ruleset `Protect main` (id `15582219`) requires exactly `Lint (ruff)` and
`Import + module smoke test`, with `bypass_actors: RepositoryRole id=5, mode=always`.
`ci.yml:237` calls mypy a "HARD gate" in its own comment; the ruleset has never asked for it.

Without this change, P2b stays false: CI becomes reproducible and still gates nothing.

```
add to required_status_checks:  "mypy (...)", "pytest (...)"
set strict_required_status_checks_policy: true
```

⚠️ **Order matters.** Adding `mypy` to the required set **before** PR A merges would block
every open dependabot PR, since all of them inherit the 5 errors. Do this in §Sequence step 4,
after PR A is on `main`.

**This is the operator's call.** It is the only change here that constrains the operator's own
future workflow — though `bypass_actors` means the owner can always override.

---

## Sequence (order is load-bearing)

1. **Merge #64 first.** It touches only `.github/workflows/ci.yml` (+16/−16) and rewrites the
   exact `setup-python` blocks Change 3 rewrites — merging it later strands it on a conflict
   dependabot will not resolve (F8). Verified today: `MERGEABLE/UNSTABLE`, and it **passes both
   required checks** (`Lint (ruff)` ✓, `Import + module smoke test` ✓); mypy fails but does not
   gate. Mergeable now.
2. **PR A — Change 2 (+2b).** Branch from the new `main`. Independently valuable and measured
   safe on both bs4 versions. Merge with **rebase**, not squash, so 2 and 2b stay revertible
   separately.
3. **PR B — Changes 3 and 4.** Branch from `main` after PR A. Re-derive the `ci.yml` line
   numbers (#64 shifted them). The PR's own run is the first check of the pinned pipeline.
4. **Change 5** — after PR A is on `main`, so adding `mypy` to the required set does not block
   every open PR.
5. **#66 last, and re-measure before merging.** #66 is a **superset** of what #63 was: 16
   updates including `playwright 1.60→1.61` and `openai 2.41→2.50`, not just bs4 and pillow.
   v1's "337 passed" baseline was measured against playwright 1.60.0 — the version the
   `render-live` job drives Chromium with. Re-run the suite on the #66 branch after PR B, and
   use the scoped relock command from Change 4, not the unscoped one.
6. **Change 1** — any time, but decide `automated-security-fixes` with it, and skip it entirely
   if the repo is going to be re-archived.

## Out of scope (unchanged from v1, explicitly)

Deleting `requirements.txt` and moving `Dockerfile`/`build.sh` to `uv sync` (the durable fix
for the drift class); removing `|| true` from `pip-audit` — **note F12: after pinning, that job
reports the same 13 Pillow advisories forever into a log nobody reads while staying green.
Reconsider including it**; the SSRF / `file://` unauthenticated read; `--no-sandbox`; the
missing `USER` in `Dockerfile`; rate limiting on `/start-download`.

## Working copy

`~/Website-Downloader` (existing checkout, `origin` + `upstream` remotes), `git fetch`, branch
from `origin/main`. Do not touch or commit the untracked single-copy `AGENTS.md` there.

## Push classification

The diff touches `.github/workflows/` and `.github/dependabot.yml` ⇒ **tier RED** under the
operator's push policy: explicit authorization required at push time, feature branch
notwithstanding. Changes 1 and 5 are repo-setting changes, also requiring authorization.

## Documentation debt this uncovers (not part of the change)

- `docs/HANDOFF.md:142` claims four required checks including `pytest` and `pip-audit`. The
  ruleset requires two. A reader trusting that line believes pytest gates merges.
- The audit synthesis A8 ("no branch protection on `main`") is wrong in mechanism — protection
  comes from a ruleset, which the legacy `branches/main/protection` endpoint reports as 404.
- `personalize/patcher.py:153-154` states the parser behaviour backwards: measured on both bs4
  versions with `html.parser`, `tag.get("class")` returns the **list**, not a string. The code
  is correct; the comment is the documented justification for an `isinstance` branch a future
  reader might delete as dead.
