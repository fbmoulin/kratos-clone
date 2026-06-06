# Runbook — Rotate `OPENAI_API_KEY` & set it on Render

**When to run this:** the `OPENAI_API_KEY` was exposed (committed, pasted into a
chat/transcript, logged, shared), or on a routine rotation schedule. It is the
**single gate** before the personalization feature works in production —
`/api/personalize/structure` and `/api/personalize/run` return `5xx` on first
call without a valid key (the OpenAI client is constructed lazily at request
time, so a missing/dead key fails per-request, not at boot).

> **Treat an exposed key as fully compromised.** Rotating means **revoking the
> old key**, not just adding a new one. Until the old key is revoked, anyone who
> saw it can spend against your account.

---

## Overview

```
1. OpenAI  →  create a new key, then REVOKE the old one
2. Render  →  set OPENAI_API_KEY to the new value (triggers redeploy)
3. Local   →  update .env (dev + live integration tests)
4. Verify  →  new key works in prod, old key is dead
```

Time: ~10 minutes. You need: OpenAI account (owner/admin), Render account with
access to the `website-downloader` service.

---

## Step 1 — Rotate the key at OpenAI

1. Sign in at <https://platform.openai.com>.
2. Open **API keys**: <https://platform.openai.com/api-keys>
   (or **Settings → API keys**).
3. **Create the new key first** (so prod is never without one longer than
   necessary):
   - Click **Create new secret key**.
   - Name it something traceable, e.g. `kratos-clone-render-2026-06`.
   - (Recommended) scope it to a **Project** and set a **monthly spend limit**
     under **Settings → Limits** — blast-radius control if it leaks again.
   - Click **Create**, then **copy the key immediately** — OpenAI shows the
     full secret **only once**. Paste it somewhere safe temporarily (you'll put
     it in Render and `.env` next).
4. **Revoke the old/exposed key:**
   - Find the old key in the list (if you can't tell which one leaked, revoke
     every key you can't positively account for, or revoke all and rely on the
     new one).
   - Click the **⋯ / trash / Revoke** control next to it → confirm.
   - Revocation is **immediate** — the old key returns `401` from then on.
5. **Check for abuse:** open **Usage** (<https://platform.openai.com/usage>) and
   confirm there's no unexpected spend from the period the key was exposed.

> Tip: there is no "edit key value" in OpenAI — rotation is always
> *create new + revoke old*. The new secret is a different string.

---

## Step 2 — Set the new key on Render

The key is a **secret**, so it lives in the Render dashboard, **not** in
`render.yaml` (which is committed to git). Non-secret tuning vars like
`PORT` and `KCD_MAX_CONCURRENT_RENDERS` stay in `render.yaml`; credentials never do.

1. Sign in at <https://dashboard.render.com>.
2. Open the service **`website-downloader`**.
3. Left sidebar → **Environment**.
4. If `OPENAI_API_KEY` already exists, click it and **Edit**; otherwise click
   **Add Environment Variable**.
   - **Key:** `OPENAI_API_KEY`
   - **Value:** the new secret from Step 1 (paste carefully — **no surrounding
     quotes, no trailing spaces or newline**).
5. Click **Save Changes**.
   - Render **automatically triggers a redeploy** when an env var changes — the
     new value is only live after that deploy completes (env vars are read at
     process start).
6. Watch the deploy under the **Events** / **Logs** tab until it shows
   **"Deploy live"**.

> **Alternatives (optional):** for multiple services sharing the key, use a
> Render **Environment Group** and link it to the service. For file-based
> secrets you could use a **Secret File**, but a plain env var is what this app
> reads (`os.getenv("OPENAI_API_KEY")`), so keep it simple.

---

## Step 3 — Update the local `.env`

The repo's local `.env` (gitignored, `chmod 600`) also held the old key — used
for local dev and the live integration tests (`RUN_OPENAI_LIVE=1`).

```bash
cd /home/fbmoulin/Website-Downloader
# Edit the OPENAI_API_KEY line to the new value (use your editor):
$EDITOR .env
# Re-confirm perms + that it is NOT tracked by git:
chmod 600 .env
git check-ignore .env   # must print ".env" (i.e. it is ignored)
git status --porcelain  # must NOT list .env
```

The `.env` line should read exactly:

```
OPENAI_API_KEY=sk-...new-key...
```

(See `.env.example` for the full variable reference — it documents `OPENAI_API_KEY`
as `[request]`-lifecycle, no default, required for the personalize endpoints.)

---

## Step 4 — Verify

**New key works in production** (after the Render redeploy is live):

1. Open the app's `/personalize` page.
2. Submit the intake form (or POST to `/api/personalize/structure`).
3. A **2xx** response means the key works. A **5xx** with a logged
   `personalize_*` error means the key is missing/invalid (see Troubleshooting).

Health endpoint (does **not** need the key — only confirms the service is up):

```bash
curl -s https://<your-render-host>/health
# {"status":"ok", ...}
```

Optional — confirm locally with the gated live test (spends ~$0.10):

```bash
RUN_OPENAI_LIVE=1 uv run pytest tests/integration -v
```

**Old key is dead:** any call with the old secret now returns `401` from OpenAI.
You can confirm with the OpenAI usage page showing the revoked key as inactive.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `/api/personalize/*` still `5xx` after deploy | Redeploy not finished, or var not saved | Wait for **"Deploy live"**; re-check the var exists under **Environment** |
| `401`/auth error in logs | Wrong/old/typo'd key, or trailing whitespace/newline pasted | Re-copy the new key; ensure no quotes/spaces; Save → redeploy |
| `429` / quota error | New key's project has no credit or hit the spend limit | Add credit / raise the limit under OpenAI **Settings → Limits** |
| Works locally, fails on Render | `.env` updated but Render var not | Set it in the **Render dashboard** (Step 2) — `.env` is not deployed |
| Var set but old value still used | Service didn't restart | Trigger **Manual Deploy → Deploy latest commit**, or **Restart** |
| `render.yaml` change didn't apply | Service is **not** Blueprint-managed | Dashboard is authoritative — set env vars there |

---

## Security notes

- **Never** put the key in `render.yaml`, source, commits, or logs. It belongs
  only in the Render dashboard (prod) and the gitignored `.env` (local).
- Prefer **project-scoped keys + a monthly spend limit** so a future leak is
  bounded.
- After any exposure, also skim **OpenAI → Usage** for anomalous activity.
- Rotating on a schedule (e.g. quarterly) is good hygiene even without a leak.
