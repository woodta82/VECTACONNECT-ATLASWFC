# Regression and operational report — release 4.9.0-wfc.20 (30 October 2026)

Legend: **PASSED** — executed in the build session and passed · **SIMULATED** — passed on invented fixture pages with a scripted search
stand-in and scripted extractor · **NOT EXECUTED** — could not be run from the build session (reason given). Nothing below is a deployment.

## Build-session limits (checked on 30 Oct 2026)

* No outbound network: the airport publisher, Brave Search, public websites, npm, PyPI and Docker registries all refuse the connection;
  the Docker daemon is not running. The real Next.js build cannot be produced here (it is built and tested by the repository's GitHub CI).
* No hosting: deployment is done from the team's own hosting account; no claude.ai connector is used.
* No search or extractor key for the application.

## 1. Contact involvement

| Case (exact text tested) | Expected | Result | Test |
|---|---|---|---|
| "Press contact: Maria Lopez, Example PR Agency, maria.lopez@examplepr.example, +370 5 000 000." | press / media contact of Example PR Agency; external contact; not a commercial contact | PASSED (rule) · PASSED on PostgreSQL with the fixture page (SIMULATED page) | `test_third_party_press_contact_is_not_a_commercial_contact`, `test_a_third_party_press_contact_is_kept_as_an_external_contact…` |
| "For media enquiries contact Laura Kim, Account Director, Bright Comms Ltd." | press contact (agency) | PASSED | same |
| "Media contact: Anna Weiss, Communications Manager, Nemunas Cargo Services UAB." | press contact (own communications role) | PASSED | `test_the_companys_own_communications_officer…` |
| "For more information, contact Tomas Petrauskas, Head of Cargo Sales at Nemunas Cargo Services UAB." | employee — a commercial role is never a press contact | PASSED | same |
| Appointed GSSA's managing director named in an appointment | appointed representative | PASSED | `test_employee_representative_adviser_unresolved` |
| Legal adviser to the buyer | external adviser | PASSED | same |
| Coverage with only a press contact linked | `none` (view and service) | PASSED | integration test |
| Research file | press contact absent from commercial people and gaps; listed under external contacts with role | PASSED | integration test; browser journey V2 |
| Discovery people ranking | press contacts and advisers score 0, marked excluded, kept | PASSED (code path, existing discovery tests) | `contact_discovery` |
| Re-check of candidates recorded before 4.9.0 | press contact re-classified, link moved to external contact, evidence note, audit row, idempotent | PASSED | integration test |
| A person's correction | survives later research and the re-check | PASSED | integration test |

## 2. Deployment — NOT EXECUTED

`tools/deploy_check.py` (version, login, persistence across restart, full airport directory, entries without IATA and ICAO search,
multi-airport country scope, budget, visible failures, browser) was validated end to end against the LOCAL stack only — that is a
check of the script, not of a deployment. Its expected outcome there: airports **FAILED** (the local stack has only the bundled seed),
backup **NOT CHECKED**. See "Script validation" below.

## 3. Full airport directory — NOT EXECUTED

Loads in the `api` pre-deploy step (`docs/DEPLOY_RAILWAY_SUPABASE.md`); verified by `deploy_check.py verify`.

## 4–5. Real public-source pilot and manual accuracy check — NOT EXECUTED

`tools/pilot.py` (companies and people without a tender; commercial opportunity from a market development; public tender with status
and deadline for verification) and its review sheet were validated against the local stack only (SIMULATED). Steps: `docs/PILOT_RUNBOOK_4.9.0.md`.

## 6. The user journey (browser, local stack)

| Step | Result |
|---|---|
| Search a market and an airport (Lithuania, Kaunas KUN) → results → company → research file | PASSED (journey S, SIMULATED pages) |
| Add pages to an opportunity in the browser → pending work shown → Continue research reads them | PASSED (journey V1) |
| Relevance, people, external contacts (press contact never a commercial contact) | PASSED (journey V2) |
| Contact routes: current only; the withdrawn address shown as not current | PASSED (journey V3) |
| Record the next action → shown on the Dashboard | PASSED (journey V4) |
| Continuation without duplicates (people, companies) | PASSED (journey V5) |
| Retry of failed organisations, corrections surviving research | PASSED (PostgreSQL integration tests, 4.8.0) |
| Cancellation updates the opportunity | PASSED (journeys K and M) |
| Historical e-mails never shown as current contact actions | PASSED (journey V3; 4.8.0 tests) |

The browser journeys ran against the real API, worker, migrations and PostgreSQL 16 in the build session; the web pages were served by
the verification bundle (`frontend/verify`), not by `next start`.

## Verification counts

| Check | Result | Kind |
|---|---|---|
| Backend suite on PostgreSQL 16 (migrations `wfc_0001`–`wfc_0019`, schema revision, all tests) | **1428 passed**, 0 failed | executed in the build session, final code |
| Browser journeys (Playwright, shared login, real API + worker + migrations + PostgreSQL; pages from the verification bundle) | **35 passed**, 0 failed | executed in the build session, local stack, final code |
| Frontend type check, lint, ESLint | passed, 0 findings | executed |
| `tools/deploy_check.py prepare` → API and worker restarted → `verify --browser` | ran end to end: version, login, persistence across restart and failure visibility PASSED; airports FAILED (seed only — correct); budget FAILED (not set — correct); browser FAILED (directory not full — correct); backup NOT CHECKED | script validation on the local stack — **not a deployment** |
| `tools/pilot.py` (three workflows) | ran end to end; no results (the local search stand-in does not index these queries; AI kill switch on) | script validation on the local stack, **SIMULATED** |
| Deployment, full airport directory, real-source pilot, manual accuracy check, production browser checks | **NOT EXECUTED** | no outbound network in the build session; deployment from the team's own hosting account (no connector) |

### Found and fixed during verification

* Journey S's new step filled the "Page URL" field while the panel was still reloading from the previous addition, so the field was
  cleared and the button stayed disabled (a test race, not a product fault). The step now reloads the page before each addition.
* With the longer journey S, later journeys exceeded the API's per-address rate limit (300 requests/minute) on the local stack — one
  address replays many users' clicks per minute. The limit is now configurable (`RATE_LIMIT_PER_MINUTE`, default unchanged at 300);
  only the local test stack raises it.

