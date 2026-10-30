# Regression report — release 4.8.0-wfc.19 (30 October 2026)

Legend: **PASSED** — executed here and passed · **SIMULATED** — passed on invented fixture pages with a scripted search stand-in and
scripted extractor, not on real sources · **NOT EXECUTED** — could not be run in this environment (reason given).

The two examples the instruction refers to ("the external-supplier example above" and the "Do not use … no longer valid" example) were not
included in the message. They were reconstructed from the description; the exact test text is quoted below. If the originals differ, they
should be added verbatim as further cases.

## 1. E-mail ownership needs explicit evidence

| Case (exact text tested) | Expected | Result | Test |
|---|---|---|---|
| **External supplier.** "Jane Smith is Head of Cargo at Nemunas Cargo Services UAB. Our booking platform is provided by Example Cargo Systems Ltd; for technical support contact their account manager at jane.smith@examplecargosystems.example." | Not Jane's; a supplier contact pending review; the matching name recorded as supporting evidence only | PASSED | `test_external_supplier_example_a_matching_local_part_is_not_ownership` |
| A matching local part with nothing else: "Our cargo team can be reached at jane.smith@nemunascargo.example for bookings." | Candidate pending review ("nothing on the page states whose address it is") | PASSED | `test_a_matching_local_part_alone_is_pending_review_never_assigned` |
| The same address with an explicit statement: "Jane Smith, Head of Cargo: jane.smith@…" | Jane's; basis explicit statement; name match as supporting evidence | PASSED | same |
| Initials shared by two people, with structure: "John Smith, Head of Sales. E-mail: jsmith@…" (Jane Smith also known) | John's (the structure decides, not the name) | PASSED | `test_same_name_people_and_initials` |
| Initials shared by two people, no structure: "Write to jsmith@…" | Neither; both candidates | PASSED | same |
| A namesake at a partner: "Jane Smith (Baltic Partner Air): jane.smith@balticpartner.example." | Not assigned; "investigate the relationship" | PASSED | same |
| Two people named Jane Smith (Nemunas Cargo Services, Amber Example Air). "Jane Smith, Head of Cargo: write to jsmith@nemunascargo.example for bookings." then "Jane Smith, Head of Cargo at Nemunas Cargo Services UAB, can be reached at jsmith@nemunascargo.example." | First: neither (candidate, "another person named Jane Smith"); second: Nemunas's Jane only | PASSED (PostgreSQL pipeline). **Found and fixed:** the check changed a shared result in place, so the outcome depended on processing order | `test_two_people_of_the_same_name_at_different_organisations` |
| Domain mismatch explained: subsidiary / appointed agent / adviser | Assigned, the explanation recorded as supporting evidence | PASSED | `test_a_domain_mismatch_prompts_investigation…` |
| Domain mismatch unexplained: "Peter Ozols, Sales Manager: p.ozols@gmail.example." | Pending review ("investigate") — not rejected | PASSED | same |
| Partner's dispatcher: "…its partner company Example Road Feeder SIA. Contact their dispatcher, Ivars Liepa, at ivars.liepa@roadfeeder.example." | Not a person at the company | PASSED | `test_partner_and_third_party_contacts` |
| Third-party press contact (4.7.0 cases) | Nobody at the company | PASSED | `test_third_party_press_contacts…` |
| Jane Smith / John Brown (4.7.0 case) | John's address never Jane's | PASSED | `test_jane_smith_john_brown…` |

## 2. Invalid, historical and withdrawn contact details

| Case (exact text tested) | Expected | Result | Test |
|---|---|---|---|
| **"Do not use"**: "John Brown, Sales Manager, Nemunas Cargo Services UAB. Do not use john.brown@nemunascargo.example — this address is no longer valid. Please write to sales@nemunascargo.example instead." | john.brown@ historical (never a current route, kept as history); sales@ current shared mailbox | PASSED | `test_invalid_example_do_not_use_no_longer_valid` |
| "… (this address is no longer monitored)" | historical | PASSED | `test_obsolete_replaced_withdrawn_and_former_employee_wording` |
| "His old address tomas.p@… was replaced by tp@…" | old historical; replacement current | PASSED | same |
| "Tomas Petrauskas has left the company. … former Head of Cargo Sales: tp@…" | historical (former employee) | PASSED | same |
| Pipeline on PostgreSQL: one page lists tomas.petrauskas@ as current, another says "Do not use … no longer valid. Please write to tp@… instead" | tp@ assigned (named replacement); old address in history, evidence note kept; conflict never assigned | PASSED (SIMULATED pages) | `test_withdrawn_and_conflicting_contact_details…` |
| Company mailbox listed on one page, "no longer monitored" on another | Contact status **Sources conflict — review before use**, conflict note recorded | PASSED (SIMULATED pages) | same |
| Publication ≠ deliverability | Every published address labelled "deliverability not verified" | PASSED | same |
| Re-check of previously assigned addresses | Withdrawn → historical; unconfirmed → under review; verified kept (note added); evidence notes and audit row written; idempotent | PASSED | same, and `test_email_attribution_recheck…` |

## 3. Truthful stage outcomes and retry

| Case | Expected | Result | Test |
|---|---|---|---|
| One organisation's official site cannot be read (connection reset) | Stage **Complete with unresolved failures**, never "done"; website **source inaccessible**, never "not found after research" | PASSED (SIMULATED pages) | `test_failures_are_never_reported_as_plain_done…` |
| Counts consistent | Research file, company page, Dashboard show the same state and "N completed, N failed, N pending" | PASSED | same |
| Continue | Leaves the failure alone; no item re-attempted | PASSED | same |
| Retry failed (API) | Only the failed organisation re-attempted; its failed page re-read; blocked stages re-run; no page recorded twice; nothing completed repeated; afterwards state Complete, retry returns 409 | PASSED | same |
| More than six organisations | Pending work continues across runs, not the first six again | PASSED | `test_more_than_six_organisations…` |
| **Found during this release:** a page a person added after research was complete was never read while the state said "complete" | Queued pages count as pending work; Continue reads them | FIXED, PASSED | `test_a_page_added_after_research_is_complete…` |

## 4. Airport directory

| Check | Result |
|---|---|
| Source, version, refresh date, record counts shown; seed / partial / full | PASSED (`test_status_names_the_directory_in_use…`) |
| Search by name, city, country (code and name), IATA, ICAO; airports without IATA; multiple airports; country / region / worldwide scopes | PASSED on the dataset's own CSV format (8-row sample) |
| Selection beyond the bundled seed | PASSED (`test_selection_reaches_airports_beyond_the_bundled_seed`) |
| Download failure: honest status, failed attempt recorded and shown, deployment continues; readiness reports `airport_directory.full: false` | PASSED (`test_a_failed_download_leaves_an_honest_status…`) |
| Verified import package; tampered package refused | PASSED |
| **Full dataset loaded in a deployment with publisher access** | **NOT EXECUTED** — this environment cannot reach the publisher (HTTP CONNECT refused); no package could be built here |

## 5. Research quality with real sources

| Check | Result |
|---|---|
| Capped demonstration in a new cargo market with the configured search and extraction services; manual comparison against original sources; incorrect associations, missed information, failures and costs | **NOT EXECUTED** — no outbound access to public websites or the search provider, and no application search or extractor key in this environment |
| `tools/public_source_demo.py` end to end (now requires `--inputs REAL|SIMULATED`; report has separate sections for failures, incorrect associations, missed information and costs) | PASSED on the local stack — **SIMULATED** (`docs/samples/public-source-demo-SIMULATED-smoke/`) |

## 6. Verification runs

| Check | Result |
|---|---|
| Backend suite on PostgreSQL 16 (migrations `wfc_0001`–`wfc_0018`, schema revision, all new tests) | **1419 passed**, 0 failed — independently executed here, final code |
| Authenticated browser journeys (Playwright, shared login, local stack) | **35 passed**, 0 failed — independently executed here, clean stack, final code |
| Frontend type check, lint, ESLint | passed, 0 findings |
| `tools/public_source_demo.py --inputs SIMULATED` end to end + screenshots U1–U4 | passed — **SIMULATED** (local stack, fixture pages, scripted search and extractor; cost USD 0.00 because the extractor is a stub) |
| Full airport dataset in a deployment with publisher access | **NOT EXECUTED** — no publisher access from this environment |
| Real-source demonstration with manual comparison | **NOT EXECUTED** — no outbound access, no search or extractor key |
| Database and browser checks against the production stack | **NOT EXECUTED** — no production deployment reachable from here |

### Found and fixed during this release's verification

* Pages added to an opportunity after its research was complete were never read while the state said "complete" (found in the smoke run).
* The same-name check changed a result shared by both namesakes, so the outcome depended on processing order (found by the new test).
* A local test host (an IP address) made every address look like it was on a foreign domain; IP and dot-less hosts are now excluded from the domain check.

### Observed, not fixed in this release

* A third-party press contact named on a company page (Maria Lopez in the fixture) is still listed among the opportunity's research
  candidates with "title not bound". Her address is correctly not assigned to anyone, but she should not appear as a candidate; this belongs
  to the people-extraction step and is left for the next release rather than changed without its own tests.

