# Operational pilot runbook — release 4.9.0-wfc.20

What this release could and could not do from its build session, and the exact steps that complete the operational pilot.

## Status at release

| Requirement | Status | Why |
|---|---|---|
| Contact involvement (press contacts, advisers, representatives) | **Done, tested** | `docs/REGRESSION_REPORT_4.9.0.md` |
| End-to-end user journey in a browser | **Done on the local stack** (real API, worker, migrations, PostgreSQL 16; pages served by the verification bundle, not `next start`) | The real Next.js build needs npm, unreachable from the build session; GitHub CI builds and tests it with `next start` |
| Deployment of the actual application | **NOT DONE** | Deployment is done from your own hosting account (no connector is used). The build session has no outbound network (npm, PyPI, Docker registries unreachable; Docker daemon not running), so it cannot build or deploy the images itself |
| Full airport directory loaded and verified | **NOT DONE** | The publisher is unreachable from the build session; loads automatically at deployment (pre-deploy step) |
| Real public-source pilot (three workflows) | **NOT DONE** | No outbound network; no search or extractor key for the application |
| Manual accuracy check | **NOT DONE** | Depends on the pilot |

Nothing in this release is presented as operationally complete.

## Smallest setup actions (in order) — no claude.ai connector is used

1. **Hosting.** Deploy from your own Railway account (or any host with Docker and outbound internet) following
   `docs/DEPLOY_RAILWAY_SUPABASE.md`: three services (`api`, `worker`, `web`) from the GitHub repository, PostgreSQL 16 on Supabase or a
   Railway PostgreSQL service. The build session does not deploy and does not use a hosting connector.
2. **Code.** Push this release to the GitHub repository; wait for **Actions → CI** to pass (lock gate, PostgreSQL tests, the real Next.js
   build, journeys against `next start`).
3. **Secrets** on `api` and `worker`, entered in the host's own settings (never in the repository): `DATABASE_URL`, `LOGIN_USERNAME`,
   `LOGIN_BOOTSTRAP_PASSWORD`, `PUBLIC_ORIGIN`, `ANTHROPIC_API_KEY` + `AI_MODEL` + `AI_PRICE_INPUT_PER_MTOK` + `AI_PRICE_OUTPUT_PER_MTOK`, and
   on `api` `SEARCH_PROVIDER=brave` + `SEARCH_API_KEY` (a Brave Search API key).
4. **Running the checks.** Run `tools/deploy_check.py` and `tools/pilot.py` from any machine that can reach the deployment (Python 3.11+,
   and Playwright for `--browser`) and send back the `deploy-check` and `pilot` folders. Alternatively, the claude.ai org admin can allow a
   build session outbound network access (Admin settings → Capabilities) so the session runs them itself — still without a connector.

## Steps once the setup exists

1. Deploy. The `api` pre-deploy runs the migrations (`wfc_0019`) and loads the airport directory. Check
   `https://<web>/api/health/ready`: release `4.9.0-wfc.20`, `schema_revision` `wfc_0019`, `airport_directory.full: true`.
2. Sign in, change the shared password, remove `LOGIN_BOOTSTRAP_PASSWORD`. **Settings → Budget**: monthly cap, warning, per-run cap.
3. Deployment checks:
   ```
   ATLAS_TRIAL_USER=… ATLAS_TRIAL_PASSWORD=… python tools/deploy_check.py --base https://<web> --out deploy-check prepare
   # Railway: restart api and worker
   ATLAS_TRIAL_USER=… ATLAS_TRIAL_PASSWORD=… python tools/deploy_check.py --base https://<web> --out deploy-check verify --browser
   ```
   Version, login, persistence across restart, airports (full directory, entries without IATA, ICAO search, multi-airport country
   scope), budget, visible failures, browser (Dashboard, airport directory panel, airport picker) — each PASSED / FAILED / NOT CHECKED.
4. Backup and restore: follow `docs/RESTORE_RUNBOOK.md` once on a copy; re-run `verify --backup-restored "<what, when>"`.
5. The pilot, in a market with no preloaded companies (e.g. Georgia / TBS, or Kazakhstan / ALA), with a capped budget:
   ```
   ATLAS_TRIAL_USER=… ATLAS_TRIAL_PASSWORD=… python tools/pilot.py --base https://<web> --out pilot --country GE --airports TBS --budget-usd 15
   ```
   Read `pilot/pilot.md`; choose one market development and one tender result to follow, and re-run with
   `--workflows commercial,tender --track commercial=<signal id> --track tender=<signal id>`.
6. Manual check: complete `pilot/review.csv` and `pilot/companies/review.csv` against the ORIGINAL pages (relevant / irrelevant /
   wrong attribution / missing), and record in `pilot/pilot.md`: relevant companies and opportunities, irrelevant results, missing or
   wrongly attributed people and contacts, missing websites, source failures and unfinished research, actual cost and elapsed time.
7. In the browser, the journey: search a market or airport → open a result → read its relevance → company and people → contact routes →
   record the next action → see it on the Dashboard.

Send the `deploy-check` and `pilot` folders back; the findings report is then written from them.
