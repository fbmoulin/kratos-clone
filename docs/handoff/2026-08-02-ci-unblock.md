# HANDOFF — kratos-clone, CI unblock → container now tested (2026-08-02 / 03)

> Context was cleared. This file is the source. Everything below was measured, except
> where explicitly marked as an assumption.
>
> **▶ The next task is step 2 of a two-step change: remove the committed
> `requirements.txt`.** Step 1 is done and merged. The plan is at
> `docs/superpowers/plans/2026-08-02-drop-requirements-txt.md` and it is approved —
> read its header first, it carries the decision rationale and the pre-mortem findings.

## State

- **Repo / branch:** `/home/fbmoulin/Website-Downloader` @ `main` (default branch is `main`)
- **HEAD:** `aeaec50` at the start of the 2026-08-03 session · working tree: clean except one
  untracked file (`AGENTS.md`, deliberate — see traps) · remote: in sync, 0 unpushed
  ⚠️ Re-measure. This line is a dated clue, not a fact.
- **Tests:** **358 passed, 3 skipped** — I ran `uv run --frozen pytest -q` on `main` at
  `c692e8c`. mypy strict: `Success: no issues found in 21 source files`.
- **CI:** **10 jobs**, all green on `main`, 7–12 steps each (step counts checked — a job
  finishing in seconds with *zero* steps is a runner/billing start-up failure, not a test
  failure). The 10th is new: `docker image build + smoke`, ~1m4s.
- **Security:** `pip-audit` on `main` reports `No known vulnerabilities found`; 0 open
  dependabot alerts (was 26 Pillow advisories).
- **Open PRs:** **2** — #74 (`structlog` 25.5→26.1, a **major** bump) and #75
  (`types-requests`, dev group). Both were `MERGEABLE/CLEAN` 9/9 when last measured, before
  the 10th job existed; **re-measure**. #73 was closed by Felipe — see the recurring-trap
  section below, it comes back.
- **Deploy:** `render.yaml` exists. Whether the Render service is actually connected and
  auto-deploying **was not measured** — I have no Render credentials. Treat a merge to
  `main` as possibly triggering a deploy.

## 🔒 Closed decisions — DO NOT REOPEN

**bs4 / type fix**

- **`find_all(name=None, attrs={...})` passes `name` BY KEYWORD, never positionally** —
  both forms type-check, but bs4 deleted a positional parameter (`_stacklevel`) in a minor
  release, so binding by name is the safer coupling. Discarded: `find_all(None, {...})`.
- **The filter dict must stay an inline literal.** Do not extract it to a variable "for
  readability": bs4 declares `_StrainableAttributes = Dict[str, _StrainableAttribute]`, an
  *invariant* `Dict`, so `flt = {attr: True}` infers `dict[str, bool]` and is rejected on
  **both** 4.14.3 and 4.15.0.
- **`tests/test_bs4_attr_filter.py` is a contract pin, NOT a revert detector.** It does not
  import `downloader.py`, and the `name=None` distinction is runtime-invisible on every bs4
  version tested — only a type-checker sees it. Its module docstring says so explicitly.
  Do not "strengthen" it to catch reverts; that job belongs to the `forward-compat` canary.
  An earlier draft claimed it caught reverts and that claim was false.

**uv / CI**

- **`uv sync --locked`, never `--frozen`, on install lines** — `--frozen` exits **0** on a
  pyproject/lock mismatch and installs the version that violates the declared constraint.
  Reproduced in a disposable worktree: bumping `psutil>=99.0` unlocked, `--frozen` silently
  installed the stale `psutil==7.2.2` while `--locked` failed correctly.
- **`uv run --frozen` on every execution line** — a bare `uv run` re-resolves and rewrites
  `uv.lock` mid-job, swapping versions between the install step and the test step.
- **`UV_FROZEN` is never set at workflow level** — mutually exclusive with `--locked`
  (exit 2). Discarded: setting it globally to avoid repeating `--frozen`.
- **`uv` pinned to `0.12.1`, not the `0.10.12` the design was drafted on.** All four
  load-bearing behaviours were re-verified on 0.12.1 before pinning. The plan's instruction
  to fall back to 0.10.12 applies only if a probe disagrees; none did.
- **`astral-sh/setup-uv` pinned to commit `c771a70e6277c0a99b617c7a806ffedaca235ff9`**
  (verified to be exactly what the `v9.0.0` tag resolves to), not to the tag — a re-pointed
  tag would otherwise change what executes with workspace write access on a public repo.

**Repo settings**

- **`strict_required_status_checks_policy` left `false`,** against the plan's instruction to
  enable it. Enabling it forces every branch up to date with `main` before it can merge,
  which turns each push to `main` into a rebase round for every open dependabot PR. Felipe
  chose "checks yes, strict no" explicitly.
- **The `mypy` required-check context is the TRUNCATED name.** See traps — this one bites
  hard.

**`/health` build identity**

- **Unresolvable SHA returns the literal string `"unknown"`, never omits the key and never
  returns `null` or `""`.** An absent field is indistinguishable from a build predating the
  change, which is the exact ambiguity the field removes.
- **A blank value falls through to the next source instead of being reported.** Measured
  against Docker: building without `--build-arg` sets `KC_BUILD_SHA` to the **empty
  string**, not to an unset variable, so `"build_sha": ""` would read as an answer.
- **Read per request, never cached at import** — a cached value describes the build that
  imported the module, the same stale-label bug the field exists to detect.

**Merging**

- **Every PR merged with `--rebase`, never squash.** The ruleset allows both; squash would
  collapse commits that were split specifically to be independently revertible.

**Removing `requirements.txt` — decided 2026-08-03**

- **Option A (`uv sync` into `/app/.venv`) over Option B (`uv export` piped into `pip`).**
  Both kill the bug identically — neither leaves a committed file for dependabot to edit.
  Chosen on measured evidence, by building both: A is **364 MB vs 391 MB**, and A **built
  first try** while B **failed three consecutive times** on `files.pythonhosted.org`
  timeouts. Discarded with B: keeping `pip` in the image and leaving `entrypoint.sh`
  untouched — real advantages, outweighed by the install-time fragility.
- **The CI docker-build job ships FIRST, as its own PR.** Two adversarial lenses disagreed
  about which option was worse and both were right for their own lens; the disagreement
  pointed at a third thing neither covered — *nothing built the image*. Landing the job
  first lets it prove itself against the known-good Dockerfile before it has to judge the
  new one. Discarded: one combined PR, which would have created the job and the change it
  guards in the same commit.
- **No `ignore:` rule in `dependabot.yml`, ever, for this.** Confirmed from GitHub's options
  reference that `ignore` also suppresses **security** updates (this repo sets no
  `target-branch`). A blanket ignore on `pydantic-core` would be a permanent silent CVE
  blind spot in a Rust-backed validation core. Discarded along with it: waiting for an
  upstream fix — `dependabot-core#2883` has been open since 2023.
- **The docker job is not a required status check yet, and not `continue-on-error` either.**
  It fails visibly but does not gate, because it is the slowest job and should prove
  stability first. Revisit after a few runs.

## ❌ Tried and discarded

- **`@dependabot rebase`, then `@dependabot recreate`, to fix the drift guard on #66/#70.**
  Both ran successfully; **neither fixed the drift**. The recreate reproduced the *identical
  12-package gap*. Do not retry this expecting a different outcome — dependabot's uv
  ecosystem systematically writes newer transitives into `requirements.txt` than into its
  own `uv.lock`, and no bot command reconciles that.
- **`scripts/relock.sh beautifulsoup4 openai playwright`** (naming the direct deps, which is
  what the plan's Task 9 prescribed) → the guard passes, but `--upgrade-package` resolves to
  the *latest* allowed version, not the PR's, so it moved `openai` to 2.52.0 and `playwright`
  to 1.62.0, **past the versions the PR had been reviewed for**. PR #72 corrects the docs
  that teach this.
- **`uv export` alone to reconcile a red guard** → resolves the mismatch in the wrong
  direction and **downgrades 12 transitives**, `certifi` (the CA trust store) among them.
- **`docker run <image> pip freeze` as the equivalence proof.** It was written into the
  removal plan and **does not work**: the venv `uv sync` creates contains **no `pip`**
  (measured — `/app/.venv/bin` has `python`, `gunicorn`, `playwright`, no `pip`). It would
  have errored mid-execution and could easily have been misread as an image problem. The
  working substitute is `importlib.metadata`, verified to enumerate all 42. Independently
  corroborated afterwards from Astral's own docs.
- **Building the image locally, tonight.** Six consecutive `pip install` runs failed with
  `ReadTimeoutError` from `files.pythonhosted.org` — including two against the **unmodified
  Dockerfile already on `main`**. The uv-based install of the identical package set
  succeeded first try under the same conditions. Do not read this as "the Dockerfile is
  broken"; read it as "pip has no retry hardening here and this network is flaky". GitHub's
  runners build it in ~1m4s.
- **The plan's own probes.** Three were unusable as written and each failed in the direction
  that *looks like a valid measurement*: `str.replace()` is a silent no-op when its target is
  absent (one probe printed its own expected success line without running the experiment);
  `uv run --frozen pip-audit` falls back to `PATH` and finds a global conda binary, inverting
  the proof; and a bare `uv export` earlier in the same probe script re-locked and erased the
  drift a later `uv lock --check` was meant to detect. Corrections are recorded at the top of
  `docs/superpowers/plans/2026-08-02-unblock-ci.md`.

## ✅ The `pydantic-core` recurring trap — CLOSED 2026-08-03 by deleting `requirements.txt`

> **This section is now history, kept because it is the evidence behind the fix.** The bug
> needed a committed `requirements.txt` for Dependabot to edit; there is no longer one. Option
> 1 in "The options, ranked" below is what shipped. If a `pydantic-core` PR appears again it
> will have to touch `pyproject.toml` + `uv.lock` through uv's own resolver, which cannot
> produce the unsatisfiable pair described here.

**Status when written: #73 was closed by Felipe at 09:59Z, and it would have come back.**
Researched 2026-08-02 07:15; this section supersedes an earlier draft that proposed a fix
which does not exist.

This is the failure the drift guard was built for, and it is not new. The same PR has now
appeared **four times**:

| PR | Outcome |
|---|---|
| **#43** | **MERGED** — `requirements.txt +1/-1` — **broke the Docker build** |
| **#48** | MERGED — the fix, restoring the pin (`requirements.txt +2/-2`) |
| **#53** | Closed by dependabot itself ("updatable in another way") |
| **#73** | Closed by Felipe, 4 min after it opened |

**Closing does not stop it.** Dependabot said so on #73, verbatim: *"This pull request was
built based on a group rule. Closing it will not ignore any of these versions in future
pull requests."*

**#73 changes exactly one file, `requirements.txt`, `+1/-1`** — it bumps `pydantic-core`
2.46.4 → 2.47.0 and leaves `uv.lock` and `pyproject.toml` untouched. But:

```
pydantic 2.13.4 declares:  pydantic-core==2.46.4     (an exact pin)
#73's requirements.txt has: pydantic==2.13.4
                            pydantic-core==2.47.0
```

Those two lines are **mutually unsatisfiable**. `pip install -r requirements.txt` returns
`ResolutionImpossible`, and `requirements.txt` is what `Dockerfile` installs. This is
verbatim the bug that broke the build in PRs #48, #49 and #51 — the one that caused the
`pip` ecosystem to be retired in favour of `uv`. It has now reappeared **through the `uv`
ecosystem** (branch `dependabot/uv/production-dependencies-ff6f40ee51`,
`package-manager=uv`), so retiring `pip` did not close the class.

**The guard caught it.** `requirements.txt ⇄ uv.lock sync` fails; the other 8 jobs pass. Note
the disguise: a one-file, one-line diff invites a merge without reading. Before this
session the guard compared against a fresh network resolution and would have let it through.

### ❌ Correction: "just bump `pydantic`" does not work — measured

An earlier draft of this section proposed bumping `pydantic` so it would pull a compatible
core. **That escape hatch does not exist.** Measured 2026-08-02 in a disposable worktree:

| Command | Result |
|---|---|
| `uv lock --upgrade-package pydantic-core` | stays **2.46.4** — uv refuses to move it |
| `uv lock --upgrade-package pydantic --upgrade-package pydantic-core` | **both stay** put |
| latest `pydantic` on PyPI | **2.13.4** — already installed, and it pins `pydantic-core==2.46.4` |

`pydantic-core 2.47.0` is published, but **nothing consumes it yet**. It is unreachable by
any coherent resolution of this project until `pydantic` itself ships a release pinning it —
at which point the group will bump both together and the guard will pass on its own.

Also do NOT reach for `scripts/relock.sh`: there is no transitive drift to reconcile here.
The requested state is unreachable, not merely unsynchronised.

### Root cause: `requirements.txt` is a generated artifact that looks like a manifest

Dependabot cannot tell the difference, so it edits single lines in it with no regard for what
`uv.lock` can satisfy. Both #43 and #73 touched **only** `requirements.txt`, `+1/-1`.

The `dependabot.yml` note claiming the uv ecosystem "never touches requirements.txt" is
**measured false** — partially corrected in #72, but the sharper truth is this: for a
lock-pinned transitive, dependabot edits `requirements.txt` *alone*, producing a file that
`pip install -r` cannot resolve.

### No security pressure, and `ignore` is not free

- **0 dependabot advisories** on `pydantic`/`pydantic-core`; `pip-audit` clean. There is no
  urgency behind this bump.
- An `ignore` rule would stop the recurrence, **but it also suppresses security updates.**
  Confirmed on GitHub's Dependabot options reference: options marked with the security icon
  — `ignore` among them — "also change how Dependabot creates pull requests for security
  updates, except where `target-branch` is used", and this repo does not use `target-branch`.
  So `ignore: pydantic-core` would blind the repo to a future CVE in a Rust-backed validation
  core. There is currently **no `ignore` rule at all** in `dependabot.yml`.

### The options, ranked

1. **Delete `requirements.txt`** and have the `Dockerfile` install from `uv.lock`
   (`uv sync --locked`). This removes the generated-artifact-that-looks-like-a-manifest, and
   with it this entire bug class — plus the drift guard's reason to exist and
   `scripts/relock.sh`. **Note this is exactly what the spec deliberately deferred** (plan
   §Known deferrals, first item). The deferral has now cost one broken build and four PRs.
   Five files reference it: `Dockerfile`, `build.sh`, `.github/workflows/ci.yml`,
   `.github/dependabot.yml`, `scripts/relock.sh`.
2. **Do nothing.** The guard catches it every time, loudly, and closing takes ten seconds.
   Cost is recurring noise; benefit is zero blind spots. Defensible.
3. **Version-scoped ignore** (`dependency-name: pydantic-core`, `versions: ["2.47.0"]`) —
   silences exactly this one, keeps CVE visibility for every other version. Returns if
   `2.48.0` ships while `pydantic` still pins `2.46.4`.

⛔ **Not recommended: a blanket `ignore` on `pydantic-core`.** The security blind spot is
permanent and silent; the noise it removes is neither.

The other two are clean and were not merged only because this session was wrapping up:
- **#74** — `structlog` 25.5.0 → 26.1.0, `MERGEABLE/CLEAN`, 9/9 green. Note it is a **major**
  version bump; the suite passing is evidence but read the changelog.
- **#75** — `types-requests`, dev group, `MERGEABLE/CLEAN`, 9/9 green.

## ✅ Step 2 is DONE — `requirements.txt` removed, container installs from `uv.lock`

**Executed 2026-08-03**, per `docs/superpowers/plans/2026-08-02-drop-requirements-txt.md`.
Both steps of the two-step change have now landed. What shipped:

- `.dockerignore` no longer excludes `uv.lock` (it is the install source now). Two invariants
  are commented in the file: `.venv` stays excluded, and the sync stays before `COPY . .`.
- `Dockerfile` runs `uv sync --locked --no-dev` into `/app/.venv`, with the `uv` binary copied
  from `ghcr.io/astral-sh/uv` **pinned by multi-arch index digest** (`sha256:cf4eedca…`), not
  by tag. `ENV UV_PYTHON_DOWNLOADS=never` forces the base image's interpreter rather than a
  uv-managed download, so the container runs the same CPython the CI matrix validates.
- 🔴 `ENV PATH="/app/.venv/bin:$PATH"` — load-bearing, because `entrypoint.sh` invokes bare
  `gunicorn`.
- `requirements.txt` and `scripts/relock.sh` deleted; the CI guard renamed to
  `uv.lock ⇄ pyproject.toml sync`, keeping only `uv lock --check`.
- `build.sh` rewritten to `uv sync` (dead code on both documented deploy paths, updated anyway
  so it does not become a trap).

### 🔴 Operator consequence that did not exist before

**`docker exec <c> pip install X` is now a silent no-op.** `pip` resolves to the system
`/usr/local/bin/pip` while `python` resolves to `/app/.venv/bin/python`, so the package
installs where the app never reads it — and the command still prints success. Correct form:

```bash
docker exec <c> uv pip install --python /app/.venv/bin/python X
```

Related, for whoever optimises the image later: `/app/.venv/bin/python` is a **symlink** to
`/usr/local/bin/python3.12`. It works because the target lives in the same image. A
multi-stage build copying only `/app/.venv` into a different final stage yields a dangling
symlink unless that stage uses the same base image.

### ⚠️ Local Docker builds keep failing on the network — that is not this repo

Measured across two nights, now **8 failures**: the `pip` path failed 6× with
`ReadTimeoutError` from `files.pythonhosted.org` (two of them against the *unmodified*
`Dockerfile` on `main`), and the new `uv` path reached `playwright install` and failed with
`ECONNRESET` pulling Chrome for Testing from Google's CDN. The discriminator that matters:
`ReadTimeoutError` / `ECONNRESET` on a download ⇒ network, retry or let CI build it.
`ResolutionImpossible`, a `COPY` error, or an apt failure ⇒ real, stop.

⚠️ **The Claude Code background-task notification reported `exit code 0` for two builds that
actually exited 1 and 2.** Chain an `echo "EXIT=$?"` into the command and read that, not the
notification. A follow-up `docker run` on the missing image then fails with *"pull access
denied"*, which reads like a credentials problem and is not.

Then, in order and not blocking:

0. **The `pydantic-core` PR will come back.** See the recurring-trap section — it is the one
   item with a wrong-if-ignored outcome.

1. **Redact the PII sitting in the Claude Code memory files.** This is the largest live
   finding and it is *outside* this repo — see "Outside this repo" below. It is not
   optional in the sense of being unimportant; it is optional in the sense that nothing in
   `kratos-clone` depends on it.
2. Widen the `ruff` CI scope to `personalize/` and `tests/`. Both are ruff-clean today
   (measured), so changing the two `run:` lines in the `lint` job should pass first try.
   See `TODO.md`.
3. Delete the four merged remote branches: `fix/bs4-find_all-overloads`,
   `ci/pin-jobs-to-lockfile`, `feat/health-build-sha`,
   `docs/relock-name-transitives-not-directs`. Rebase-merges leave them behind, because the
   branch tip is not an ancestor of `main`.

## 🔴 Outside this repo — PII inside the Claude Code memory files

Found 2026-08-02 while answering whether `~/.claude/projects/*/memory/` should be
versioned. It should not, and the reason is the finding:

- **8 memory files contain real CNJ case numbers.** Two are serious: one holds a table of
  six TJES repossession cases with **full party names**, vehicle plates, amounts and the
  recommended ruling for each; another identifies a **6-year-old child with TEA/TDAH** by
  name, tied to a case number.
- These were never swept. `projects/` has always been gitignored, so it was never a
  repository, so no repo-scoped scan ever reached it.
- ✅ One real secret found and redacted: a Qdrant Cloud API key (signed HS256 JWT, write
  scope) that had sat in plaintext for 164 days. 🔴 **Redacting does not revoke it — it
  must be rotated in the Qdrant dashboard, and only Felipe can do that.** The other two
  gitleaks hits are false positives (a spec filename, and the string `kratos-v5-ec2.pem`,
  which is a key *filename*, not a key).

Detail, and the commands that re-find all of it:
`~/.claude/projects/-home-fbmoulin/memory/reference_pii-inside-the-memory-files-2026-08-02.md`

## ⚠️ Active traps

- 🔴 **Renaming the `mypy` job breaks `main`.** Its declared `name:` is **114 characters**;
  GitHub truncates emitted check-run names at **98**, ending in a literal `...`. The ruleset
  context is the *truncated* string. A context that never matches an emitted check does not
  error — it creates a required check that never arrives, so **every PR blocks forever**. If
  you shorten that name, update the ruleset in the same change, then confirm an open PR
  reports `MERGEABLE/CLEAN` and not `BLOCKED`. Read emitted names with:
  `gh api repos/fbmoulin/kratos-clone/commits/main/check-runs -q '.check_runs[] | "\(.name|length)|\(.name)"'`
- 🔴 **`AGENTS.md` is untracked and exists in a single copy. NEVER `git add -A` or
  `git add .` in this checkout.** Stage explicitly, path by path.
- ⚠️ **Every production-group dependabot PR will arrive with the drift guard red.** This is
  systematic, not a glitch. Fix by naming the **transitives** the guard's diff lists — not
  the direct deps the PR bumps. `scripts/relock.sh`'s header explains why (after #72 lands).
- ⚠️ **`bandit` prints `High: 10` under CONFIDENCE, not Severity.** The Severity row reads
  `Low: 10, Medium: 0, High: 0`, exit 0. Read the right column before diagnosing.
- ⚠️ **In Claude Code's Bash tool, `grep` and `find` are shadow functions** running the
  Claude Code binary with a V8 heap; they have crashed this WSL host twice. Use
  `command grep -r` or `rg` for anything recursive.
- ⚠️ **`downloader.py` is legacy upstream code and is deliberately outside the `ruff` CI
  scope.** Its 28 findings are not new debt. `CLAUDE.md` says new work goes in
  `kratos_clone/`.
- ⚠️ **The 14 `print()` calls in `kratos_clone/__main__.py` and `personalize/cli.py` are
  legitimate CLI output**, not logging violations. Do not "fix" them.

## Open (not blocking)

- **PII in the Claude Code memory files** — see the section above. Largest live item.
- **`ruff` scope narrower than `bandit`/`mypy`** — `personalize/` and `tests/` are clean but
  unguarded. Recorded in `TODO.md`.
- **No metrics or tracing** — zero prometheus/otel/sentry/datadog/statsd. Observability is
  structured logs + `/health` + `/api/client-errors` + the browser logger. Recorded in
  `TODO.md` so the absence reads as a decision, not an oversight.
- **`actions/checkout@v7` still on a mutable tag** while `setup-uv` is SHA-pinned. Low risk
  given `permissions: contents: read` and no untrusted-PR-with-write trigger.
- **Two pre-existing `E501` findings at `app.py:234-235`** — confirmed present at HEAD
  before this session's changes.
- **The hosted service question is untouched and predates this session** — whether the
  Render instance is running, and the unauthenticated arbitrary-file-read finding (A1) it
  would expose. See `~/claudedocs/kratos-clone-audit-2026-08-01/00-SYNTHESIS.md`.

## Confidence

- **Measured and confirmed:** every test count, every mypy result, `pip-audit` output on
  `main`, all 9 CI job results *with step counts*, the ruleset contents (re-read after
  writing), the check-name truncation (98 vs 114, byte-counted), the Docker `ARG`→`ENV`
  mechanism on all three paths (with build-arg, without, runtime `-e`), the
  `uv sync --frozen` vs `--locked` divergence (reproduced in a disposable worktree), the
  12-package dependabot drift (measured on #66 and re-measured identically after the #70
  recreate), and that `personalize/`/`tests/` are ruff-clean.
- **Read the code but did not execute:** that Render injects `RENDER_GIT_COMMIT` at runtime
  for Docker services — the resolver reads it if present, but I could not verify Render's
  behaviour without an account. `KC_BUILD_SHA` is the guaranteed path.
- **Assumption:** that the remaining 8 stale remote branches are safe to delete. I did not
  audit what predates this session; only my own four are confirmed merged.
