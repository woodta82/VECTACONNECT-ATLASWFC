# VECTA Connect / ATLAS / DYNAMIC MARKET INTELLIGENCE
## Release report — release `3.7.0-wfc.9`, schema `wfc_0010` (unchanged), validation rules v7, 28 October 2026

This is the only build report. It replaces the report for `3.6.0-wfc.8`; where an older document disagrees, this report
is current. The requirement-by-requirement classification is `docs/ACCEPTANCE_MATRIX.md`.

**Configured customer:** World Freight Company. This release preserves and exercises:
- the identity VECTA Connect / ATLAS / DYNAMIC MARKET INTELLIGENCE, Poppins and the existing VECTA design;
- **one shared username and password**;
- all **nine freight capability areas**;
- single-country, multiple-country, regional and worldwide discovery;
- the corrected chronology rules: cancellation, reopening, publication-date and status-freshness protections.

Human approval is still required for external communications, bookings, pricing, and contractual or operational
commitments. No VECTA contacts, deals or credentials were imported. The live VECTA deployment was not touched.

### Commit identification

| What | Commit |
|---|---|
| **Verified commit.** Every check in section 1 ran on a clean `git archive` export of it. | `ed837c05788c303bd2b53170b2826b5147a5e962` on branch `wfc/spec-completion-2026-10-28`, based on `e6d56c5` (release 3.6.0-wfc.8) |
| **Release commit.** Adds this report, `PULL_REQUEST.md`, the change manifest and two README notes. | Recorded in `RELEASE-COMMIT.txt` in the delivered ZIP. `git diff --stat ed837c0 <release>` shows documentation only. |

### Status: not production-ready

**Met in the software as tested here (sections 0 and 1):**
- All nine original business workflows produce reconciled, evidence-backed outputs from inputs loaded through the same
  import and discovery paths WFC data will use. Every number is checked against a value computed independently.
- Missing data produces an explicit gap, never a zero or a confident recommendation.
- All 19 datasets complete upload → mapping → validation → preview → commit → reconciliation → duplicate → correction →
  reversal (or a refusal naming the re-import route).
- No historical, excluded, contradictory, unsupported, cancelled or stale record reaches a qualified-live status in any
  area.

**Not met:**
- "Real discovery and extraction have measured results": no provider key and no authorised source.
- "The production application installs and runs reproducibly": the lock files cannot be generated, and the official
  images and the real Next.js server cannot be run from this session.
- Live WFC adapters: no API documentation or credentials.

**All workflow evidence uses synthetic data** (invented organisations, example domains). It proves the application's
rules, not WFC's figures. No simulated result is presented as live functionality.

### Result labels

| Label | Meaning |
|---|---|
| **Passed** | Ran here, on the verified commit, and passed. The evidence file is named. |
| **Failed** | Ran here and returned failure, including expected failures. |
| **Simulated** | Ran here with a local stand-in for something external. The result shows only what the stand-in allows. |
| **Unexecuted** | Could not run here. The exact dependency and the way to run the check are given. |

---

## 0. Instruction checklist (28 Oct 2026)

| # | Item | What was done | Evidence | Result |
|---|---|---|---|---|
| 1 | **Release foundation.** Locks, clean install, gate; official PostgreSQL, API, worker and real Next.js stack; authenticated journeys including production configuration, migrations, backup/restore, worker recovery and budget enforcement; logs kept on failure. | Nothing substituted. Journeys extended (journey L). Migrations, upgrade path and dump/restore run on PostgreSQL 16. Journeys run on the process stack and on the substitute container stack (worker restart in `test_f`, budget in `test_02` and `test_f`). | `lock-gate.log`, `access-check.log`, `real-image-attempt.log`, `migrations.log`, `browser/`, `container-journeys/` | **Failed / unexecuted** for locks, official images and `next start` (sections 2 and 4); **passed** on the stacks available here |
| 2 | **Nine business workflows** with independently calculated expected results; explicit gaps. | `domain/recommendations.py` (capacity, trucking, technology, network); opportunity creation from each; network coverage gaps; outsourcing live-only demand. **Defect found and fixed:** a feeder that does not run on the ship date was "insufficient data" when the cutoff was unknown; now infeasible, giving a coverage gap. | `tests/integration/test_business_workflows.py` (10 tests); journey L | **Passed** (synthetic data) |
| 3 | **Data onboarding** for every dataset; docs reconciled; templates; required-field explanations; source, period, currency, units, freshness; refresh labels. | Docs, `FIELDS.md` and templates generated from the contracts with a drift test; the stale "dry run only / 9 datasets" text removed; rules shown on the import screen and "Data used" in every area. **Defect found and fixed:** a corrected airline name was previewed as an update but only added as an alias. | `tests/integration/test_data_onboarding.py` (20), `tests/unit/test_import_docs.py` (3); journeys `test_03`, `test_04`, `test_l` | **Passed** |
| 4 | **Real external intelligence**: authorised source, provider under a capped budget, measured against manual review. | Nothing run against a real provider. Scripted-extractor evaluation re-run as a regression and kept separate (section 5). | `access-check.log` (`ANTHROPIC_API_KEY` not set) | **Unexecuted** (section 4) |
| 5 | **Live WFC adapters** only against supplied interfaces. | All four stay **Not connected**. The exact information each needs is in `docs/CONNECTORS_AND_DATASETS.md`. No endpoint invented. | registry and docs | **Unexecuted**: nothing supplied |
| 6 | **Qualification and prioritisation across all nine areas.** | Rank, rank reason (with the provisional ordering rule) and missing inputs on every ordered list; the four dimensions kept separate. | `tests/integration/test_qualified_live_guard.py` (20: control qualifies; eight non-live cases never do; no override passes any of the 13 factual checks); earlier chronology suites unchanged and passing | **Passed** |
| 7 | **Access and deployment.** Identity, Poppins, single login, nine areas, geography modes, WFC; ¶33 superseded; Netlify. | `BRIEF_TRACEABILITY.md` ¶33 and section K. `netlify.toml`, build preflight, signed proxy; the API verifies `x-nf-sign` when `PROXY_SIGNATURE_SECRET` is set; `docs/DEPLOYMENT.md` §8 names where each part runs and says a static ZIP is not the system. | `test_signed_proxy_requirement`; journeys `test_01`, `test_10`, `test_12`, `test_d` | **Passed**, except the Netlify deployment itself (**unexecuted**: no site or API host) |
| 8 | **One evidence-backed release.** | This report, the ZIP, `VERSION` 3.7.0-wfc.9, the SHA above, `docs/MIGRATIONS.md` (no new migration), `docs/ACCEPTANCE_MATRIX.md`. | — | Delivered. **Not delivered:** the lock files (item 1) |

## 1. Passed checks (verified commit, clean export; PostgreSQL 16, Python 3.13, Node 22, Chromium)

| # | Check | Command | Result | Evidence |
|---|---|---|---|---|
| 1.1 | Python lint, types, secret scan | `ruff check app tests ../e2e ../tools`, `mypy app`, `tools/secret_scan.py` | ruff 0 findings; mypy 0 errors (69 files); secret scan 0 findings | `static-checks.log` |
| 1.2 | Backend tests on PostgreSQL | `pytest -q -rs tests` | **1084 passed, 0 failed, 0 skipped** (6 min 32 s), up from 1027 | `backend-pytest.log`, `backend-junit.xml` |
| 1.3 | TypeScript type check and bundle; offline lint rules; real ESLint 10 | `node verify/build.mjs`, `verify/lint.mjs`, `verify/eslint-core.mjs` | type check passed (41 files, 26 pages); bundle built; 0 lint findings; 0 ESLint problems. `npm run lint` (eslint-config-next) not run: npm unreachable | `frontend-checks.log` |
| 1.4 | Nine business workflows | `tests/integration/test_business_workflows.py` | 10 passed (one per area plus missing-data) | `backend-junit.xml` |
| 1.5 | Data onboarding, every dataset | `tests/integration/test_data_onboarding.py`, `tests/unit/test_import_docs.py` | 20 + 3 passed | `backend-junit.xml` |
| 1.6 | Qualified-live guard | `tests/integration/test_qualified_live_guard.py` | 20 passed | `backend-junit.xml` |
| 1.7 | Signed-proxy requirement (Netlify) | `tests/sql/test_http_security.py::test_signed_proxy_requirement` | passed: good token accepted; wrong key, expired, wrong issuer, `alg=none`, malformed and missing rejected with 403; liveness exempt; short secret refused; secret redacted | `backend-junit.xml` |
| 1.8 | Earlier protections (status chronology and freshness, publication dates, relevance, announced vs open, geography, eligibility) | earlier suites | unchanged and passing | `backend-junit.xml` |
| 1.9 | Migrations, upgrade path, backup/restore | `alembic upgrade head` on an empty database; re-run; non-empty refused; `pg_dump`/`pg_restore`; `wfc_0002` → … → `wfc_0010` → head | Head `wfc_0010` (89 tables, 249 countries, 31 regions, 0 re-check jobs on a fresh install). Re-run a no-op. Non-empty database refused. Dump and restore at `wfc_0010`. Every step exits 0; head from `wfc_0010` changes nothing (no migration in this release). | `migrations.log`, `migration-upgrade-path.log` |
| 1.10 | Container stack smoke test (PostgreSQL, migrate, API, worker, web containers) | `tools/docker_substitute/run.sh` | Build and `up --wait` exit 0. `/health/ready` reports release `3.7.0-wfc.9` and `wfc_0010`. 401 unauthenticated; login and briefing 200; security headers present; jobs succeed after a worker restart. | `docker-substitute/report.txt` |
| 1.11 | Authenticated browser journeys, container stack | `tools/docker_substitute/run_e2e.sh` | **28 passed** (6 min 32 s), including new journey L | `container-journeys/` |
| 1.12 | Authenticated browser journeys, process stack | `tools/run_journeys.sh` | **28 passed** (6 min 20 s). No page errors; the console shows only the four expected 401 responses of signed-out session checks, as in 3.6.0-wfc.8 | `browser/` (screenshots 40–43 for journey L) |
| 1.13 | Evaluation regression, all eight sets | `python -m evaluation.run --split …` | Every report identical to 3.6.0-wfc.8 (extraction rules unchanged) | `evaluation/` |
| 1.14 | Access checks (recorded, not retried around) | registry `curl`, `docker pull`, `gh auth status`, repository listing | npm and PyPI hosts do not resolve; Docker Hub returns 403; the GitHub token is invalid; the session's repository list is empty; `ANTHROPIC_API_KEY` is not set (28 Oct, 07:26 UTC) | `access-check.log`, `real-image-attempt.log` |

During development the first journey run failed `test_03`, `test_04`, `test_08` and `test_l`: the new dataset rules on
the import screen also contain the word "committed", which made the journeys' text selector ambiguous, and the later
failures followed from the setup import stopping. The journeys now wait for the confirmation by its status role. Both
complete runs above are on the verified commit.

## 2. Failed checks

| Check | Result | Why | What makes it pass |
|---|---|---|---|
| Lock gate `tools/check_locks.sh` on the clean export | **Failed** (exit 1): the three lock files are MISSING | They cannot be generated here (section 4). The gate is working and correctly reports failure. | Commit the lock files generated by the `commit-locks` workflow in your repository. |
| `docker pull python:3.13-slim`, `node:22-alpine`, `postgres:16-alpine` | **Failed** (×3): Docker Hub 403 | The official base images cannot be fetched from this session. | The CI `docker` job on a host with registry access. |

## 3. Simulated checks (not production evidence)

| What was simulated | Stand-in | Used by | What the result does **not** show |
|---|---|---|---|
| AI provider | `tools/fake_ai_provider.py`; the evaluation harness's scripted extractor; scripted model replies in integration tests | 1.2, 1.10–1.13 | the configured AI extractor's quality or cost |
| Public sources | the synthetic fixture site; authored evaluation notices; genuine notices reconstructed from captured text | 1.2, 1.11–1.13 | retrieval from live portals |
| WFC data | synthetic CSV imports (invented forwarders, lanes, agreements, stations, events) | 1.4–1.6, journeys | WFC's actual figures |
| Next.js server | the verification bundle (real page components, esbuild and Next shims), not `next start` | 1.10–1.12 | the real `next build` output and server |
| Official container base images | substitutes from this host's Python, Node and PostgreSQL, same Dockerfile layout, user, ports and health checks | 1.10, 1.11 | official image builds and installation from hash locks |
| Production configuration | container runs use `ENVIRONMENT=development` | 1.10, 1.11 | the production start-up refusals (unit-tested only) |

## 4. Unexecuted checks, with the exact dependency for each

| Check (item) | Missing dependency | How it gets done |
|---|---|---|
| **Generate, verify and commit `frontend/package-lock.json`, `backend/requirements.lock`, `backend/requirements-dev.lock`; clean install; release gate** (1) | **Your GitHub repository (`owner/repo`), attached to this session with push access.** Re-checked 28 Oct: registries unreachable, GitHub token invalid, repository list empty. Requested before and not supplied. No lock was written by hand. | Attach the repository and push `wfc/spec-completion-2026-10-28`. Run `commit-locks` (generates the locks constrained to `backend/requirements.verified.txt`, installs from them with `--require-hashes`, `pip check`, `npm ci`, `tsc --noEmit`, runs `tools/check_locks.sh`, opens a PR). Merge it. |
| **Official PostgreSQL, API, worker and real Next.js stack; journeys A–L; production configuration** (1) | Docker Hub and npm, through the same repository's CI | CI `docker` and `e2e` jobs after the locks are merged; artefacts kept with `if: always()`. |
| `npm run lint` (eslint-config-next), `next build`, `npm audit`, `pip-audit` | npm, PyPI | CI `frontend` and `security` jobs |
| **Configured AI extractor on originals; capped country discovery measured against manual review** (4) | `ANTHROPIC_API_KEY`, `AI_MODEL` and prices as a server-side secret; a named authorised source; a budget cap. The answer given was "Not available now". | `tools/live_trial.py` (`docs/DEPLOYMENT.md` §5), then `python -m evaluation.run --split heldout7 --extractor configured`. A reviewer fills `comparison.csv`. |
| **Live WFC adapters** (5) | Per adapter: system and API documentation, a change feed, the field dictionary, a read-only test credential, written authorisation (`docs/CONNECTORS_AND_DATASETS.md`) | Implement each adapter against the supplied interface with checkpoints, retries, idempotent upserts, reconciliation, health and freshness. |
| **Netlify deployment** (7) | A Netlify site, an HTTPS API host, and the shared `PROXY_SIGNATURE_SECRET` | `docs/DEPLOYMENT.md` §8, including the post-deploy checks. |
| Push the branch and open the pull request | the repository | `PULL_REQUEST.md` (base `wfc/amendments-2026-10-27c`) |

## 5. Evaluation: scripted extractor, kept separate from real extraction

The harness (`backend/evaluation/`) runs each case through the production pipeline on a fresh database with a **scripted
extractor** that returns each case's prepared proposals, correct and incorrect alike. The figures measure the
application's rules; they are **not** real extraction results, and there are **no real-provider results** in this
release.

This release did not change the extraction or evidence rules, so no new held-out set was created. All eight sets were
re-run on the verified commit as a regression, and every report is identical to 3.6.0-wfc.8:

| Set | Cases | Opp. precision | Opp. recall | Actionable precision | Actionable recall | Field acc. | False 'supported' |
|---|---|---|---|---|---|---|---|
| heldout7 | 14 | 8/8 | 8/8 | 4/4 | 4/4 | 38/38 | 0/1 |
| heldout6 | 17 | 16/16 | 16/16 | 6/6 | 6/6 | 77/77 | 0/5 |
| heldout5 | 18 | 7/7 | 7/7 | 6/6 | 6/6 | 35/35 | 0/10 |
| heldout4 | 10 | 7/7 | 7/7 | 7/7 | 7/7 | 35/35 | 0/7 |
| heldout3 | 20 | 16/16 | 16/16 | 13/13 | 13/13 | 78/80 | 0/15 |
| heldout2 | 12 | 8/8 | 8/8 | 8/8 | 8/8 | 32/32 | 0/15 |
| genuine (reconstructed) | 19 | 7/7 | 7/7 | 1/1 | 1/1 | 34/35 | 0/41 |
| tuning | 32 | 23/23 | 23/23 | 23/23 | 23/23 | 92/92 | 0/36 |

These are small, authored or reconstructed samples. They do not show coverage of any country or of the world.

## 6. Known limitations and open questions for WFC

- **Provisional thresholds and ordering rules.** Capacity (85% / 50% utilisation, ±10% demand), technology (5 sessions,
  20% booking rate, 3 failures), the 90-day dormancy window and every ranking rule are labelled provisional until WFC
  confirms them or outcomes are available to calibrate them.
- **Company-wide capability** (no station) counts as coverage in every territory for network gaps. A capability WFC
  holds only in some countries should be recorded with its station.
- **Netlify proxy limit.** Netlify ends proxied requests after 26 seconds; very large import previews (up to 20 MB)
  may need splitting.
- **Carried over:**
  - reopening needs explicit, dated wording;
  - `NOTICE_AGE_REVIEW_DAYS` (90) is a build default, not an agreed policy;
  - `backend/Dockerfile` copies `tests/` into the image;
  - migrations have no downgrade: restore from backup.

## 7. Delivery contents

- `atlas-wfc/`: the repository with `.git` (all branches), plus `atlas-wfc.bundle` and `RELEASE-COMMIT.txt`.
- `evidence/`:
  - static, backend, frontend, migration and lock-gate logs;
  - `docker-substitute/`, `container-journeys/`, `browser/`;
  - `evaluation/`: current reports for every set, the earlier run-once sets, and `previous/` (release 3.6.0-wfc.8 and
    earlier runs);
  - `live-trial-dry-run/`, `access-check.log`, `real-image-attempt.log`, `verified-commit.txt`,
    `clean-verification-script.sh`.
- The data is synthetic, authored, or captured from public notices as recorded. The only credentials are the documented
  local-verification defaults, and the evidence was checked to make sure they do not appear in it.
