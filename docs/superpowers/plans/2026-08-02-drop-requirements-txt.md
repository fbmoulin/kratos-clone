# Plan — remove `requirements.txt`, install from `uv.lock`

**Status: APPROVED 2026-08-03. Step 1 of 2 is DONE and merged. Step 2 is this plan.**

## Read this before executing

**Step 1 (prerequisite) already landed:** PR #76, on `main` at `c692e8c`. It added a
`docker image build + smoke` job to CI — the first thing in this pipeline that ever built
the container. It builds the image, asserts `import app` works inside it, asserts
`gunicorn` resolves on PATH, and asserts `/health` reports the `build_sha` it was built
from. Measured green on `main`: 10/10 jobs, the docker job in ~1m4s.

That job is **the safety net for everything below.** Before it existed, a Dockerfile change
had zero automated coverage; two independent pre-mortem lenses rated that HIGH.

### Why Option A and not the alternative

Research (2026-08-03) surfaced a second approach the community converged on: keep `pip`
installing into the system Python and generate the requirements **inside** the build
(`uv export … | pip install`), rather than switching to `uv sync`. Both kill the bug
equally — neither leaves a committed file for dependabot to edit. Felipe chose **Option A
(`uv sync`)** on this evidence, all measured by building both variants:

| | A — `uv sync` → `/app/.venv` | B — `uv export` → `pip` |
|---|---|---|
| Runtime packages | 42 | 42 (+`pip`) |
| Image size | **364 MB** | 391 MB |
| Network resilience | **built first try** | **3 consecutive failures**; needed `--timeout 120 --retries 10` |
| Runtime change | needs `ENV PATH` | none |

⚠️ The network evidence is stronger than it looks: **six** `pip install` runs failed with
`ReadTimeoutError` from `files.pythonhosted.org` that night, including two against the
**unmodified Dockerfile on `main`**, while the uv path succeeded first try under identical
conditions. The current `Dockerfile` has no `--retries`/`--timeout` hardening; Option A
makes that moot rather than patching it.

### Pre-mortem findings that must be honoured (3 adversarial lenses, 2026-08-03)

- 🔴 **`docker exec … pip install` silently no-ops under Option A.** Measured in the built
  image: `pip` resolves to `/usr/local/bin/pip` (system site-packages) while `python`
  resolves to `/app/.venv/bin/python`. An operator hot-patching a running container gets a
  success message and the app never sees the package. **Mitigation: document it** in the
  Dockerfile and `docs/HANDOFF.md` — the correct form is
  `uv pip install --python /app/.venv/bin/python`.
- 🔴 **The venv's `python` is a symlink out of the venv** — measured in the image:
  `/app/.venv/bin/python -> /usr/local/bin/python3.12`. It works because the target exists
  in the same image. **A future multi-stage build that copies only `/app/.venv` would
  produce a dangling symlink** unless the final stage uses the same base image. Leave a
  comment saying so.
- ⚠️ `render.yaml` has **no `healthCheckPath`**, so Render promotes on a TCP socket check.
  The `/health` endpoint this session added does not participate in the deploy gate.
  Out of scope here, but worth a follow-up.
- ⚠️ The rollback section below describes git-revert. Render's **dashboard rollback** reuses
  a prior build artifact and is faster; it also auto-disables auto-deploy. Prefer it for an
  actual incident.

### Upstream context — this is not a local quirk

- [`dependabot-core#13912`](https://github.com/dependabot/dependabot-core/issues/13912) —
  **OPEN.** uv-ecosystem PRs edit a `requirements*.txt` without touching `uv.lock`. Our
  `pydantic-core` recurrence is a direct instance.
- [`dependabot-core#2883`](https://github.com/dependabot/dependabot-core/issues/2883) —
  **OPEN since 2023.** "Ignore a specific manifest." Multiple users describe this exact
  layout. **There is no file-level ignore**, and `.gitattributes: linguist-generated` has
  no effect on Dependabot.
- An `ignore:` rule is **not** a safe workaround: GitHub's options reference marks `ignore`
  as also affecting **security** updates (no `target-branch` here), so it would create a
  silent CVE blind spot.

Full evidence: `~/claudedocs/kratos-clone-audit-2026-08-01/` —
`DECISAO-requirements-txt.md`, `research-uv-docker.md`, `research-dependabot-uv.md`,
`research-render-deploy.md`, `premortem-lens-{deploy,ci,runtime}.md`.

---

**Goal.** Delete `requirements.txt` and make the container install directly from `uv.lock`,
removing the generated-artifact-that-looks-like-a-manifest that dependabot keeps editing.

**Why now.** `requirements.txt` is exported from `uv.lock` but is indistinguishable from a
hand-maintained manifest, so dependabot edits single lines in it with no regard for what the
lock can satisfy. Measured: the identical `pydantic-core` PR has appeared **four times**;
**#43 was merged and broke the Docker build**; #48 was the fix. Every mitigation so far —
the drift guard, `scripts/relock.sh`, the `dependabot.yml` note — contains the symptom. This
removes the cause. It is the first item in the CI-unblock spec's *Known deferrals*; the
deferral has now cost one broken build and four PRs.

**Blast radius.** This changes how the production image is built. If the Render service is
connected to this repo, merging alters a real deploy. Treat the merge as tier 🔴.

---

## Measured starting state (2026-08-02 07:20)

| Fact | Value | Consequence for this plan |
|---|---|---|
| `.dockerignore:52` | **excludes `uv.lock`** | 🔴 blocker — must be removed first, or `uv sync --locked` cannot see the lock |
| `pyproject.toml`, `.python-version` | **not** excluded | reach the build context already |
| `Dockerfile:16,19` | `COPY requirements.txt` + `pip install -r` | the main consumer |
| `build.sh:5` | `pip install -r requirements.txt` | second consumer — non-Docker build path |
| `entrypoint.sh` | `exec gunicorn wsgi:app …` — **bare `gunicorn`** | 🔴 `uv sync` installs into `/app/.venv`; without a PATH change this breaks at runtime, not at build |
| `render.yaml` | `env: docker`, `dockerfilePath: ./Dockerfile` | Render uses the Dockerfile, not `build.sh` |
| `Procfile` | `web: bash entrypoint.sh` | run command only, not a build step |
| CI job `requirements.txt ⇄ uv.lock sync` | **not** a required status check | safe to rename or reshape |
| Required checks | `Lint (ruff)`, `Import + module smoke test`, `mypy (…)`, `pytest (…)` | none of them is touched by this plan |
| Suite | 358 passed, 3 skipped | the invariant |
| `requirements_integration.txt` | **does not exist** (referenced by untracked `AGENTS.md`) | out of scope; do not create it |

---

## ✅ Pre-flight measurements (done 2026-08-02 22:30, before any edit)

Three things were verified locally, which materially de-risks the rest of this plan.

**1. Blocker confirmed empirically, not from a doc claim.** `uv.lock` really is excluded from
the build context:

```
COPY failed: file not found in build context or excluded by .dockerignore: stat uv.lock
```
`pyproject.toml` and `.python-version` copy fine in the same probe. So exactly one line of
`.dockerignore` has to change.

**2. Equivalence is already PROVEN — no image build required.** Installed a parallel venv with
`UV_PROJECT_ENVIRONMENT=/tmp/uvsync-test uv sync --locked --no-dev` and compared against
`requirements.txt`:

- **42 packages, identical.**
- The only apparent difference was `colorama`, which `requirements.txt` carries as
  `colorama==0.4.6 ; sys_platform == 'win32'`. Measured: that marker evaluates **False** on
  Linux, so `pip install -r requirements.txt` would not install it either. Not a difference.

⇒ The install-source swap is behaviour-preserving on Linux. The image build below is now
confirmation, not discovery.

**3. 🔴 The verification method originally written into this plan does not work.**
It said `docker run --rm <image> pip freeze`. **The uv-created venv contains no `pip`** —
measured, `/app/.venv/bin` has `python`, `gunicorn`, `playwright`, but no `pip`. That command
would have errored mid-execution and, worse, could have been misread as an image problem.

**Use `importlib.metadata` instead** — verified it enumerates all 42:

```bash
docker run --rm <image> python -c "
import importlib.metadata as md
for d in sorted(md.distributions(), key=lambda d: d.metadata['Name'].lower()):
    print(f\"{d.metadata['Name']}=={d.version}\")"
```

---

## Task 0 — Baseline from the current image

Equivalence is already proven at the venv level (above). This task exists to catch what the
venv comparison cannot see: things the *image* provides outside the venv — the system Python's
own packages, and Chromium.

- [ ] Record the baseline image's package set and prove the current image works:

```bash
cd ~/Website-Downloader
docker build -t kc-before:baseline .          # slow: downloads Chromium
docker run --rm kc-before:baseline python -c "
import importlib.metadata as md
for d in sorted(md.distributions(), key=lambda d: d.metadata['Name'].lower()):
    print(f\"{d.metadata['Name']}=={d.version}\")" | sort > /tmp/pkgs.before.txt
wc -l /tmp/pkgs.before.txt
docker run --rm kc-before:baseline python -c "import app; print('boots')"
docker run --rm kc-before:baseline sh -c 'command -v gunicorn'
```

If the baseline build fails, **stop** — `main` is already broken and that is a different task.

⚠️ Expect the before/after diff to be **non-empty** here even though the venvs match: the
current image installs into the system Python (so `pip`, `setuptools`, `wheel` appear), while
the new one installs into `/app/.venv`. Every line of that diff must be explained as
"tooling that was never a runtime dependency" — if a *runtime* package differs, stop.

---

## Task 1 — Let the lock reach the build context

- [ ] Remove the `uv.lock` line from `.dockerignore`, replacing it with a comment saying why
      it must stay in (it is now the install source).
- [ ] Verify it actually reaches the context — the file being present in the repo is not the
      same thing:

```bash
docker build -q -f - . <<'EOF'
FROM busybox
COPY uv.lock pyproject.toml .python-version /probe/
RUN ls -l /probe/
EOF
```

Expect all three listed. If `uv.lock` is missing, `.dockerignore` still excludes it.

---

## Task 2 — Rewrite the Dockerfile to install from the lock

- [ ] Copy the `uv` binary from the official image, **pinned by digest**, not by tag —
      same reasoning as the SHA-pinned `setup-uv` in CI. Resolve the digest first and record
      it in the commit message.
- [ ] `COPY pyproject.toml uv.lock .python-version ./` **before** the source, so the
      dependency layer caches independently of code changes.
- [ ] `uv sync --locked --no-dev` — **one sync, not two.**
      — `--locked` (not `--frozen`): fails loudly on a pyproject/lock mismatch instead of
        installing a violating version. Same contract the CI jobs use.
      — `--no-dev`: matches what `requirements.txt` was exported with, so the package set is
        comparable.
      — **`--no-install-project` omitted, and the docs' second `uv sync` after `COPY . .`
        omitted too.** Both measured 2026-08-02 against this project: with `package = false`,
        `--no-install-project` produces a byte-identical package set (same 42 dist-info dirs),
        and a second `uv sync` after the source copy reports `Checked 42 packages` and installs
        nothing. The canonical two-sync pattern in Astral's guide exists to install *the project
        itself*; this project is not a package, so the second step is dead weight. Fewer steps,
        one less thing to be wrong.
      ℹ️ The app code still imports fine: `WORKDIR /app` puts the source on `sys.path`, and the
        modules are top-level — nothing depends on the project being pip-installed.
- [ ] 🔴 `ENV PATH="/app/.venv/bin:$PATH"` — **the failure mode this prevents is silent and
      runtime-only.** `entrypoint.sh` calls bare `gunicorn`; today it resolves because pip
      installed globally. After `uv sync` the binaries live in `/app/.venv/bin`, the image
      still builds green, and the container dies on start. Do not leave `entrypoint.sh` to
      discover this.
- [ ] Keep, unchanged: the Playwright Chromium install, the `GIT_SHA`/`KC_BUILD_SHA` block,
      `ENV PORT`, `EXPOSE`, `CMD`.
- [ ] ⚠️ `playwright install --with-deps chromium` must run **after** the venv is on PATH (or it
      resolves a different Python) **and while still root** (the `--with-deps` step runs `apt`).
      Both conditions hold today because this Dockerfile has no `USER` directive. That is
      currently a *pre-existing* audit finding (`docs/AUDIT.md` P3, missing `USER`) — note the
      coupling: **adding a non-root `USER` later, without also moving this line, breaks the
      build.** Leave a comment in the Dockerfile saying so, so the two findings do not collide.

**Verify — the load-bearing step. Note `pip` is NOT available in the new image's venv:**

```bash
docker build -t kc-after:lock .
docker run --rm kc-after:lock python -c "
import importlib.metadata as md
for d in sorted(md.distributions(), key=lambda d: d.metadata['Name'].lower()):
    print(f\"{d.metadata['Name']}=={d.version}\")" | sort > /tmp/pkgs.after.txt
diff /tmp/pkgs.before.txt /tmp/pkgs.after.txt
docker run --rm kc-after:lock python -c "import app; print('boots')"
docker run --rm kc-after:lock sh -c 'command -v gunicorn && gunicorn --version'
docker run --rm kc-after:lock python -c "
from playwright.sync_api import sync_playwright
with sync_playwright() as p: b = p.chromium.launch(args=['--no-sandbox']); print('chromium ok'); b.close()"
```

The 42 **runtime** packages must match exactly — that is already proven at the venv level, so a
runtime difference here means the Dockerfile is wrong, not the lock. Differences confined to
`pip`/`setuptools`/`wheel` are expected and acceptable: those are build tooling the base image
provided incidentally, never declared runtime dependencies.

- [ ] Prove the container actually serves, not just imports:

```bash
docker run --rm -d -p 8099:8080 --name kc-smoke kc-after:lock
until curl -sf localhost:8099/health >/dev/null; do sleep 2; done
curl -s localhost:8099/health
docker rm -f kc-smoke
```

Expect JSON including `build_sha`. This is the first end-to-end proof that PATH is right.

---

## Task 3 — `build.sh` (researched: it is dead code on BOTH documented deploy paths)

Researched 2026-08-02, sources in `~/claudedocs/kratos-clone-audit-2026-08-01/research-render-deploy.md`:

- **Render, `env: docker`, runs only the Dockerfile.** Render's docs state plainly: *"you can't
  customize the command that Render uses to build your image."* `build.sh` is never invoked.
- **Railway, per this repo's own `RAILWAY_DEPLOY.md`, also uses the Dockerfile** ("Railway vai
  detectar automaticamente o Dockerfile") — it is not a buildpack route, contrary to what the
  `Procfile`'s presence suggests. Both documented platforms converge on the same file.
- Heroku, and a pure Nixpacks/Railpack build with no Dockerfile, are hypothetical — no doc and
  no config in this repo points at them. (For the record, Nixpacks and Railpack **do** support
  `uv.lock` natively, running `uv sync --no-dev --frozen`, so even that hypothetical route would
  survive deleting `requirements.txt`.)

⇒ `build.sh` has **no live consumer**. Updating it is hygiene, not a deploy requirement.

- [ ] Rewrite it to `uv sync --locked --no-dev` + `uv run playwright install chromium`, keeping
      its shape and its tolerant `|| echo` on system deps. Rationale: leaving a script that
      installs from a file we deleted is a trap for whoever runs it next, and "it is dead code"
      is exactly the belief that decays.
- [ ] Verify it runs on a clean checkout in a disposable worktree.

🔴 **Atomicity constraint discovered here.** Because both platforms build from the Dockerfile,
the `.dockerignore` change, the Dockerfile rewrite and the `requirements.txt` deletion **must
land in the same commit**. Split across commits, any intermediate state fails the next deploy
with a `COPY` error for a missing file. This is already satisfied by shipping one PR, but it
means: do not "land the safe parts first".

---

## Task 4 — Delete `requirements.txt` and reshape the CI guard

- [ ] `git rm requirements.txt`
- [ ] In `.github/workflows/ci.yml`, the `requirements-lock-sync` job loses its export/diff
      step but **keeps `uv lock --check`** — pyproject↔lock drift is still real and nothing
      else detects it. Rename the job to reflect what remains.
      ✅ Safe: this job is **not** one of the 4 required contexts (measured). Re-verify with
      `gh api …/rulesets/15582219` before renaming, and confirm an open PR still reports
      `MERGEABLE/CLEAN` afterwards.
- [ ] Remove the now-dead `::error::` annotation pointing at `scripts/relock.sh`.

---

## Task 5 — Delete `scripts/relock.sh`, rewrite the dependabot note

- [ ] `git rm scripts/relock.sh` — its entire purpose was regenerating `requirements.txt`.
- [ ] Rewrite the `.github/dependabot.yml` NOTE. It currently explains the drift and the
      remedy; both cease to exist. Replace with a short record of **why `requirements.txt`
      was removed**, so nobody reintroduces it: dependabot edited it independently of the
      lock, which broke the Docker build in #43.
- [ ] Grep for stragglers: `command grep -rn 'relock.sh\|requirements.txt' --include='*.yml' --include='*.sh' --include='Dockerfile' .`

---

## Task 6 — Documentation

- [ ] `CLAUDE.md:132` — mentions `pip-audit -r requirements.txt`; annotate as historical.
- [ ] `docs/HANDOFF.md` — the CI-pipeline section names the old job; update, and add a line
      recording that the container installs from the lock.
- [ ] `CHANGELOG.md` — new entry under `[Unreleased]`.
- [ ] `TODO.md` — close the recurring-`pydantic-core` item this removes.
- [ ] `docs/PRE_DEPLOY_AUDIT_2026-05-10.md` — **leave alone.** It is a dated audit record and
      its claims were true when written. Rewriting history to match the present is how audit
      trails stop being evidence.
- [ ] Update `docs/handoff/2026-08-02-ci-unblock.md` **and its prompt, in the same commit.**

---

## Task 7 — Ship

- [ ] Full local gate: `pytest -q`, `mypy`, `ruff check`/`format --check`, `bandit`,
      `uv lock --check`.
- [ ] PII sweep on the diff (`gitleaks protect --staged`), repo is PUBLIC.
- [ ] Branch + PR. **Do not push to `main` directly** — the diff touches `Dockerfile`,
      `.github/workflows/`, `.github/dependabot.yml`.
- [ ] Read all **10** CI jobs (was 9; PR #76 added `docker image build + smoke`), with
      **step counts**, not just pass/fail. The docker job is the one that matters here —
      it is the only thing that exercises the Dockerfile this plan rewrites.
- [ ] 🔴 **STOP — operator authorization required before merging.** This changes how the
      production image is built.

---

## Rollback

`git revert` of the PR restores `requirements.txt`, the `.dockerignore` line, `build.sh`,
`relock.sh` and the guard together, because they land as one PR. Verified rollback path:
rebuild the image from the reverted tree and re-run the Task 2 smoke.

## Explicitly out of scope

- The missing `USER` directive in `Dockerfile` (pre-existing, in `docs/AUDIT.md` as P3).
- `--no-sandbox` and the SSRF/`file://` read (pre-existing audit findings).
- Multi-stage build to drop the `uv` binary from the final image — a size optimisation, not
  a correctness fix, and it would widen this diff.
- `requirements_integration.txt`, referenced by the untracked `AGENTS.md`. It does not exist
  and this plan does not create it.

## Open question for the operator — now measured

`build.sh` and `.dockerignore` are two of the six files inherited **byte-identical** from
`asimov-academy/Website-Downloader`, which has no licence file. Verified 2026-08-02 by diffing
against `upstream/main`: all six (`DEPLOY.md`, `RAILWAY_DEPLOY.md`, `Procfile`, `build.sh`,
`.dockerignore`, `.python-version`) are still identical.

Editing them reduces the verbatim-redistribution surface flagged in the audit
(`00-SYNTHESIS.md`, licence finding) — a side benefit, but it is a change to inherited content
and worth naming rather than doing silently.

**Why the `uv.lock` exclusion is safe to reverse — traced, not assumed.** It was introduced by
upstream in `082c96b` (2026-02-02, *"Adicionar suporte Docker para Playwright no Render"*,
author Rodrigo Soares Tadewald) with the comment:

```
# UV lock file (not needed in container)
uv.lock
```

The exclusion was deliberate but **premised on the container installing from
`requirements.txt`** — which is exactly the premise this change removes. It is not a security
or image-size decision being undone; it is an assumption that stops being true. Only one commit
has ever touched `.dockerignore`, so there is no later intent layered on top.
