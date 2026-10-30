# Amendment checklist — release 4.7.0-wfc.18 (30 October 2026)

Legend: **PASSED** — executed here and passed · **FAILED** — executed and failed · **SIMULATED** — passed on fixture pages, a scripted
search stand-in and a scripted extractor (no real public source) · **NOT EXECUTED** — could not be run in this environment (reason given).

| # | Requirement | Check | Result |
|---|---|---|---|
| 1 | Jane Smith / John Brown: John's address never assigned to Jane | `tests/domain/test_email_attribution.py::test_jane_smith_john_brown…`; PostgreSQL re-check and research run in `test_email_attribution_recheck…` | PASSED (rule) · SIMULATED (pipeline) |
| 1 | Explicit statement, labelled contact block, structured row, own-name association | domain tests: explicit statement, contact blocks, table rows, name forms | PASSED |
| 1 | Shared / departmental mailboxes kept apart from personal addresses | `test_shared_and_departmental_mailboxes…` | PASSED |
| 1 | Ambiguous addresses unassigned / pending review | `test_two_people_one_address…` | PASSED |
| 1 | Multiple people, multiple e-mails, tables, neighbouring blocks, third-party press contacts | 8 domain tests | PASSED |
| 1 | Re-check of addresses created under the defective rule; evidence kept; uncertain flagged | `test_email_attribution_recheck…` (2 examined, 2 flagged, evidence rows kept, idempotent); runs once at API start | PASSED (SIMULATED data) |
| 2 | Persisted queue replaces six-organisation slicing | `research_stage_items`; `test_more_than_six_organisations…` (9 organisations, 3 runs) | PASSED (SIMULATED pages) |
| 2 | Total / attempted / completed / failed / pending per stage | same test; stage `counts` and `progress` | PASSED |
| 2 | Continue with pending, never the first six again | same test: run 2 searches only the 3 pending | PASSED |
| 2 | No stage "done" while work remains | same test + journey S | PASSED |
| 3 | Complete airport dataset loaded at deployment / verified import package | `airports` deployment step; `app.airports_cli package / verify / load --package`; tampered package refused (`test_import_package…`) | PASSED (tooling) · **NOT EXECUTED** with the real file — no outbound access; no package included |
| 3 | Show source, version, refresh date, total records, seed vs full | `test_status_names_the_directory_in_use…`; Settings → Data sources → Airport directory (journey T2) | PASSED |
| 3 | Selection by name, city, country, IATA, ICAO, no-IATA, multiple, all-airports scopes | `test_selection_by_name_city_country…` on the dataset's own CSV format | PASSED (8-row sample; full file NOT EXECUTED) |
| 3 | Directory inclusion is not cargo evidence | `test_directory_inclusion_is_never_evidence…` | PASSED |
| 4 | Controlled public-source demonstration in a new market | `tools/public_source_demo.py` (queries, sources, gaps, costs, review sheet) | **NOT EXECUTED** — no outbound access, no search connector key, no extractor key in this environment |
| 5 | Four summaries, priority table, recent changes kept; analytics collapsed | journey S/T, `app/page.tsx` | PASSED |
| 5 | Every summary opens matching records | `test_dashboard_summaries_open_exactly_their_records…` (3 filter scopes); journey T1 (clicks through) | PASSED |
| 5 | Every opportunity has a clear next action | same test | PASSED |
| 5 | Research completeness apart from relevance; fuller profile / e-mail does not raise priority | same test (order unchanged after deep research) | PASSED |
| 6 | Discovery and deep research update the same records; continuation creates no duplicates | `test_staged_research…`, `test_company_correction…` | PASSED (SIMULATED) |
| 6 | Confirmed corrections survive further research | website correction and confirmed identity tests | PASSED |
| 6 | Changed evidence prompts rechecking | website "Changed evidence — re-check"; person e-mail `recheck` | PASSED |
| 6 | Consistency across Relationships, company page and opportunity | `test_company_correction…` compares the three views | PASSED |
| 7 | Database and migration tests | PostgreSQL 16 suite incl. `wfc_0017` schema revision | see counts below |
| 7 | Authenticated browser tests | Playwright journeys on the local stack with the shared login | see counts below |
| 7 | Against the real production stack | — | **NOT EXECUTED** — no deployment, keys or network reachable from here |

## Counts

| Check | Result |
|---|---|
| Backend suite on PostgreSQL 16 (incl. migrations `wfc_0001`–`wfc_0017`, schema revision, new tests) | **1398 passed**, 0 failed |
| New tests this release | 8 e-mail attribution (domain); 4 airport directory; 4 deep-research integration (queue >6 orgs, e-mail re-check and corrections, Dashboard summaries and ranking, company correction and consistency) |
| Authenticated browser journeys (Playwright, shared login, local stack) | **35 passed**, 0 failed — journey S extended with T1–T4 |
| Frontend type check, lint, ESLint | passed, 0 findings |
| `tools/public_source_demo.py` end-to-end smoke run | passed — **SIMULATED** (local stack: fixture pages, scripted search, scripted extractor); recorded cost USD 0.00 because the extractor is a stub |
| Real public-source demonstration | **NOT EXECUTED** (no outbound access, no search or extractor key) |
| Full OurAirports file loaded | **NOT EXECUTED** (no outbound access); tooling and package verification tested |
| Production stack | **NOT EXECUTED** |

## Issues found and fixed during verification

* A pre-existing timing flake: `test_a_supplied_station_list…` built its workbook twice; an embedded creation time could differ by a second, so the
  duplicate-import check did not fire. The test now builds the file once (the check itself was correct).
* The smoke run showed a person's address listed among company e-mails with a departmental label ("cargo") and an airport recorded both as a station
  and as "served from elsewhere". Fixed: personal addresses are labelled **personal**; "served" is never recorded beside a station, office or hub.
* A local stack left running from the first smoke run (stopped with the wrong logs directory) served part of one journey run. That run was
  discarded; the journeys were re-run on a clean stack (35 passed), and `tools/local_stack.py up` now refuses to start when its ports are taken.

