# CI/CD with GitHub Actions — Zero to Hero

A complete, first-timer's guide to the CI and CD pipelines in this repository: what
they are, how to push your code, how CI runs automatically, how to configure and run
CD (deploy to Databricks), and how to fix every problem we actually hit along the way.

- **Repo:** `anjijava16/-retail-insights-databricks-agents`
- **Databricks workspace:** `https://dbc-d40d7b72-eeb2.cloud.databricks.com`
- **Workflows:** [`.github/workflows/ci.yml`](.github/workflows/ci.yml), [`.github/workflows/cd.yml`](.github/workflows/cd.yml)

---

## 0. What is CI/CD here?

| | CI (Continuous Integration) | CD (Continuous Deployment) |
|---|---|---|
| **File** | `.github/workflows/ci.yml` | `.github/workflows/cd.yml` |
| **Runs when** | **Automatically** on every `push` to `main` and every pull request | **Manually only** (you click "Run workflow", or `gh workflow run`) |
| **What it does** | lint + unit tests + offline agent eval + build the wheel; optionally `bundle validate` | Deploy the Databricks Asset Bundle: validate → deploy → run ETL → grant → start app → (optional) live eval |
| **Credentials** | **None needed** for tests (Spark runs locally, agent uses fakes). `bundle validate` job is skipped if Databricks secrets are absent | **Requires** a Databricks **service principal** (OAuth machine-to-machine) |
| **Where the work happens** | GitHub's `ubuntu-latest` runners | GitHub runner drives the Databricks CLI, which deploys into your workspace |

> **Key idea:** CI proves the code is good. CD ships it to Databricks. **CD does not
> "push code to GitHub"** — pushing is a separate `git push` step you do first.

---

## 1. Prerequisites (install once)

- **git** — version control.
- **GitHub CLI (`gh`)** — easiest way to authenticate and trigger workflows.
  `brew install gh`
- A **GitHub account** with access to the repo.
- For CD only: access to the **Databricks workspace** with permission to create a
  service principal.

---

## 2. Part A — Get your code onto GitHub

CI/CD only runs on code that's on GitHub, so push first.

### 2.1 Authenticate git/gh (do this once)

> ⚠️ **The #1 gotcha (we hit this):** if an environment variable `GITHUB_TOKEN` or
> `GH_TOKEN` is set to an old/invalid value, `gh` uses it and fails with
> `HTTP 401: Bad credentials`, and `gh auth login` refuses to store new credentials.
> **Clear it first.**

```bash
# Is a stale token hiding in your shell? (prints "set" if present)
echo "GH_TOKEN=${GH_TOKEN:+set}  GITHUB_TOKEN=${GITHUB_TOKEN:+set}"

# If either is "set", clear it from THIS shell:
unset GITHUB_TOKEN GH_TOKEN

# And remove it from your shell profile so it doesn't come back
# (our bad token lived in ~/.zprofile.sh). macOS sed:
sed -i '' '/GITHUB_TOKEN/d;/GH_TOKEN/d' ~/.zprofile.sh

# Confirm it's gone (must print CLEARED):
[ -z "$GITHUB_TOKEN" ] && echo CLEARED || echo STILL_SET
```

Now log in via browser and let git reuse gh's credentials:

```bash
gh auth login -h github.com     # GitHub.com -> HTTPS -> authenticate Git? Yes -> Login with a web browser
gh auth status                  # should say: Logged in to github.com as <you>
gh auth setup-git               # git push will now use gh's credentials
```

> If `gh auth login` still says *"The value of the GITHUB_TOKEN environment variable
> is being used for authentication"*, the `unset` didn't take in this terminal — run
> `unset GITHUB_TOKEN GH_TOKEN` again (and don't `source ~/.zprofile.sh` afterward).

### 2.2 Point the repo at GitHub and push

```bash
# One-time: add the remote (only if `git remote -v` shows nothing)
git remote add origin https://github.com/anjijava16/-retail-insights-databricks-agents.git

# Push your default branch
git push -u origin main
```

The moment this lands on `main`, **CI starts automatically**.

---

## 3. Part B — Watch CI run (automatic)

CI (`ci.yml`) triggers on push to `main` and on PRs. It has two jobs:

1. **`test`** (matrix on Python 3.11 and 3.12) — runs with **no Databricks access**:
   - `ruff check` + `ruff format --check` (lint/format)
   - `pytest` with a **local Spark** session (needs Java; CI installs Temurin 17)
   - `retail-eval --offline` (agent contract eval + SQL red-team)
   - `uv build --wheel`, then uploads reports + the wheel as artifacts.
2. **`bundle-validate`** — runs `databricks bundle validate` for `dev` and `prod`.
   **Automatically skipped** if the `DATABRICKS_CLIENT_ID` secret isn't set, so CI is
   green even before you configure Databricks.

Watch it:

```bash
gh run list   --repo anjijava16/-retail-insights-databricks-agents
gh run watch  --repo anjijava16/-retail-insights-databricks-agents
```

Or in the browser: **repo → Actions tab → CI**.

---

## 4. Part C — Configure CD (one-time)

CD authenticates to Databricks as a **service principal** using OAuth
machine-to-machine. The workflow reads these from GitHub:

```yaml
DATABRICKS_HOST:          # defaulted to the workspace URL in cd.yml
DATABRICKS_CLIENT_ID:     ${{ secrets.DATABRICKS_CLIENT_ID }}
DATABRICKS_CLIENT_SECRET: ${{ secrets.DATABRICKS_CLIENT_SECRET }}
```

> Your personal `dapi…` PAT is **not** used by CD. Create a service principal instead
> (the project's rule: *no personal tokens in CI*).

### 4.1 Create the service principal in Databricks

1. **Workspace → Settings (⚙) → Identity and access → Service principals → Add → Add new.**
2. Name it e.g. `github-cd-retail-insights`.
3. Open it and copy its **Application ID** → this is **`DATABRICKS_CLIENT_ID`**.

### 4.2 Generate its OAuth secret

1. On the service principal's page → **Secrets** → **Generate secret**.
2. Copy the **Secret** value immediately (shown once) → this is **`DATABRICKS_CLIENT_SECRET`**.

### 4.3 Give it permission to deploy

The SP runs deploy, ETL, grant and app steps, so it needs enough access. Easiest on a
single-user / Free-Edition workspace: add it to the **`admins`** group. For least
privilege instead, grant:

- Workspace access entitlement + permission to **create jobs and apps**
- On the `workspace` catalog: `USE CATALOG` + `CREATE SCHEMA`
- `CAN_USE` on the `Serverless Starter Warehouse`

> A `PERMISSION_DENIED` during the CD run almost always means this step needs widening.

### 4.4 Store the two secrets in GitHub

In your repo terminal (each command prompts you to paste the value — it never echoes
or appears in logs):

```bash
gh secret set DATABRICKS_CLIENT_ID     --repo anjijava16/-retail-insights-databricks-agents
gh secret set DATABRICKS_CLIENT_SECRET --repo anjijava16/-retail-insights-databricks-agents

# verify
gh secret list --repo anjijava16/-retail-insights-databricks-agents
```

You should see both `DATABRICKS_CLIENT_ID` and `DATABRICKS_CLIENT_SECRET`.

> These are **repo-level** secrets (the `environment: dev` job can read them). To scope
> per environment instead, add `--env dev` to each `gh secret set` command.

### 4.5 (Optional) Environments and prod protection

`cd.yml` uses `environment: ${{ inputs.target }}` (dev / staging / prod). GitHub creates
the environment on first use. For **prod**, add required reviewers so deploys wait for
approval: **repo → Settings → Environments → prod → Required reviewers**.

### 4.6 (Optional) No-secret alternative: GitHub OIDC

Instead of storing `DATABRICKS_CLIENT_SECRET`, you can let Databricks trust GitHub's
OIDC tokens: add a **federation policy** on the service principal that trusts
`https://token.actions.githubusercontent.com` for this repo, delete the
`DATABRICKS_CLIENT_SECRET` line in `cd.yml`, and set `DATABRICKS_AUTH_TYPE: github-oidc`.
The workflow already requests `id-token: write`. No long-lived secret to rotate.

---

## 5. Part D — Run CD (deploy to Databricks)

### Option 1 — From the browser
**Repo → Actions tab → CD (left sidebar) → Run workflow →** choose target `dev`, toggle
`run_etl` / `run_eval`, **Run workflow**.

### Option 2 — From the terminal
```bash
gh workflow run cd.yml --repo anjijava16/-retail-insights-databricks-agents \
  -f target=dev -f run_etl=true -f run_eval=false

gh run watch --repo anjijava16/-retail-insights-databricks-agents
```

### What CD does, step by step
1. **Who am I** — prints the service principal identity (proves auth works).
2. **Validate bundle** — `databricks bundle validate -t dev`.
3. **Deploy bundle** — builds the wheel, uploads it + synced files, creates/updates the
   two jobs and the app.
4. **Run ETL** (if `run_etl`) — `retail_etl`: setup → generate → bronze → silver → gold → quality_gate.
5. **Grant** — gives the app's service principal `SELECT` on the schema.
6. **Start app and deploy its code** — launches the Databricks App; the run URL/app URL appears in logs.
7. **Live agent eval** (if `run_eval`) — scores the agent against live gold tables.
8. **Summary** — writes `databricks bundle summary` into the run summary.

---

## 6. Troubleshooting (everything we actually hit)

| Symptom | Cause | Fix |
|---|---|---|
| `gh`: `HTTP 401: Bad credentials` | a stale `GITHUB_TOKEN`/`GH_TOKEN` env var overrides gh | `unset GITHUB_TOKEN GH_TOKEN`, remove it from `~/.zprofile.sh`, then `gh auth login` |
| `gh auth login`: *"GITHUB_TOKEN environment variable is being used"* | env token still set in this shell | `unset GITHUB_TOKEN GH_TOKEN` and retry; don't re-`source` the profile |
| `git push`: `unable to get password from user` / `failed to get: -50` | no stored git credentials | `gh auth login` then `gh auth setup-git`, or use an HTTPS credential helper |
| Shell stuck at `quote>` / `pipe quote>` | pasted multi-line block including `#` comment lines | press **Ctrl-C**; paste commands **one line at a time**, no comments |
| **CD tab missing** in Actions, even though `cd.yml` is on `main` | a `workflow_dispatch`-only workflow isn't indexed by the initial push | push a commit that **modifies `cd.yml`** (any edit) to force registration |
| `databricks … 403 Invalid access token` (local) | stale PAT or wrong profile; custom profile file not sourced | export a valid `DATABRICKS_TOKEN`/host, or `databricks auth login`; ensure the file is actually sourced |
| CD fails at **Who am I** | `DATABRICKS_CLIENT_ID`/`SECRET` missing or wrong | re-check `gh secret list`; regenerate the SP secret |
| CD `PERMISSION_DENIED` / table not found | service principal lacks workspace/UC permissions | widen grants (see 4.3); ensure ETL has run |
| CI `bundle validate` shows "Skipped" | Databricks secrets not set | expected; it runs once secrets exist |
| CI tests "skipped" (local) | Java missing on the runner/machine | install JDK 17 or 21 |
| `Pattern dist/** does not match any files` (validate) | wheel not built yet | harmless warning; disappears after first build/deploy |

---

## 7. Security notes

- **Never commit tokens.** `.gitignore` ignores `.env*`, `.databrickscfg`, `*.pat`,
  `*.pem`, `*.key`, `*token*`, `*secret*`, `.zprofile.sh`, `Login_All_steps.md`, and the
  local `.monocle/` / `.vscode/` dirs.
- **Rotate any token you paste anywhere** (chat, screenshare, a file). Databricks:
  User Settings → Developer → Access tokens. GitHub: Settings → Developer settings →
  Personal access tokens.
- **Prefer the service principal (or OIDC)** over personal tokens for CI/CD.
- GitHub **secrets are write-only** — you can set/replace them but never read them back;
  `gh secret list` shows only names.

---

## 8. Quick reference

```bash
# --- one-time auth ---
unset GITHUB_TOKEN GH_TOKEN
gh auth login -h github.com
gh auth setup-git

# --- push code (runs CI automatically) ---
git push -u origin main

# --- configure CD secrets (after creating the service principal) ---
gh secret set DATABRICKS_CLIENT_ID     --repo anjijava16/-retail-insights-databricks-agents
gh secret set DATABRICKS_CLIENT_SECRET --repo anjijava16/-retail-insights-databricks-agents
gh secret list                          --repo anjijava16/-retail-insights-databricks-agents

# --- run / watch workflows ---
gh workflow list --repo anjijava16/-retail-insights-databricks-agents
gh workflow run cd.yml --repo anjijava16/-retail-insights-databricks-agents -f target=dev -f run_etl=true
gh run list   --repo anjijava16/-retail-insights-databricks-agents
gh run watch  --repo anjijava16/-retail-insights-databricks-agents
```
