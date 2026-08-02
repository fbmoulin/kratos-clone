# kratos-clone CI Unblock — Implementation Plan

> ## ⚠️ EXECUTED 2026-08-02 — read this before following any step below
>
> This plan was carried out. It is kept as a record of the reasoning, **not as a runbook**.
> Five of its verification steps turned out to assert things that are not true, and following
> them as written would produce measurements that look valid and are not. Corrections, in the
> order you would hit them:
>
> | Where | The plan says | Measured on 2026-08-02 |
> |---|---|---|
> | Task 3 Step 2 | `uv run --frozen pip-audit --version` fails with *Failed to spawn*, proving `pip-audit` is undeclared | **Machine-dependent.** `uv run` falls back to `PATH`. On a workstation with a global `pip-audit` (conda, pipx) it prints a version and the proof silently inverts. Prove it with `ls .venv/bin/ \| grep -c pip-audit` (expect 0), or re-run under a CI-like `PATH`. |
> | Task 4 Step 3 | `uv lock --upgrade-package <bad-name>` exits non-zero | **Exits 0.** `--upgrade-package` is a resolution hint, not a lookup; uv never validates the name. `scripts/relock.sh` therefore ships its own `assert_in_lock` guard — that guard is the fix for this, and deleting it restores the silent no-op. |
> | Task 5 Step 1 and Task 6 Step 1 | probes mutate `pyproject.toml` with a bare Python `str.replace()` | **`str.replace()` does not fail when its target is absent.** It returns the text unchanged and the probe writes it back, so the drift never exists — and Task 6's probe then prints its own expected `GUARD PASSES — drift undetected` line without having run the experiment. Any such mutation must assert `after != before` and exit non-zero otherwise. |
> | Task 5 Step 1 | `<UV_VERSION>` unresolved; fall back to 0.10.12 if probes disagree | **Resolved to `0.12.1`.** All probes matched, plus a fourth (added here) confirming `UV_FROZEN` still conflicts with `--locked` on the candidate. |
> | Task 6 Step 3 | dependabot's uv ecosystem "also rewrites `requirements.txt`" | **Only for production-group bumps.** Development-group bumps do not touch it, because it is exported `--no-dev`. Measured on the open PRs: #66 (production) touches it, #65 (development) does not. |
>
> One further ordering hazard, found while running Task 6's probe: a bare `uv export` earlier in
> the *same* script silently re-locks and erases the drift, so a later `uv lock --check` reports
> 0 and looks like a refutation. Order matters inside a probe as much as inside the job.
>
> **For agentic workers (original note):** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to
> implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `main` type-check green and make CI reproducible and enforcing, so that PR #66
(Pillow 12.3.0, closing 13 advisories) can be merged with evidence rather than hope.

**Architecture:** Three sequenced PRs against `fbmoulin/kratos-clone`. PR A fixes five
`beautifulsoup4` call sites in a form that type-checks under both the locked (4.14.3) and
incoming (4.15.0) versions. PR B replaces seven jobs' unpinned `pip install` with
lockfile-pinned `uv`, using the exact flag pair measured to be safe. Repo-setting changes are
applied out-of-band. Everything is anchored to file *content*, not line numbers, because PR #64
shifts every line in `ci.yml`.

**Tech Stack:** Python 3.12, uv (lockfile), mypy, pytest, ruff, bandit, GitHub Actions,
BeautifulSoup4.

**Spec:** `SPEC-v2-unblock-ci-2026-08-02.md` (approved 2026-08-02).
**Pre-mortem:** `.premortems/PREMORTEM-2026-08-02T04-48-33Z.md` (verdict on v1: REWORK). Every
hardening item below traces to a finding there.

**Plan location note:** written to `~/claudedocs/kratos-clone-audit-2026-08-01/` rather than the
repo's `docs/superpowers/plans/` because nothing may be committed before Task 0. Task 1 Step 8
copies it into the repo.

---

## File structure

| File | Change | PR | Responsibility |
|---|---|---|---|
| `downloader.py` | modify 3 call sites + 3 subscripts | A | SPA capture engine (the deployed path) |
| `scripts/validate.py` | modify 1 call site | A | asset-reference validator |
| `scripts/post_process.py` | modify 1 call site | A | post-capture HTML rewriting CLI |
| `tests/test_bs4_attr_filter.py` | **create** | A | pins the attribute-presence contract at runtime, so the fix has a test and not only a type-check |
| `pyproject.toml` | add `pip-audit` to dev group; add `[tool.uv] package = false` | B | dependency + build declarations |
| `uv.lock` | regenerate | B | resolved dependency set (generated — never hand-edit) |
| `scripts/relock.sh` | **create** | B | single implementation of the relock command, referenced by both places that document it |
| `.github/workflows/ci.yml` | pin 7 jobs; fix the guard; add canary | B | CI definition |
| `.github/dependabot.yml` | correct comment + point at `scripts/relock.sh` | B | dependency automation config |

---

## Task 0: Prerequisites

**Files:** none (repo state only)

- [ ] **Step 1: Merge PR #64 first**

`#64` touches only `.github/workflows/ci.yml` (+16/−16), bumping `actions/checkout@v6→v7` and
`actions/setup-python@v6→v7`. Every one of its hunks has the `setup-python` block as context —
exactly where Task 5 inserts a new step. Merging it *after* PR B strands it on a conflict
dependabot will not resolve (pre-mortem F8).

Verify it is still mergeable, then merge:

```bash
gh pr view 64 -R fbmoulin/kratos-clone --json mergeable,mergeStateStatus,files \
  -q '"\(.mergeable)/\(.mergeStateStatus) files=\(.files|map(.path)|join(","))"'
# Expected: MERGEABLE/UNSTABLE files=.github/workflows/ci.yml
```

`UNSTABLE` means a non-required check is red — `mypy`, which fails on all PRs for the inherited
five errors. The ruleset requires only `Lint (ruff)` and `Import + module smoke test`, both of
which pass on #64. Confirm before merging:

```bash
gh pr checks 64 -R fbmoulin/kratos-clone | grep -E "Lint \(ruff\)|Import \+ module"
# Expected: both lines end in `pass`
```

**🔴 STOP — operator authorization required.** Merging #64 modifies `.github/workflows/`.
Under the operator's push policy this is tier RED. Ask before running:

```bash
gh pr merge 64 -R fbmoulin/kratos-clone --rebase
```

- [ ] **Step 2: Refresh the working copy**

```bash
cd ~/Website-Downloader
git fetch origin
git status --porcelain
# Expected: exactly one line — `?? AGENTS.md`
```

`AGENTS.md` is an untracked single-copy file. **Never `git add -A` in this repo.** Stage files
explicitly, always.

- [ ] **Step 3: Cut the PR A branch from the new main**

```bash
cd ~/Website-Downloader
git checkout -b fix/bs4-find_all-overloads origin/main
git merge-base --is-ancestor origin/main HEAD && echo "branch is current with origin/main"
# Expected: branch is current with origin/main
```

- [ ] **Step 4: Record the pre-change baseline**

Do not quote the spec's numbers — measure on this branch.

```bash
cd ~/Website-Downloader && uv sync --locked --group dev && uv run --frozen pytest -q 2>&1 | tail -2
# Record the exact "N passed, M skipped" line. It is the invariant for Task 1 Step 6.
```

---

## Task 1: Fix the five `find_all` overload sites (PR A)

**Files:**
- Test: `tests/test_bs4_attr_filter.py` (create)
- Modify: `downloader.py` (3 sites), `scripts/validate.py` (1), `scripts/post_process.py` (1)

**Why a test at all.** After PR B pins CI to the lock, nothing in the repo will ever exercise
bs4 4.15 again (pre-mortem F7), so a revert of this fix would pass green. A runtime test pins
the *behaviour* independently of which bs4 version is installed.

- [ ] **Step 1: Write the failing test**

Create `tests/test_bs4_attr_filter.py`:

```python
"""Pins the attribute-presence filter contract used by the capture and script paths.

`find_all(name=None, attrs={KEY: True})` selects every element carrying KEY, regardless of
value — including an empty value. bs4 >=4.15 requires `name` to be supplied for the
dict-attrs overload; these tests fail loudly if the call form is "cleaned up" back to
`attrs=` alone, or if bs4 changes presence semantics.
"""

import pytest
from bs4 import BeautifulSoup

HTML = (
    '<p style="a">one</p>'
    '<div style="">two</div>'
    '<span data-background="y">three</span>'
    '<img src="x.png">'
    '<b>no-attrs</b>'
)


def _soup() -> BeautifulSoup:
    return BeautifulSoup(HTML, "html.parser")


@pytest.mark.parametrize(
    ("key", "expected_texts"),
    [
        ("style", ["one", "two"]),
        ("data-background", ["three"]),
        ("src", [""]),
    ],
)
def test_attr_presence_filter_selects_elements_carrying_the_key(key, expected_texts):
    found = _soup().find_all(name=None, attrs={key: True})
    assert [el.get_text() for el in found] == expected_texts


def test_empty_attribute_value_still_counts_as_present():
    """`style=""` must match: the filter tests presence, not truthiness."""
    found = _soup().find_all(name=None, attrs={"style": True})
    assert any(el.get("style") == "" for el in found), "empty-valued attribute must match"


def test_element_without_the_attribute_is_excluded():
    found = _soup().find_all(name=None, attrs={"style": True})
    assert all(el.name != "b" for el in found)


def test_every_match_carries_the_attribute():
    """The invariant the three downloader.py call sites rely on before subscripting."""
    for key in ("style", "data-background", "src"):
        for el in _soup().find_all(name=None, attrs={key: True}):
            assert el.get(key) is not None, f"{el.name} matched on {key} but lacks it"
```

- [ ] **Step 2: Run the test to verify it passes on the locked bs4**

```bash
cd ~/Website-Downloader && uv run --frozen pytest tests/test_bs4_attr_filter.py -v
# Expected: 6 passed  (3 parametrized + 3 single)
```

This test passes *before* the source change — it documents bs4's contract, not our call sites.
The failing-first artifact for this task is the **mypy run in Step 4**, which is the actual
defect being fixed.

- [ ] **Step 3: Verify mypy currently FAILS under bs4 4.15**

```bash
cd ~/Website-Downloader && uv run --isolated --no-project \
  --with mypy --with "beautifulsoup4==4.15.0" --with openai --with pillow --with python-dotenv \
  --with playwright --with requests --with types-requests --with urllib3 --with flask \
  --with flask-limiter --with gunicorn --with psutil --with structlog \
  mypy --config-file pyproject.toml
# Expected: Found 5 errors in 3 files (checked 21 source files)
#   downloader.py:307, downloader.py:1013, downloader.py:1048,
#   scripts/validate.py:163, scripts/post_process.py:74
```

- [ ] **Step 4: Apply the fix to all five sites**

The transform adds `name=None` **by keyword**. Do not use the positional form
`find_all(None, {...})`: both type-check, but the keyword form binds by parameter *name*, and
bs4 deleted a positional parameter (`_stacklevel`) in a minor release (pre-mortem F6).

`downloader.py` — three sites. Find and replace each exact line:

```python
# downloader.py:307  (in _fix_scroll_blocking)
-        for elem in soup.find_all(attrs={"style": True}):
+        for elem in soup.find_all(name=None, attrs={"style": True}):
```

```python
# downloader.py:1013  (in process, inline-style pass)
-        for elem in soup.find_all(attrs={"style": True}):
+        for elem in soup.find_all(name=None, attrs={"style": True}):
```

```python
# downloader.py:1048  (in process, background-image pass)
-        for elem in soup.find_all(attrs={"data-background": True}):
+        for elem in soup.find_all(name=None, attrs={"data-background": True}):
```

`scripts/validate.py:163`:

```python
-        for tag in soup.find_all(attrs={attr: True}):
+        for tag in soup.find_all(name=None, attrs={attr: True}):
```

`scripts/post_process.py:74`:

```python
-        for tag in soup.find_all(attrs={attr: True}):
+        for tag in soup.find_all(name=None, attrs={attr: True}):
```

Then add this comment immediately **above** the first site (`downloader.py:307`), so a future
reader does not revert it (pre-mortem F6 hardening 2):

```python
        # `name=None` is required by beautifulsoup4 >=4.15: the dict-`attrs` overload
        # declares `name: None` with no default, so omitting it matches no overload.
        # Do not "clean up" back to `find_all(attrs=...)` — mypy will fail on bs4 >=4.15.
```

⚠️ Do **not** introduce a named variable for the filter dict. It type-checks only as an inline
literal: bs4 declares `_StrainableAttributes = Dict[str, _StrainableAttribute]`, an invariant
`Dict`, so `flt = {attr: True}` infers `dict[str, bool]` and is rejected on **both** bs4
versions (pre-mortem F15).

- [ ] **Step 5: Verify mypy passes under BOTH bs4 versions**

```bash
cd ~/Website-Downloader
for V in 4.14.3 4.15.0; do
  echo "--- bs4 $V ---"
  uv run --isolated --no-project \
    --with mypy --with "beautifulsoup4==$V" --with openai --with pillow --with python-dotenv \
    --with playwright --with requests --with types-requests --with urllib3 --with flask \
    --with flask-limiter --with gunicorn --with psutil --with structlog \
    mypy --config-file pyproject.toml
done
# Expected, both: Success: no issues found in 21 source files
```

Both versions must pass. If only 4.15.0 passes, the fix has coupled `main` to an unmerged PR.

- [ ] **Step 6: Verify the suite is unchanged**

```bash
cd ~/Website-Downloader && uv run --frozen pytest -q 2>&1 | tail -2
# Expected: the Task 0 Step 4 baseline, PLUS 6 (the new test file). Nothing else may change.
```

- [ ] **Step 7: Commit**

```bash
cd ~/Website-Downloader
git add tests/test_bs4_attr_filter.py downloader.py scripts/validate.py scripts/post_process.py
git commit -m "fix(types): supply name=None for bs4 >=4.15 dict-attrs overload

beautifulsoup4 4.15 declares \`name: None\` with no default on the overload that
accepts \`attrs\` as a dict, so \`find_all(attrs={...})\` matches no variant and
mypy fails with [call-overload] at 5 sites.

Passing \`name=None\` by keyword selects that overload. Verified green under both
4.14.3 (locked) and 4.15.0 (incoming via the production-dependencies PR), with
identical runtime results. Keyword rather than positional: bs4 removed a
positional parameter in a minor release, so binding by name is the safer coupling.

Adds tests/test_bs4_attr_filter.py to pin the attribute-presence contract at
runtime, independent of the installed bs4 version."
```

- [ ] **Step 8: Copy the spec, pre-mortem and this plan into the repo**

The repo already uses `docs/superpowers/specs/` and `docs/superpowers/plans/`.

```bash
cd ~/Website-Downloader
mkdir -p docs/superpowers/plans docs/superpowers/specs
D=~/claudedocs/kratos-clone-audit-2026-08-01
cp "$D/SPEC-v2-unblock-ci-2026-08-02.md" docs/superpowers/specs/2026-08-02-unblock-ci-design.md
cp "$D/PLAN-unblock-ci-2026-08-02.md"    docs/superpowers/plans/2026-08-02-unblock-ci.md
git add docs/superpowers/specs/2026-08-02-unblock-ci-design.md docs/superpowers/plans/2026-08-02-unblock-ci.md
git commit -m "docs: spec and plan for the CI unblock"
```

⚠️ **PII sweep before this commit.** The repo is PUBLIC. Both documents reference
`~/Website-Downloader` and `/home/fbmoulin/...`. The repo already publishes such paths in five
doc locations, so this introduces no new class — but confirm no other identifier crept in:

```bash
cd ~/Website-Downloader && gitleaks protect --staged --no-banner --redact
# Expected: no leaks found
```

---

## Task 2: Remove the `KeyError` trap (PR A, separate commit)

**Files:** Modify `downloader.py:308`, `downloader.py:1014`, `downloader.py:1049`

**Why.** The `{KEY: True}` filter is the only thing making the next line's subscript safe, and
Task 1 just rewrote those exact lines — so they are what the next editor will be looking at.
Widening the filter (a lambda predicate, or matching by tag name) makes the subscript raise
`KeyError` on real user downloads, with mypy staying green: `Tag.__getitem__` raises rather than
returning `None`, so `None` is not in the revealed type (pre-mortem F13).

`_as_str` already handles `None` correctly, so the existing `None` arm is currently dead code.

**This is a separate commit so the operator can drop it without touching Task 1.**

- [ ] **Step 1: Write the failing test**

Append to `tests/test_bs4_attr_filter.py`:

```python
def test_get_and_subscript_agree_for_matched_elements():
    """`.get(key)` must return exactly what `[key]` returns when the element matched.

    This is what makes the Task 2 substitution behaviour-preserving.
    """
    for key in ("style", "data-background", "src"):
        for el in _soup().find_all(name=None, attrs={key: True}):
            assert el.get(key) == el[key]


def test_subscript_raises_but_get_returns_none_when_absent():
    """Documents why `.get()` is the safer form if the filter is ever widened."""
    tag = _soup().find("b")
    assert tag is not None
    assert tag.get("style") is None
    with pytest.raises(KeyError):
        _ = tag["style"]
```

- [ ] **Step 2: Run it — it must pass before the change**

```bash
cd ~/Website-Downloader && uv run --frozen pytest tests/test_bs4_attr_filter.py -v
# Expected: 8 passed
```

These two tests assert bs4's contract, which is what licenses the substitution. They pass before
and after; their job is to fail if a future bs4 changes `.get`/`[]` equivalence.

- [ ] **Step 3: Apply the substitution**

```python
# downloader.py:308  (inside the loop opened at :307)
-            style = _as_str(elem["style"])
+            style = _as_str(elem.get("style"))
```

```python
# downloader.py:1014  (inside the loop opened at :1013)
-            style = _as_str(elem["style"])
+            style = _as_str(elem.get("style"))
```

```python
# downloader.py:1049  (inside the loop opened at :1048)
-            bg = _as_str(elem["data-background"])
+            bg = _as_str(elem.get("data-background"))
```

- [ ] **Step 4: Verify mypy and the suite**

```bash
cd ~/Website-Downloader
uv run --frozen mypy --config-file pyproject.toml
# Expected: Success: no issues found in 21 source files
uv run --frozen pytest -q 2>&1 | tail -2
# Expected: Task 1 Step 6 count, +2
```

- [ ] **Step 5: Commit**

```bash
cd ~/Website-Downloader
git add downloader.py tests/test_bs4_attr_filter.py
git commit -m "refactor(downloader): use .get() for filter-guaranteed attributes

The three sites subscript an attribute whose presence is guaranteed only by the
find_all filter on the line above. Tag.__getitem__ raises rather than returning
None, so mypy cannot see the coupling, and widening the filter later would raise
KeyError on the live download path.

_as_str already handles None, so the change is behaviour-preserving today and
removes the trap. No functional change."
```

- [ ] **Step 6: Open PR A**

```bash
cd ~/Website-Downloader
git push -u origin fix/bs4-find_all-overloads
```

**🔴 STOP — operator authorization required before pushing.** The repo is PUBLIC (tier ORANGE:
push permitted after a PII sweep) and this branch does **not** touch CI or workflows, so it is
not tier RED. Run the sweep, then ask:

```bash
cd ~/Website-Downloader && gitleaks detect --no-banner --redact --log-opts="origin/main..HEAD"
# Expected: no leaks found
```

```bash
gh pr create -R fbmoulin/kratos-clone --base main --head fix/bs4-find_all-overloads \
  --title "fix(types): supply name=None for bs4 >=4.15 dict-attrs overload" \
  --body "Fixes the 5 [call-overload] errors that have made mypy red on every PR since
2026-06-29. Verified green under bs4 4.14.3 (locked) and 4.15.0 (incoming), with identical
runtime results.

Merge with **rebase**, not squash: the two commits are independently revertible by design."
```

⚠️ **Merge with `--rebase`.** The ruleset allows `["squash","rebase"]`; a squash would collapse
Tasks 1 and 2 into one unit, so reverting the `.get()` change would also revert the type fix
(pre-mortem F14).

---

## Task 3: Declare `pip-audit` and freeze the packaging decision (PR B)

**Files:** Modify `pyproject.toml`; regenerate `uv.lock`

**Why this comes first in PR B.** Task 5 replaces the `pip-audit` job's `pip install pip-audit`
with `uv sync`. `pip-audit` is in no dependency group today, so without this task `uv run
pip-audit` fails to spawn, exits 2, and `|| true` swallows it — a permanently green job auditing
nothing (pre-mortem F2). This is the single most dangerous item in the whole change.

- [ ] **Step 1: Cut PR B's branch from main (after PR A merges)**

```bash
cd ~/Website-Downloader
git fetch origin
git checkout -b ci/pin-jobs-to-lockfile origin/main
git log --oneline -1
# Expected: the merge of PR A
```

- [ ] **Step 2: Prove the failure this task prevents**

```bash
cd ~/Website-Downloader && uv run --frozen pip-audit --version
# Expected: error: Failed to spawn: `pip-audit` / No such file or directory
```

If this *succeeds*, `pip-audit` has been added to the lock already — re-check the dev group
before proceeding.

- [ ] **Step 3: Edit `pyproject.toml`**

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
```

And append, after the `[dependency-groups]` block:

```toml
[tool.uv]
# CI installs with `uv sync --locked`, which must NOT attempt to build this project.
# The modules are top-level (app.py, downloader.py) and the distribution name
# `10-website-downloader` is not a valid module name, so a build backend cannot infer
# what to ship. Today uv infers non-package status from the ABSENT [build-system]
# table; stating it explicitly means adding [build-system] later cannot silently break
# all seven pinned CI jobs at their install step.
package = false
```

- [ ] **Step 4: Regenerate the lock and verify the guard passes**

```bash
cd ~/Website-Downloader
uv lock
uv lock --check                      # Expected: exit 0, no "needs to be updated"
uv sync --locked --group dev
uv run --frozen pip-audit --version  # Expected: a version string, not "Failed to spawn"
```

⚠️ Use plain `uv lock`, **never** `uv lock --upgrade` here. `--upgrade` re-resolves all 62
packages — measured at 24 version changes including `mypy 2.1→2.3` and `ruff 0.15→0.16`
(pre-mortem F4). Confirm the diff is small:

```bash
git diff --stat uv.lock
# Expected: additions for pip-audit and its transitives ONLY. If runtime packages
# (pillow, playwright, openai, beautifulsoup4) changed version, STOP — you ran --upgrade.
```

- [ ] **Step 5: Verify `requirements.txt` did not move**

`requirements.txt` is exported with `--no-dev`, so a dev-group addition must not touch it.

```bash
cd ~/Website-Downloader
uv export --locked --format requirements-txt --no-dev --no-emit-project --no-hashes -o /tmp/req.check.txt
diff <(grep -v '^#' /tmp/req.check.txt) <(grep -v '^#' requirements.txt) && echo "requirements.txt unchanged — correct"
# Expected: requirements.txt unchanged — correct
```

- [ ] **Step 6: Commit**

```bash
cd ~/Website-Downloader
git add pyproject.toml uv.lock
git commit -m "build: declare pip-audit in dev group; pin package=false

pip-audit is invoked by CI but declared nowhere, so it exists on the runner only
via an ad-hoc \`pip install\`. The next commit replaces that with \`uv sync\`,
which would prune it — and the job's trailing \`|| true\` would hide the resulting
spawn failure, leaving a permanently green CVE scan that audits nothing.

[tool.uv] package = false makes the non-package status explicit rather than
inferred from an absent [build-system] table, so adding one later cannot break
every pinned job at once.

requirements.txt is unaffected (exported --no-dev)."
```

---

## Task 4: Extract the relock command to one place (PR B)

**Files:** Create `scripts/relock.sh`

**Why.** The remediation command exists twice: in `.github/dependabot.yml` (a comment only
dependabot parses) and in `ci.yml`'s `::error::` annotation (what GitHub renders on the Checks
tab — the copy the operator actually reads and pastes). v1 fixed only the first. Nothing asserts
the two match, so they will drift again (pre-mortem F3).

- [ ] **Step 1: Create the script**

```bash
#!/usr/bin/env bash
# Regenerate requirements.txt after a dependency change.
#
# Why this exists: requirements.txt is generated from uv.lock and is what
# Dockerfile installs, so the two must agree. Dependabot's uv ecosystem updates
# pyproject.toml and uv.lock; the export must then be refreshed.
#
# Usage:
#   scripts/relock.sh                 # reconcile the lock with pyproject.toml
#   scripts/relock.sh pillow openai   # additionally advance only the named packages
#
# NEVER run `uv lock --upgrade` for this: it re-resolves every package in the lock
# (measured: 24 version changes on this repo, including the mypy and ruff that gate
# CI), turning a one-package security bump into an unreviewed toolchain swap.
set -euo pipefail

cd "$(dirname "$0")/.."

if [ "$#" -gt 0 ]; then
  for pkg in "$@"; do
    echo "==> uv lock --upgrade-package $pkg"
    uv lock --upgrade-package "$pkg"
  done
else
  echo "==> uv lock"
  uv lock
fi

echo "==> uv export --locked"
uv export --locked --format requirements-txt --no-dev --no-emit-project --no-hashes \
  -o requirements.txt

echo "==> git diff --stat"
git --no-pager diff --stat uv.lock requirements.txt
echo
echo "Review the diff above. If it is larger than the PR it belongs to, you ran too wide a"
echo "scope — reset and pass explicit package names."
```

- [ ] **Step 2: Make it executable and verify it is a no-op on a clean tree**

```bash
cd ~/Website-Downloader
chmod +x scripts/relock.sh
./scripts/relock.sh
git diff --stat uv.lock requirements.txt
# Expected: no output (no changes) — the tree is already consistent after Task 3.
```

- [ ] **Step 3: Verify it fails loudly on a bad package name**

```bash
cd ~/Website-Downloader && ./scripts/relock.sh not-a-real-package-xyz; echo "exit=$?"
# Expected: non-zero exit, uv reports the package is not in the lock.
# (`set -euo pipefail` must propagate the failure — if exit=0, the script is broken.)
git checkout uv.lock requirements.txt 2>/dev/null || true
```

- [ ] **Step 4: Commit**

```bash
cd ~/Website-Downloader
git add scripts/relock.sh
git commit -m "chore: add scripts/relock.sh as the single relock implementation

The regeneration command is currently documented in two places that nothing keeps
in sync — a dependabot.yml comment and the ci.yml error annotation — and the two
already disagree. Both now point at this script.

Defaults to plain \`uv lock\`; \`--upgrade-package\` only for explicitly named
packages. Bare \`uv lock --upgrade\` is deliberately unavailable."
```

---

## Task 5: Pin the seven jobs to the lockfile (PR B)

**Files:** Modify `.github/workflows/ci.yml`

**The measured flag contract.** These are not stylistic choices; each was verified:

| Command | Consistent tree | Drifted `pyproject.toml` | Mutates `uv.lock`? |
|---|---|---|---|
| `uv sync --frozen` | exit 0 | **exit 0 — installs the wrong version** | no |
| `uv sync --locked` | exit 0 | **exit 1 — actionable message** | no |
| `uv run <tool>` | ok | ok | 🔴 **rewrites the lock mid-job** |
| `uv run --frozen <tool>` | ok | ok | no |
| `UV_FROZEN=1` with `--locked` | **exit 2** | **exit 2** | — |

⚠️ **Never set `UV_FROZEN` at workflow level.** It is mutually exclusive with `--locked`
(`error: the argument --locked cannot be used with UV_FROZEN`). Use `--locked` on sync lines and
`--frozen` on run lines.

- [ ] **Step 1: Decide the `uv` version to pin, by measuring**

Everything in the spec and pre-mortem was measured on **uv 0.10.12** (released 2026-03-19). The
current release is **0.12.1** (2026-07-31) — two minors ahead, on which **none** of the table
above has been verified.

Re-run the three load-bearing probes on the candidate version before pinning to it:

```bash
cd /tmp && rm -rf uvprobe && git clone -q https://github.com/fbmoulin/kratos-clone uvprobe && cd uvprobe
UVX="uvx uv@0.12.1"        # substitute the version under test

# probe 1: --locked must FAIL on a drifted pyproject
python3 -c "import pathlib;p=pathlib.Path('pyproject.toml');p.write_text(p.read_text().replace('\"pillow>=11\"','\"pillow>=12.3.0\"'))"
$UVX sync --locked --group dev; echo "probe1 exit=$?   # expected: 1"
git checkout pyproject.toml

# probe 2: a bare `uv run` must be shown to rewrite the lock (justifying --frozen)
$UVX sync --locked --group dev >/dev/null 2>&1
python3 -c "import pathlib;p=pathlib.Path('pyproject.toml');p.write_text(p.read_text().replace('\"pillow>=11\"','\"pillow>=12.3.0\"'))"
M0=$(md5sum uv.lock|cut -d' ' -f1); $UVX run python -c pass >/dev/null 2>&1
M1=$(md5sum uv.lock|cut -d' ' -f1); [ "$M0" = "$M1" ] && echo "probe2: lock intact" || echo "probe2: lock REWRITTEN (expected)"
git checkout pyproject.toml uv.lock

# probe 3: --frozen on the run line must leave the lock intact
$UVX sync --locked --group dev >/dev/null 2>&1
python3 -c "import pathlib;p=pathlib.Path('pyproject.toml');p.write_text(p.read_text().replace('\"pillow>=11\"','\"pillow>=12.3.0\"'))"
M0=$(md5sum uv.lock|cut -d' ' -f1); $UVX run --frozen python -c pass >/dev/null 2>&1
M1=$(md5sum uv.lock|cut -d' ' -f1); [ "$M0" = "$M1" ] && echo "probe3: lock intact (expected)" || echo "probe3: REGRESSION"
git checkout pyproject.toml uv.lock
```

**If all three behave as annotated, pin the candidate version.** If any differs, pin `0.10.12`
— the version the evidence base was gathered on — and record why in the commit message.
Use the chosen version as `<UV_VERSION>` below.

- [ ] **Step 2: Add the shared uv setup step to each of the seven jobs**

For `lint`, `smoke`, `pytest`, `render-live`, `pip-audit`, `mypy`, `bandit`, replace the whole
`Set up Python` + install block. The `actions/setup-python` step is **removed**: `setup-uv`
provisions the interpreter from `.python-version` (`3.12`), so keeping both would allow them to
disagree.

Insert immediately after the `- uses: actions/checkout@...` line in each job:

```yaml
      - name: Set up uv
        uses: astral-sh/setup-uv@c771a70e6277c0a99b617c7a806ffedaca235ff9  # v9.0.0
        with:
          version: "<UV_VERSION>"
          enable-cache: true

      - name: Install locked dependencies
        run: uv sync --locked --group dev
```

The action is pinned to a commit SHA, not a tag, so a compromised or re-pointed tag cannot
change what executes with write access to the workspace on a public repo (pre-mortem F11).

Also delete the now-dead `cache: pip` lines — after this change nothing installs via pip, so the
cache key is a silent no-op (pre-mortem F8 hardening 2). They appear in `requirements-lock-sync`,
`smoke`, `pytest`, `render-live` and `mypy`.

- [ ] **Step 3: Prefix every execution line with `uv run --frozen`**

Replace each `run:` command exactly:

```yaml
# job lint
- run: ruff check kratos_clone/ scripts/ --output-format=github
+ run: uv run --frozen ruff check kratos_clone/ scripts/ --output-format=github
- run: ruff format --check kratos_clone/ scripts/
+ run: uv run --frozen ruff format --check kratos_clone/ scripts/

# job smoke — the four `python -c "..."` blocks and the CLI check
- run: python -c "
+ run: uv run --frozen python -c "
- run: python -m kratos_clone --help
+ run: uv run --frozen python -m kratos_clone --help

# job pytest
- run: pytest -v tests/
+ run: uv run --frozen pytest -v tests/

# job render-live
-   python -m playwright install --with-deps chromium
+   uv run --frozen playwright install --with-deps chromium
- run: pytest -v tests/test_render_live.py
+ run: uv run --frozen pytest -v tests/test_render_live.py

# job pip-audit
- run: pip-audit --vulnerability-service osv --desc on || true
+ run: uv run --frozen pip-audit --vulnerability-service osv --desc on || true

# job mypy
- run: mypy --config-file pyproject.toml
+ run: uv run --frozen mypy --config-file pyproject.toml

# job bandit
- run: bandit -r personalize/ kratos_clone/ scripts/ app.py --severity-level medium
+ run: uv run --frozen bandit -r personalize/ kratos_clone/ scripts/ app.py --severity-level medium
```

There are **four** `python -c` blocks in `smoke` (`Verify kratos_clone imports`, `Smoke test
scripts/ imports`, `Verify post.py round-trip`, `Verify Flask app imports without side effects`)
plus the `python -m kratos_clone --help` step. All five need the prefix.

⚠️ `render-live` installs browsers **outside** the venv (`~/.cache/ms-playwright`;
`PLAYWRIGHT_BROWSERS_PATH` is unset — measured), so `uv sync` never prunes them. What matters is
that the `playwright` package driving them comes from the same locked resolution as the test —
which `--frozen` on both lines guarantees.

- [ ] **Step 4: Verify every job's commands locally**

```bash
cd ~/Website-Downloader && uv sync --locked --group dev
uv run --frozen ruff check kratos_clone/ scripts/                 # All checks passed!
uv run --frozen ruff format --check kratos_clone/ scripts/        # N files already formatted
uv run --frozen pytest -q tests/ 2>&1 | tail -1                   # Task 2 Step 4 count
uv run --frozen mypy --config-file pyproject.toml                 # Success: no issues found
uv run --frozen bandit -r personalize/ kratos_clone/ scripts/ app.py --severity-level medium; echo "bandit exit=$?"
uv run --frozen python -m kratos_clone --help | head -1           # usage: kratos_clone
uv run --frozen pip-audit --vulnerability-service osv --desc on | tail -3
```

`bandit exit=0` is required. Its summary reports `High: 10` under **Confidence**, not Severity —
the Severity row reads `Low: 10, Medium: 0, High: 0`. Read the correct column.

- [ ] **Step 5: Validate the workflow file parses**

```bash
cd ~/Website-Downloader
uv run --frozen python -c "
import yaml, pathlib
d = yaml.safe_load(pathlib.Path('.github/workflows/ci.yml').read_text())
jobs = d['jobs']
print('jobs:', len(jobs))
for name, job in jobs.items():
    for step in job['steps']:
        run = step.get('run', '')
        assert 'pip install' not in run or name == 'requirements-lock-sync', f'{name}: stray pip install'
print('no stray pip install outside requirements-lock-sync')
"
# Expected: jobs: 9   (8 original + forward-compat from Task 7)
#           no stray pip install outside requirements-lock-sync
```

Run this **after** Task 7 adds the canary; before that, expect `jobs: 8`.

- [ ] **Step 6: Commit**

```bash
cd ~/Website-Downloader
git add .github/workflows/ci.yml
git commit -m "ci: pin seven jobs to uv.lock

Each job installed unpinned latest from PyPI, so a green run described whatever
PyPI served that morning. That is how beautifulsoup4 4.15.0 made main red with no
commit touching the code.

uv sync --locked (not --frozen): --frozen exits 0 on a pyproject/lock mismatch and
installs a version violating the declared constraint. uv run --frozen on every
execution line: a bare uv run re-resolves and rewrites uv.lock mid-job, swapping
package versions between the install step and the test step.

UV_FROZEN is deliberately NOT set at workflow level: it is mutually exclusive with
--locked (exit 2).

setup-uv is pinned to a commit SHA; actions/setup-python is dropped because setup-uv
provisions the interpreter from .python-version. Dead \`cache: pip\` keys removed."
```

---

## Task 6: Fix the drift guard and correct both copies of the command (PR B)

**Files:** Modify `.github/workflows/ci.yml` (`requirements-lock-sync` job),
`.github/dependabot.yml`

**Why.** `uv export` **re-locks silently** when `pyproject.toml` and `uv.lock` disagree, then
exports the fresh resolution — measured: `md5(uv.lock)` changed during the guard's own run. So
the job asserts "requirements.txt matches a fresh network resolution", not "matches the committed
lock" as its own comment claims. Separately, nothing in CI detects a pyproject↔lock drift at all:
neither `uv sync --frozen` nor this guard catches it; only `uv lock --check` does.

- [ ] **Step 1: Reproduce the guard's blind spot**

```bash
cd /tmp && rm -rf guardprobe && git clone -q https://github.com/fbmoulin/kratos-clone guardprobe && cd guardprobe
python3 -c "import pathlib;p=pathlib.Path('pyproject.toml');p.write_text(p.read_text().replace('\"pillow>=11\"','\"pillow>=12.3.0\"'))"
uv export --format requirements-txt --no-dev --no-emit-project --no-hashes -o /tmp/exp.txt
diff -q <(grep -v '^#' /tmp/exp.txt) <(grep -v '^#' requirements.txt) && echo "GUARD PASSES — drift undetected"
uv lock --check; echo "uv lock --check exit=$?   # expected: 1"
```

Expected: the guard passes while `uv lock --check` exits 1. That gap is what Step 2 closes.

- [ ] **Step 2: Rewrite the `requirements-lock-sync` job**

Replace the `Install uv` and `Assert requirements.txt matches uv.lock` steps with:

```yaml
      - name: Set up uv
        uses: astral-sh/setup-uv@c771a70e6277c0a99b617c7a806ffedaca235ff9  # v9.0.0
        with:
          version: "<UV_VERSION>"
          enable-cache: true

      - name: Assert uv.lock agrees with pyproject.toml
        # `uv sync --frozen` does NOT check this (it exits 0 and installs the stale
        # pin), and the export check below cannot see it either, because it exports
        # from the lock. `uv lock --check` is the only command that detects it.
        run: uv lock --check

      - name: Assert requirements.txt matches uv.lock
        # --locked is required: a bare `uv export` silently re-locks on a mismatch and
        # then exports the FRESH resolution, so the diff below would compare against
        # something that is not the committed lock.
        run: |
          uv export --locked --format requirements-txt --no-dev --no-emit-project --no-hashes -o /tmp/requirements.expected.txt
          if ! diff -u <(grep -v '^#' /tmp/requirements.expected.txt) <(grep -v '^#' requirements.txt); then
            echo "::error::requirements.txt is out of sync with uv.lock. Regenerate with: scripts/relock.sh (see the script header before passing package names)"
            exit 1
          fi
          echo "requirements.txt is in sync with uv.lock"
```

The `::error::` string is the copy the operator actually sees and pastes. It now names the
script rather than embedding a command that can drift.

Also update the job's leading comment block: replace the sentence beginning *"This re-exports
from the lock and diffs…"* with:

```yaml
    # the lock and diffs (with --locked, so a mismatch fails instead of silently
    # re-locking). A separate `uv lock --check` step catches the pyproject↔lock
    # drift that neither this diff nor `uv sync` can see.
```

- [ ] **Step 3: Correct `.github/dependabot.yml`**

Replace the `NOTE:` comment block (the four lines beginning *"dependabot's uv ecosystem does
NOT regenerate requirements.txt"*) with:

```yaml
    # NOTE: dependabot's uv ecosystem updates pyproject.toml AND uv.lock, and also
    # rewrites requirements.txt — but with a different resolution scope, so
    # requirements.txt ends up AHEAD of uv.lock (measured on PR #63: lock moved 4
    # packages, requirements.txt moved 14). The CI "requirements.txt ⇄ uv.lock sync"
    # guard flags this. Refresh before merging with:
    #   scripts/relock.sh <package> [<package> ...]
    # Do NOT run `uv export` alone: it regenerates from the lock and therefore
    # DOWNGRADES the transitive packages dependabot advanced (measured: 10 packages,
    # including certifi — the CA trust store).
```

- [ ] **Step 4: Verify the two copies now agree**

```bash
cd ~/Website-Downloader
grep -c "scripts/relock.sh" .github/workflows/ci.yml .github/dependabot.yml
# Expected: ci.yml:1  dependabot.yml:1
grep -rn "uv export --format requirements-txt" .github/ || echo "no un-scoped export command remains in .github/"
# Expected: no un-scoped export command remains in .github/
```

- [ ] **Step 5: Commit**

```bash
cd ~/Website-Downloader
git add .github/workflows/ci.yml .github/dependabot.yml
git commit -m "ci: make the drift guard check what it claims to check

Two defects, both measured:

1. \`uv export\` re-locks silently on a pyproject/lock mismatch and exports the
   fresh resolution, so the guard compared requirements.txt against a fresh network
   resolution rather than the committed lock. Fixed with --locked.
2. Nothing in CI detected pyproject-vs-lock drift at all. Added \`uv lock --check\`,
   the only command that does.

The remediation command lived in two places that disagreed; the copy operators
actually read (the ::error:: annotation) still prescribed the export-only form that
downgrades transitives. Both now point at scripts/relock.sh."
```

---

## Task 7: Add the forward-compatibility canary (PR B)

**Files:** Modify `.github/workflows/ci.yml`

**Why.** Pinning removes the only thing that ever exercised bs4 4.15. After Task 5, a revert of
Task 1 — or a new `find_all(attrs={...})` copied from the surviving idiom at
`scripts/validate.py:244` — passes green, and the failure resurfaces months later on an unrelated
PR (pre-mortem F7).

- [ ] **Step 1: Add the job**

Append to `.github/workflows/ci.yml`:

```yaml
  forward-compat:
    # Informational only. Pinning every other job to uv.lock means nothing in CI
    # exercises newer dependency releases, so a forward-incompatibility (e.g. the
    # beautifulsoup4 4.15 find_all overload change) would stay invisible until a
    # lock bump made it red on an unrelated PR. This job deliberately resolves
    # latest-from-PyPI so that incompatibility appears as a yellow annotation on the
    # PR that introduces it. It must never gate: continue-on-error is load-bearing.
    name: forward-compat canary (unpinned — informational)
    runs-on: ubuntu-latest
    continue-on-error: true
    steps:
      - uses: actions/checkout@v7

      - name: Set up uv
        uses: astral-sh/setup-uv@c771a70e6277c0a99b617c7a806ffedaca235ff9  # v9.0.0
        with:
          version: "<UV_VERSION>"

      - name: Type-check against latest dependencies
        run: |
          uv run --isolated --no-project \
            --with mypy --with beautifulsoup4 --with openai --with pillow \
            --with python-dotenv --with playwright --with requests --with types-requests \
            --with urllib3 --with flask --with flask-limiter --with gunicorn \
            --with psutil --with structlog \
            mypy --config-file pyproject.toml
```

Use `actions/checkout@v7` to match what PR #64 left in the file. If #64 has not merged, use
`@v6` and let #64's rebase update it.

- [ ] **Step 2: Verify it passes locally with latest deps**

```bash
cd ~/Website-Downloader
uv run --isolated --no-project --with mypy --with beautifulsoup4 --with openai --with pillow \
  --with python-dotenv --with playwright --with requests --with types-requests --with urllib3 \
  --with flask --with flask-limiter --with gunicorn --with psutil --with structlog \
  mypy --config-file pyproject.toml
# Expected: Success: no issues found in 21 source files
```

This is the same command the canary runs. It must pass now, because Task 1 already fixed the
only known forward-incompatibility. If it fails, a **new** one exists — investigate before
merging PR B; do not merge a canary that is born red.

- [ ] **Step 3: Re-run the workflow parse check from Task 5 Step 5**

```bash
cd ~/Website-Downloader && uv run --frozen python -c "
import yaml, pathlib
d = yaml.safe_load(pathlib.Path('.github/workflows/ci.yml').read_text())
print('jobs:', len(d['jobs']))
assert d['jobs']['forward-compat']['continue-on-error'] is True, 'canary must not gate'
print('canary is non-blocking')
"
# Expected: jobs: 9 / canary is non-blocking
```

- [ ] **Step 4: Commit and open PR B**

```bash
cd ~/Website-Downloader
git add .github/workflows/ci.yml
git commit -m "ci: add non-blocking forward-compat canary

Pinning to uv.lock removes the only thing that exercised newer dependency releases.
This job resolves latest-from-PyPI and type-checks, so a forward-incompatibility
surfaces as a yellow annotation on the PR that introduces it rather than as a red
build months later on an unrelated PR. continue-on-error is load-bearing."
git push -u origin ci/pin-jobs-to-lockfile
```

**🔴 STOP — operator authorization required before pushing.** This diff touches
`.github/workflows/` and `.github/dependabot.yml`: tier RED under the operator's push policy,
feature branch notwithstanding. Ask explicitly.

```bash
gh pr create -R fbmoulin/kratos-clone --base main --head ci/pin-jobs-to-lockfile \
  --title "ci: pin jobs to uv.lock and fix the drift guard" \
  --body "Makes CI reproducible. See docs/superpowers/specs/2026-08-02-unblock-ci-design.md.

Merge with **rebase**, not squash — the five commits are independently revertible.

This PR's own run is the first execution of the pinned pipeline. Read every job, not just
the two required checks."
```

- [ ] **Step 5: Read the PR's CI run job by job**

```bash
gh pr checks $(gh pr view --json number -q .number -R fbmoulin/kratos-clone \
  --head ci/pin-jobs-to-lockfile) -R fbmoulin/kratos-clone
```

All nine must be `pass` except `forward-compat`, which may be `fail` without blocking. A job
finishing in **under ~15 seconds with zero steps** is a start-up failure (billing/runner), not a
test failure — check step count before diagnosing:

```bash
gh api repos/fbmoulin/kratos-clone/actions/runs/<RUN_ID>/jobs \
  -q '.jobs[] | "\(.name) | \(.conclusion) | steps=\(.steps|length)"'
```

---

## Task 8: Repo settings (out-of-band, operator decisions)

**Files:** none

- [ ] **Step 1: Enable vulnerability alerts**

```bash
gh api repos/fbmoulin/kratos-clone/vulnerability-alerts -X PUT
gh api repos/fbmoulin/kratos-clone/vulnerability-alerts   # Expected: HTTP 204, no body
```

- [ ] **Step 2: DECISION — automated security fixes**

`vulnerability-alerts` enables *alerts only*. `automated-security-fixes` is a separate endpoint,
measured `{"enabled":false}`. While it is off, the `security` group in `.github/dependabot.yml`
(`applies-to: security-updates`) never fires — advisories are visible but unactioned.

**Ask the operator.** If yes:

```bash
gh api repos/fbmoulin/kratos-clone/automated-security-fixes -X PUT
gh api repos/fbmoulin/kratos-clone -q '.security_and_analysis.dependabot_security_updates.status'
# Expected: enabled
```

⚠️ Neither setting survives re-archiving. If the repo will be archived again, skip both.

- [ ] **Step 3: DECISION — required status checks**

Measured: the ruleset `Protect main` (id `15582219`) requires only `Lint (ruff)` and
`Import + module smoke test`. `mypy` and `pytest` gate nothing, so PR B delivers reproducibility
with no enforcement.

**Must run after PR A is on `main`** — otherwise adding `mypy` blocks every open dependabot PR
at once, since all inherit the five errors.

**Ask the operator.** If yes:

```bash
gh api repos/fbmoulin/kratos-clone/rulesets/15582219 > /tmp/ruleset.json
# Edit the required_status_checks rule to add these two contexts verbatim:
#   "mypy (Stage A+B+C+D — full strict on personalize/ + app.py + wsgi.py + kratos_clone/* + scripts/* + downloader.py)"
#   "pytest (kratos_clone + post + client_errors)"
# and set strict_required_status_checks_policy: true
gh api repos/fbmoulin/kratos-clone/rulesets/15582219 -X PUT --input /tmp/ruleset.json
gh api repos/fbmoulin/kratos-clone/rulesets/15582219 \
  -q '.rules[] | select(.type=="required_status_checks") | .parameters.required_status_checks[].context'
# Expected: four contexts
```

Context strings must match the job `name:` values **exactly**, including the em-dash in the mypy
name. Copy them from `ci.yml`, do not retype.

---

## Task 9: Merge PR #66 (Pillow 12.3.0)

**Files:** none in this repo's working copy — this is a dependabot branch.

- [ ] **Step 1: Re-measure, because #66 is not #63**

#66 carries **16 updates**, not #63's 14 — including `playwright 1.60→1.61` and
`openai 2.41→2.50`. The suite baseline was measured against playwright 1.60.0, which is what
`render-live` drives Chromium with.

```bash
cd ~/Website-Downloader
git fetch origin pull/66/head:pr66 && git checkout pr66
uv lock --check                                   # Expected: exit 0
uv sync --locked --group dev
uv run --frozen pytest -q 2>&1 | tail -2          # Compare against the Task 2 baseline
uv run --frozen mypy --config-file pyproject.toml # Expected: Success
uv run --frozen pip-audit --vulnerability-service osv --desc on | tail -5
# Expected: the 13 pillow advisories are GONE (that is the point of the PR)
git checkout main
```

- [ ] **Step 2: If the guard is red on #66, use the script**

```bash
cd ~/Website-Downloader && git checkout pr66
./scripts/relock.sh pillow beautifulsoup4 playwright openai
git diff --stat uv.lock requirements.txt
# Review: the diff must match the packages named in the PR body. If it is much larger,
# reset and narrow the argument list.
```

- [ ] **Step 3: Merge**

**🔴 STOP — operator authorization required.** Merging a dependency PR changes
`requirements.txt`, which `Dockerfile` installs.

```bash
gh pr merge 66 -R fbmoulin/kratos-clone --rebase
```

- [ ] **Step 4: Verify `main` is green and the advisories are closed**

```bash
gh run list -R fbmoulin/kratos-clone --branch main --limit 1
gh api repos/fbmoulin/kratos-clone/dependabot/alerts \
  -q '[.[] | select(.state=="open")] | length'
# Expected: 0 open pillow advisories (requires Task 8 Step 1 to have run)
```

---

## Task 10: Reconcile the documents this work proved wrong

**Files:** Modify `docs/HANDOFF.md`; `~/claudedocs/kratos-clone-audit-2026-08-01/00-SYNTHESIS.md`

Correcting the record is part of the work that discovered the divergence — a stale runbook
reintroduces the bug it documents, with the authority of being written down.

- [ ] **Step 1: Fix `docs/HANDOFF.md:142`**

It claims four required checks including `pytest` and `pip-audit`. Measured: the ruleset requires
two (or four, if Task 8 Step 3 ran). Replace the line with the measured set and the date it was
measured.

- [ ] **Step 2: Fix `personalize/patcher.py:153-154`**

The comment states the parser behaviour backwards: it says `class` is a string under
`html.parser` and a list under lxml. Measured on bs4 4.14.3 and 4.15.0 with `html.parser` — the
parser this function uses — `tag.get("class")` returns the **list**. The code is correct; the
comment is the documented justification for an `isinstance` branch a future reader could delete
as dead. Correct the comment only; do not touch the code.

- [ ] **Step 3: Correct audit finding A8**

In `00-SYNTHESIS.md`, A8 states "No branch protection on `main`". Protection exists via a
**ruleset**; the legacy `branches/main/protection` endpoint returns 404 when protection comes
from a ruleset, which is what was measured. Rewrite to: the ruleset requires two contexts, and
`bypass_actors: RepositoryRole id=5, mode=always` means the owner bypasses it.

- [ ] **Step 4: Commit the repo-side doc fixes**

```bash
cd ~/Website-Downloader
git add docs/HANDOFF.md personalize/patcher.py
git commit -m "docs: correct required-check list and class-attribute comment

docs/HANDOFF.md listed four required status checks; the ruleset requires the
measured set recorded here. personalize/patcher.py's comment described the parser
behaviour backwards — measured on bs4 4.14.3 and 4.15.0 with html.parser,
tag.get('class') returns a list. Code unchanged; only the explanation was wrong."
```

This is a doc-only diff plus one comment, so it is pre-authorized to push directly — **after** a
PII sweep:

```bash
cd ~/Website-Downloader && gitleaks detect --no-banner --redact --log-opts="origin/main..HEAD"
# Expected: no leaks found
```

---

## Self-review

**Spec coverage.** Change 1 → Task 8 Steps 1–2. Change 2 → Task 1. Change 2b → Task 2. Change 3a
→ Task 3. Change 3b → Task 5. Change 3c → Task 5 Step 1–2. Change 3d → Task 7. Change 3e → Task 5
Step 2. Change 4 → Tasks 4 and 6. Change 5 → Task 8 Step 3. Sequence steps 1–6 → Tasks 0, 1–2,
3–7, 8, 9. Documentation debt → Task 10. **No spec section is unimplemented.**

**Placeholder scan.** `<UV_VERSION>` and `<RUN_ID>` are the only substitutions; both are resolved
by a preceding measurement step (Task 5 Step 1; the `gh run list` output). `<package>` in
`relock.sh` is a runtime argument, not a plan gap.

**Type consistency.** `find_all(name=None, attrs={...})` is used identically in Tasks 1, 7 and
the test file. `scripts/relock.sh` is referenced by the same path in Tasks 4, 6 and 9.
`astral-sh/setup-uv@c771a70e6277c0a99b617c7a806ffedaca235ff9` is identical in Tasks 5, 6 and 7.
Baselines chain explicitly: Task 0 Step 4 → Task 1 Step 6 → Task 2 Step 4 → Task 5 Step 4 →
Task 9 Step 1.

**Known deferrals** (spec §Out of scope, deliberate): deleting `requirements.txt`; removing
`|| true` from `pip-audit` — note that after Task 5 this job reports the same advisories forever
into a log nobody reads while staying green, so it is worth reconsidering; the SSRF/`file://`
unauthenticated read; `--no-sandbox`; the missing `USER` in `Dockerfile`; rate limiting on
`/start-download`.
