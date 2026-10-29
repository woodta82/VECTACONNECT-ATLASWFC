# Deployment — VECTA Connect / ATLAS / DYNAMIC MARKET INTELLIGENCE

Configured customer: **World Freight Company**. One shared username and password for the whole workspace.

> **Status:** not production-ready. Do not describe this build as production-ready until every check listed as
> *outstanding* in `BUILD_REPORT.md` §3 has passed (committed lockfiles and a clean install from them, real `next build`,
> ESLint with `eslint-config-next`, dependency audits, the official container images) and a real authorised source and
> AI provider have been exercised under a capped budget (§5 below).

## 1. What runs

| Service | Image | Role |
|---|---|---|
| `migrate` | `backend/Dockerfile` | `alembic upgrade head` (sole owner of the schema), then exits |
| `api` | `backend/Dockerfile` | FastAPI on :8000 (internal only) |
| `worker` | `backend/Dockerfile` | `python -m app.worker_main`: discovery runs, schedules, budget-controlled extraction, deadline revalidation, partner-fit refresh. Run 1–N copies; leases make them safe together |
| `web` | `frontend/Dockerfile` | Next.js on :3000; proxies `/api/*` to the API (same origin, no CORS) |
| database | PostgreSQL 16 | external in production; a dedicated database for this customer |

## 2. Before the first deployment

1. Put the repository on GitHub and run the CI workflow once with **Run workflow** (`workflow_dispatch`). The
   `commit-locks` job generates `backend/requirements.lock`, `backend/requirements-dev.lock` and
   `frontend/package-lock.json` (constrained to the tested versions in `backend/requirements.verified.txt`) and opens a
   pull request. Review and merge it. From then on every build installs from the committed locks.
2. Confirm the CI jobs `frontend` (type check, ESLint, **`next build`**), `security` (`pip-audit`, `npm audit`),
   `docker` (official images, health) and `e2e` (browser journeys against `next start`) are green.
3. Prepare secrets in your secret store using `deploy/production.env.example` (placeholders only).

## 3. Deploy

```bash
# on the host, with the secrets exported or in a root-only env file
docker compose -f docker-compose.yml -f deploy/docker-compose.production.yml \
  --env-file /secure/atlas.env up -d --build
```

- TLS terminates at your reverse proxy in front of `web` (published on 127.0.0.1:3000 by the override).
  `PUBLIC_ORIGIN` must be the `https://` address users open; `TRUSTED_PROXY_HOPS` the number of proxies in front.
- The API refuses to start in `production` with development credentials, a non-HTTPS origin or API docs enabled.

## 4. Check it

```bash
curl -fsS https://<host>/api/health/live     # {"status":"live","release":"4.1.0-wfc.11","build":"<BUILD_ID>"}
curl -fsS https://<host>/api/health/ready    # "schema_revision":"wfc_0012"; 503 until migrations match
curl -s -o /dev/null -w "%{http_code}\n" https://<host>/api/briefing   # 401 without the session
```

Sign in with `LOGIN_USERNAME` and the one-time `LOGIN_BOOTSTRAP_PASSWORD`, change the password under **Settings**,
then remove `LOGIN_BOOTSTRAP_PASSWORD` from the environment and restart `api`.

## 5. Turn on AI extraction (optional)

Set `ANTHROPIC_API_KEY`, `AI_MODEL`, `AI_PRICE_INPUT_PER_MTOK`, `AI_PRICE_OUTPUT_PER_MTOK` on the worker, then under
**Settings** set a monthly budget and a per-run cap and lift the kill switch. Each discovery run gets one approved
ceiling; long documents are read completely in sections within it, and reading pauses (document shown *partly read*,
run *incomplete*) when the ceiling is reached until a person approves more or the next run continues.

**Controlled live-source trial (required before production; OUTSTANDING until done).** `tools/live_trial.py` runs the
whole procedure against a deployment: with the provider key on the worker only and the shared login in the environment,

```bash
ATLAS_TRIAL_USER=... ATLAS_TRIAL_PASSWORD=... python tools/live_trial.py --base https://<host> \
  --source-url https://<portal>/tenders/ --source-name "<portal>" --countries KE \
  --authorisation-note "terms permit automated retrieval; see <link>" \
  --monthly-cap 5 --warn-at 4 --per-run-cap 1 --out trial-$(date +%F)
```

It checks that the provider is connected, sets the capped budget, registers and enables the source (retention on, so
passages can be inspected), runs ONE country search, waits, and writes `run.json`, `queue.json`, `opportunities.json`,
`comparison.csv` (one row per opportunity for the reviewer to check against the original notice, plus rows for missed
notices) and `report.md` (actual provider cost, fetch failures, unread material and remaining work from the run itself).
A reviewer fills in `comparison.csv`, summarises missed notices, unsupported interpretations, fetch failures, unread
material, cost and remaining work in `report.md`, and copies the figures into `BUILD_REPORT.md`. The simulated runs in
`BUILD_REPORT.md` never count as this trial.

## 6. Upgrading an existing installation

Back up first (`docs/RESTORE_RUNBOOK.md`); migrations have no downgrade. Then run `alembic upgrade head` (the `migrate`
service does this). `docs/MIGRATIONS.md` lists what each revision changes and re-checks; 4.1.0-wfc.11 adds `wfc_0012`
(evidence-backed relationship research, additive, no worker re-check) after 4.0.0-wfc.10's `wfc_0011`, and summarises how
existing records are carried over.

## 7. Operate

- Backups: `pg_dump -Fc` of the database plus the `atlas_snapshots` volume (`docs/RESTORE_RUNBOOK.md`).
- Scale workers: `docker compose ... up -d --scale worker=3`.
- Logs: JSON lines on stdout; no secrets or document bodies are logged.
- WFC internal connectors (bookings, schedules, operations, finance, channel analytics) remain **Not connected** until
  WFC supplies endpoints and credentials; until then use the import templates in `docs/import-templates/`.

## 8. Netlify as the web front end (optional)

Netlify can host the **web front end only**. It cannot run the API, the worker or PostgreSQL (the worker is a
long-running process; discovery runs, schedules and extraction happen there). A ZIP or static upload of `frontend/`
to Netlify is **not** the system and does not work on its own: every screen reads the API.

| Part | Where it runs |
|---|---|
| Web front end (Next.js) | Netlify, built from this repository with `netlify.toml` (Netlify applies its OpenNext adapter automatically for Next.js 13.5 and later) |
| API (`api`) and worker (`worker`, 1–N) | A container host you control, from `backend/Dockerfile`, e.g. `docker compose -f docker-compose.yml -f deploy/docker-compose.production.yml up -d migrate api worker` on a VM, or the same images on a container platform. The API must be reachable over HTTPS from Netlify |
| PostgreSQL 16 | A managed PostgreSQL service or the database host, reachable from the API and worker only (never public) |
| Snapshots volume | Next to the API and worker (`SNAPSHOT_DIR`) |

Steps:

1. Deploy PostgreSQL, then `migrate`, `api` and `worker` on the container host with TLS on the API's public name
   (for example `https://api.atlas.example.com`). Set on the API: `PUBLIC_ORIGIN` = the Netlify site's https address
   (custom domain or `https://<site>.netlify.app`), `PROXY_SIGNATURE_SECRET` = a random value of at least 32
   characters, and `TRUSTED_PROXY_HOPS` = the number of proxies between the browser and the API (Netlify plus any load
   balancer in front of the API).
2. In `netlify.toml`, replace `API_ORIGIN_PLACEHOLDER` with the API's host name. The build stops while the placeholder
   is present (`deploy/netlify/preflight.mjs`).
3. In the Netlify site settings, set the environment variable `PROXY_SIGNATURE_SECRET` to the same value, with a scope
   that includes **Runtime** (Netlify uses it to sign each proxied request in the `x-nf-sign` header; the API rejects
   unsigned or wrongly signed requests with 403, except `/health/live`).
4. Link the repository to the Netlify site. The base directory, build command, publish directory and Node version
   come from `netlify.toml`.
5. Check: `https://<site>/api/health/ready` returns the release and `wfc_0012`; `https://<api-host>/health/ready`
   called directly returns 403 (`proxy_signature`); signing in through the site works and the session cookie is
   `__Host-atlas_session`; after a sign-in, the audit log shows the browser's address, not Netlify's (adjust
   `TRUSTED_PROXY_HOPS` if not).

Limits to know: Netlify times out a proxied request after 26 seconds. Discovery and extraction run in the worker, so
they are not affected; a very large import preview (the limit is 20 MB) can exceed it, so split large files.

Status: this configuration follows Netlify's published documentation (Next.js adapter; rewrites and proxies, including
signed proxy redirects). The signature check on the API is tested; **a deployment to Netlify has not been executed**
(no Netlify site or API host was supplied).
