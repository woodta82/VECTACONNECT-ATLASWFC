# VECTA Connect / ATLAS / DYNAMIC MARKET INTELLIGENCE

Freight commercial intelligence, configured for **World Freight Company** (customer and use case, not the product name).

It lets the team see global opportunities, understand their relevance, and identify the people and relationships needed
to pursue them:

**Discover an opportunity → understand it → research the organisations and relevant people → identify existing
relationships or introduction routes → track progress.**

Five sections: **Overview**, **Opportunities**, **Discover**, **Relationships**, **Settings**. The screens, record types
and research rules are described in `docs/SCREENS_AND_WORKFLOWS.md`. Discovery and relationship research need no WFC
bookings, financial data or operational feeds; those optional tools are kept under Settings.

> **Release:** see `VERSION` (one identifier, used by the API health endpoints, UI footer and exports).
> **Status:** read `BUILD_REPORT.md` first. It is the single current release report and separates *passed*, *failed*, *simulated* and *unexecuted* checks.
> - Backend: unit, PostgreSQL 16, live-API, integration and process-level tests run for real.
> - Browser: the real page components ran in Chromium (Playwright) against the live API, worker, a synthetic source site and a **simulated** AI provider. They were bundled by a verification harness (`frontend/verify`), because Next.js itself could not be installed here; the Next production build is run by CI.
> - Docker: exercised with **substitute** base images built from host binaries (`tools/docker_substitute`), because base images could not be pulled. The browser journeys also run against that container stack (`tools/docker_substitute/run_e2e.sh`).
> - Not production-ready: committed lockfiles and a clean install from them, `next build`, `eslint-config-next`, audits, official images, the evaluation of the configured AI extractor and the controlled live-source trial are unexecuted (`BUILD_REPORT.md` §3 names the dependency for each). Measured results (authored sets, two held-out sets run once, nineteen reconstructed genuine notices covering all nine areas; scripted extractor, small samples) are in `BUILD_REPORT.md` §5. The lock gate runs and fails until the locks are committed.

## Layout

| Path | What it is |
|---|---|
| `backend/app/domain/` | Framework-free rules: evidence, qualification, rights, capability, metrics, economics, scoring, imports, SSRF-safe retrieval, AI guard |
| `backend/app/services/` | Workflows over the `Database` protocol: auth, ingestion, opportunities, imports, operations, durable worker |
| `backend/app/http/` | Security middleware and auth endpoints (Starlette) |
| `backend/app/api/` | FastAPI routers, one per navigation section |
| `backend/app/repo/queries.py` | Every SQL statement, each PREPAREd against PostgreSQL in tests |
| `backend/migrations/` | Alembic lineage `wfc` (sole schema owner): `wfc_0001` → … → `wfc_0010` (SQL in `sql/`; upgrade steps in `docs/MIGRATIONS.md`) |
| `backend/app/reference/` | ISO 3166 countries, UN M49 regions, economic groupings (geography for discovery and filters) |
| `backend/evaluation/` | Extraction-quality evaluation: authored notices (tuning / fresh held-out), genuine public notices with provenance, and the runner that measures the pipeline |
| `backend/tests/` | `domain/` (no DB), `sql/` (real PostgreSQL), `api/` (live app), `integration/` (discovery pipeline, imports, qualification, capability areas, evidence regressions, worker processes), `fixtures/` (synthetic source site, simulated AI provider) |
| `frontend/` | Next.js App Router UI (15 sections, 26 pages); `verify/` = verification harness (type check + esbuild bundle of the same pages); `e2e/` = TypeScript spec run by CI |
| `e2e/` | Python Playwright browser journeys and responsive/accessibility checks |
| `tools/` | `local_stack.py` (full local stack), `run_journeys.sh`, `fixture_site.py`, `fake_ai_provider.py` (SIMULATED), `docker_substitute/`, `secret_scan.py`, generators |
| `docs/` | Deployment (`DEPLOYMENT.md`), environment, data model and scoring, security, migrations, restore, connectors, import templates |
| `deploy/`, `.env.example` | Configuration examples (placeholders only) and the production compose override |
| `legacy/vecta-2.9.0/` | The original archive, retired (moved, not deleted) |
| `BASELINE_AUDIT.md`, `BRIEF_TRACEABILITY.md`, `BUILD_REPORT.md` | Audit, traceability, final report |

## Local setup

Locks: `backend/requirements.verified.txt` pins the exact versions this build was tested with. Generate the hashed locks where PyPI and npm are reachable (CI does this automatically until they are committed):

```
cd backend && uv pip compile requirements.in -c requirements.verified.txt --generate-hashes -o requirements.lock \
           && uv pip compile requirements-dev.in -c requirements.verified.txt --generate-hashes -o requirements-dev.lock
cd frontend && npm install && git add package-lock.json
```

Then:

```
export LOGIN_USERNAME=ops@wfc.local LOGIN_BOOTSTRAP_PASSWORD='<12+ chars, 3 classes>'
docker compose up --build        # db, migrate (alembic upgrade head), api, worker, web on :3000
```

Sign in once, change the password under **Settings**, then remove `LOGIN_BOOTSTRAP_PASSWORD`. Then: **Settings → Sources** to register the public sources the team is authorised to monitor; optionally set `SEARCH_PROVIDER`/`SEARCH_API_KEY` for authorised web search in relationship research; set a budget and lift the AI kill switch if an AI key is configured; **Discover** to search; open an opportunity and choose **Research relationships**. WFC data imports (Settings → WFC data imports) are optional.

Hosting on GitHub + Railway + Supabase: `docs/DEPLOY_RAILWAY_SUPABASE.md`. Netlify front end: `docs/DEPLOYMENT.md` §8.

Verification:

```
cd backend
pytest tests/domain                                                        # pure rules
WFC_TEST_PG="host=127.0.0.1 port=5432 user=atlas" pytest tests            # + PostgreSQL, live API, integration, worker processes
cd .. && PYTHON=python tools/run_journeys.sh e2e-artifacts               # clean local stack + browser journeys + responsive/a11y
tools/docker_substitute/run.sh docker-artifacts python                    # only where base images cannot be pulled
```

## Non-negotiables built into the code

- **One shared login.** One username and password gives access to the whole workspace, and every record is visible after sign-in. Company, region, country and service are reporting filters. Owners, relationship owners and contacts are descriptive records in the shared workspace.
- **Every API route requires the session.** Mutations also require the CSRF header. Responses are `Cache-Control: no-store`.
- **Claims need evidence.** Evidence is counted per announcement family. Reachability is not verification. Contradictions are kept.
- **Unknown is never zero.** Utilisation needs a compatible denominator. Currencies are never mixed. Revenue is never shown as contribution.
- **Scores are four separate, versioned, provisional assessments.** They are never a probability of winning.
- **AI is off until configured,** budget-reserved before every call, schema-validated, and never fed private WFC data.
- **Human authority.** Pricing, bookings, external messages and commitments always remain human actions. ATLAS never sends messages or outreach.
- **Titles are bound by evidence.** A title or organisation is attached to a person only by a source passage that binds
  them; otherwise it reads "not established". Records are never merged on a name alone (possible duplicates are reviewed
  and merges can be undone), and research reports what it read, what it could not, and whether it is complete.
- **People are evidence-based.** A person found by research is a candidate until someone confirms who they are; being named in a source is not decision-making authority; a public association is not a relationship; an introduction is available only with the introducer's confirmed willingness; a LinkedIn search link is not a contact. No win probabilities.
