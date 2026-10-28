# Acceptance matrix: VECTA Connect / ATLAS / DYNAMIC MARKET INTELLIGENCE for World Freight Company

Release **3.7.0-wfc.9** · 28 October 2026 · instruction of 28 Oct 2026 (eight items) on top of 3.6.0-wfc.8.

Each original requirement is linked to the screen where it is used, the data it needs, the calculation or decision,
the output, and the evidence that verifies it. Every row has one classification:

- **Implemented and verified**: built, and exercised by executed tests (PostgreSQL integration tests, browser journeys
  or rule tests) that pass in this release.
- **Implemented but not verified**: built and documented, but the check that would prove it in its real setting has not
  run here (named in the row).
- **Awaiting external data or access**: cannot be completed or shown without something only WFC, VECTA or a provider
  can supply (named in the row). Nothing is simulated in its place.
- **Not implemented**: not built (with the reason).

"Synthetic" means invented organisations and example domains. All business workflows below were verified on synthetic
data loaded through the same import and discovery paths WFC data will use; **no WFC data, no real public source and no
real AI provider has been used**. Simulated or scripted results are never presented as live results.

Test files are under `backend/tests/`; browser journeys under `e2e/`. Executed totals are in `BUILD_REPORT.md` §1.

## 1. The nine business workflows (instruction item 2; brief ¶7–24)

Every number asserted in `tests/integration/test_business_workflows.py` is computed in the test from the raw rows,
not by calling the code under test.

| # | Workflow | Screen | Data inputs | Calculation or decision | Output | Verification evidence | Classification |
|---|---|---|---|---|---|---|---|
| 1 | Airline representation: source discovery → evidence → qualified cargo opportunity → pipeline | Discovery, Review, Opportunity page, Opportunities (pipeline) | Registered public source; country search; extracted or reviewer-recorded claims; capabilities register | Tender identity, per-field evidence validation, freight relevance, status chronology, publication date; factual checks (existence, not expired, live status, capability, evidence reviewed) and commercial checks (eligibility, scope) kept apart; human approval before pursuit | Live cargo GSSA opportunity, `ready_for_review` → `approved_for_pursuit`, stages reviewing → qualified → pursuing with history; four separate prioritisation dimensions | `test_business_workflows::test_1_airline_representation_discovery_to_pipeline`; browser `test_05`–`test_09`, `test_e`, `test_h`–`test_k` | **Implemented and verified** (synthetic site, scripted/simulated extractor) |
| 1b | … the same against real notices and a real AI provider | as above | An authorised source list and an `ANTHROPIC_API_KEY` with a budget cap | — | Measured relevance, precision/recall, field accuracy, cost | Procedure: `tools/live_trial.py`; scripted-extractor measurements kept separate in `evidence/evaluation/` | **Awaiting external data or access** (key and authorised source: "Not available now") |
| 2 | Account growth: mandate and territory coverage → evidenced expansion gap → capability and contractual-rights checks | Capability areas › Account growth | agreements, capabilities, training_credentials, bookings imports | Territories where WFC holds verified, in-date capability for a service it already provides the airline under an in-force agreement; appointment rights (may extend / consent / prohibited), exclusivity, credential validity | Ranked candidates with blockers, unknowns, rank reason; opportunity with `appointment_rights`, `capability`, `territory_conflict` checks | `test_2_account_growth_…` (expired capability not actionable; prohibited rights blocked; booking evidence counted) | **Implemented and verified** (synthetic imports) |
| 3 | Forwarder sales: bookings and quotes → dormant/declining account or conversion issue → prioritised recommendation | Capability areas › Forwarder sales | bookings, quotes imports | Month vs previous month and same month last year; dormancy (90 days); conversion = won/(won+lost) over 90 days; lost-on-price share | Accounts ordered (needs review, dormant, volume) with rank reason and missing inputs; account-review opportunity with explained factors | `test_3_forwarder_sales_…` (−20%/−40% decline, 33.3% and 10% conversion, order Bravo, Alpha, Charlie) | **Implemented and verified** (synthetic imports) |
| 4 | Capacity and lanes: directional bookings and capacity → compatible utilisation/yield → sourced recommendation | Capability areas › Capacity and trade lanes | bookings, capacity imports | Directional lanes; utilisation only on bookable kg for the same period; trend vs the preceding period; yield per kg per currency; provisional thresholds (85% / 50% / ±10%) | Recommendation (add capacity / review allotment / monitor / insufficient data) with inputs, sources, thresholds, missing; opportunity scored on spare capacity and trend | `test_4_capacity_and_lanes_…` (90.5% utilisation, +20.67% trend, yield, 25% / −33.33% review, no-capacity lane = gap); browser `test_l` | **Implemented and verified** (synthetic imports) |
| 5 | Service and operations: exception → alert and task → resolution with retained history | Service Intelligence | exceptions import | One alert and one task per exception, idempotent on re-import; owner, acknowledge, resolve | History open → owner_changed → acknowledged → resolved; task closed; list ranked by severity then deadline with missing owner/deadline shown | `test_5_service_and_operations_…`; browser `test_10` | **Implemented and verified** (synthetic imports) |
| 6 | Trucking and gateways: station and connection data → cutoff feasibility → coverage recommendation | Capability areas › Trucking and gateways | stations, trucking, gateway_connections imports | Feeder must run on the ship date (checked first), arrive before the connection cutoff, connect within 2 days; unknown cutoff is unresolved, never feasible | Per station: coverage available (best option), insufficient data, or coverage gap; opportunity with a `feasibility` check | `test_6_trucking_…` (06:00 + 240 min vs 23:50 − 180 min feasible; Sunday-only feeder = gap; no feeder = gap) | **Implemented and verified** (synthetic imports). Defect fixed this release: a feeder not running that day was "insufficient data" when the cutoff was unknown |
| 7 | Outsourcing and training: verified demand → capability and valid credentials → qualified match | Capability areas › Outsourcing and training | Supported tenders (discovery or reviewer); capabilities, training_credentials, service_requirements imports | Live tenders only (open/revised, freight in scope, dated); match on verified capability, station, delivery date, every required credential current | Demand ranked by readiness then deadline with missing inputs; cancelled, historical, excluded or unverified records listed apart with why | `test_7_outsourcing_…` (live tender matched ready; cancelled tender excluded) | **Implemented and verified** (synthetic) |
| 8 | Technology and solutions: linked channel events → measurable friction → evidence-backed solution opportunity | Capability areas › Technology and solutions | channel_events, bookings, trucking imports | Booking funnel from linked sessions (≥5 quote-request sessions, booking rate < 20% = friction); ≥3 integration failures; adoption gaps; combined service | Ranked solution candidates with evidence counts, thresholds, rank reason; opportunity from a candidate | `test_8_technology_…` (6 sessions, 1 booked = 16.67%; 3 failures; unlinked channel = insufficient data) | **Implemented and verified** (synthetic imports) |
| 9 | Network development: coverage gap or sourced target → partner assessment / referral / acquisition research → reviewable recommendation | Network Development | agreements, capabilities imports; partners; linked signals | Derived gap = in-force mandate territory/service without verified capability; partner fit from supported claims only; acquisition research never ranked or valued | Coverage gaps recorded for review; candidates ranked by fit, evidence, status (provisional); referrals between WFC companies | `test_9_network_development_…`; browser `test_l` | **Implemented and verified** (synthetic) |
| 10 | Missing data produces explicit gaps, not zeros or confident recommendations | Every area | — | Not connected / stale detection per dataset | "Not connected" state, gaps listed, no recommendation without its inputs | `test_missing_data_gives_explicit_gaps_never_zero_or_confident_recommendations`; `test_missing_feeds_show_not_connected_never_zero` | **Implemented and verified** |
| 11 | Real WFC figures in the eight data-driven areas | as above | WFC exports or system access | — | — | — | **Awaiting external data or access** (WFC data; see `docs/CONNECTORS_AND_DATASETS.md`) |

## 2. Data onboarding (instruction item 3; brief ¶28–29, ¶32)

| Requirement | Screen | Evidence | Classification |
|---|---|---|---|
| Upload, mapping, validation, preview, commit, reconciliation, duplicates, corrections, reversal for every dataset (19) | Data Sources and Imports | `tests/integration/test_data_onboarding.py` (one case per dataset; a coverage test fails if a contract has no case); browser `test_03`, `test_04`, `test_l` | **Implemented and verified**. Defect fixed: a corrected airline name was previewed as an update but not applied |
| Documentation reconciled with the code; templates; required-field explanations | Import screen (rules list, field table); `docs/import-templates/` | `docs/CONNECTORS_AND_DATASETS.md` and `FIELDS.md` generated from the contracts; `tests/unit/test_import_docs.py` fails on drift | **Implemented and verified** |
| Source, period, currency, units and freshness shown throughout; refresh requirements labelled | Every area ("Data used"), insights, import screen | `_loaded` returns source of truth and refresh requirement; browser `test_l` | **Implemented and verified** |
| Authorised CSV/XLSX imports sufficient for the workflows while live APIs are unavailable | — | Section 1 tests load all inputs through imports | **Implemented and verified** |

## 3. External intelligence (instruction item 4; brief ¶25–27, ¶30)

| Requirement | Evidence | Classification |
|---|---|---|
| Register an authorised source; server-side AI provider under a capped budget | Source registration, budget, kill switch, per-run ceiling: browser `test_02`, `test_05`, `test_f`; `test_many_small_calls_cannot_exceed_the_run_ceiling` | **Implemented and verified** (simulated provider) |
| Country discovery against original notices compared with manual review; relevance, precision/recall, field accuracy, unsupported claims, duplicates, incomplete reading, failures, actual cost | `tools/live_trial.py` writes `comparison.csv` and `report.md` for a reviewer | **Awaiting external data or access**: no API key and no authorised source supplied |
| Scripted, reconstructed-document and real-provider results kept separate; no claim of comprehensive coverage | `backend/evaluation/` splits (tuning, genuine, held-out 2–7), `evidence/evaluation/`; worldwide searches state what was searched and not read (`test_d`) | **Implemented and verified** (scripted extractor only; there are no real-provider results) |
| Single-country, multiple-country, regional, worldwide discovery | `test_relevant_links_beyond_the_limit_are_queued_and_resumed` × 4 modes; browser `test_06`, `test_d` | **Implemented and verified** |

## 4. Live WFC adapters (instruction item 5; brief ¶32)

| Adapter | Classification | Exact information required |
|---|---|---|
| Booking / quoting | **Awaiting external data or access** | `docs/CONNECTORS_AND_DATASETS.md` "What is needed" (system, API docs, change feed, field dictionary, test credential, authorisation) |
| Schedules / capacity | **Awaiting external data or access** | same document |
| Operational exceptions | **Awaiting external data or access** | same document |
| Channel analytics | **Awaiting external data or access** | same document |

All four show **Not connected**; no endpoint has been invented. The import path provides the required guarantees today
(idempotent keys, reconciliation, freshness, reversal).

## 5. Qualification and prioritisation (instruction item 6; brief ¶3, ¶30, ¶38)

| Requirement | Evidence | Classification |
|---|---|---|
| Factual eligibility, commercial attractiveness, evidence confidence and readiness kept distinguishable | `test_dimensions_are_never_combined`, `test_scores_are_separate_dimensions_and_never_probabilities`; `test_factual_checks_cannot_be_overridden` (every factual check) | **Implemented and verified** |
| Why each recommendation ranks where it does, missing inputs, evidence; weights labelled provisional | rank, rank_reason (with the provisional rule), missing on every ordered list in all nine areas; prioritisation factors with reasons; `test_business_workflows` assertions; browser `test_l` | **Implemented and verified** |
| Historical, excluded, contradictory or unsupported records never qualified live | `tests/integration/test_qualified_live_guard.py` (control qualifies; AI-unreviewed, historical, passenger-only, self-contradicting, cancelled-after-approval, stale data, no-action recommendations, prohibited rights do not; cross-area invariant query) | **Implemented and verified** |
| Cancellation, reopening, publication-date and status-freshness protections preserved | `test_status_chronology*`, `test_status_freshness*`, `test_revision_then_cancellation_keeps_history`; browser `test_j`, `test_k`; full suite passing | **Implemented and verified** |
| Weights calibrated on WFC outcomes | — | **Awaiting external data or access** (WFC won/lost history) |

## 6. Access, identity and deployment (instruction items 1, 7; brief ¶1, ¶33)

| Requirement | Evidence | Classification |
|---|---|---|
| VECTA Connect / ATLAS / DYNAMIC MARKET INTELLIGENCE; Poppins; existing VECTA design; WFC as configured customer | browser `test_01`, responsive sweep; export header test | **Implemented and verified** |
| One shared username and password | `test_http_security.py`, browser `test_01`, `test_12`, `test_g` | **Implemented and verified** |
| Brief ¶33 "configurable permissions" | Superseded by the later single-login instruction (recorded in `BRIEF_TRACEABILITY.md` ¶33) | **Not implemented**, by instruction |
| Audit history, scanning schedules, AI usage controls (rest of ¶33) | audit tests; `test_11`; budget and kill-switch tests | **Implemented and verified** |
| All nine capability areas | `test_every_area_produces_meaningful_output`, section 1; browser `test_10` | **Implemented and verified** |
| Netlify as the front-end host, with the API, worker and PostgreSQL elsewhere | `netlify.toml`, `deploy/netlify/preflight.mjs`, `docs/DEPLOYMENT.md` §8; signed-proxy check `test_signed_proxy_requirement` | **Implemented but not verified**: no Netlify site or API host supplied; not deployed |
| Committed `package-lock.json`, `requirements.lock`, `requirements-dev.lock`; clean install; release gate | CI `commit-locks` workflow; `tools/check_locks.sh` | **Awaiting external data or access**: package registries unreachable here and no repository (`owner/repo`) supplied to run the workflow |
| Official PostgreSQL, API, worker and real Next.js production stack; authenticated journeys incl. production configuration, migrations, backup/restore, worker recovery, budget enforcement | Journeys executed on the local process stack (real PostgreSQL, API, worker processes; pages bundled by the verification harness, not `next build`): `run_journeys.sh` results in `BUILD_REPORT.md` §1 | **Implemented but not verified** on the official images and `next start` (needs registries or CI) |
| Backup and restore | `docs/RESTORE_RUNBOOK.md`; restore rehearsal in the clean verification (`BUILD_REPORT.md` §1) | **Implemented and verified** on local PostgreSQL; production rehearsal outstanding |
