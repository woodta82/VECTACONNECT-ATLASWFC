# Schema ownership and migrations

## Rules
- **Alembic is the only schema owner.** The application never runs `create_all()` or `ALTER TABLE` at startup. Startup writes data only: the credential bootstrap, the connector register and scoring model versions, all idempotent.
- Lineage `wfc` starts at `wfc_0001`, which builds the **complete** schema on an **empty** database by executing `migrations/sql/wfc_0001_schema.sql`. The PostgreSQL test suite applies that same file.
- `wfc_0001` **refuses** to run on a database that already has tables. It never stamps an arbitrary head.
- Destructive changes use expand/contract across releases: add the new structure, dual-write, backfill, switch reads, then remove the old structure in a later release. Each step has its own restore plan. Downgrade is not a data-recovery strategy; restore from backup (`RESTORE_RUNBOOK.md`).

## Clean install
```
ENVIRONMENT=staging DATABASE_URL=postgresql+psycopg://… alembic upgrade head
psql … -Atc "SELECT value FROM schema_meta WHERE key='revision'"   # -> wfc_0001
```
`/health/ready` returns 503 until the revision matches the release's expected revision.

Evidence in this build (Alembic 1.20.1, SQLAlchemy 2.0.55, psycopg 3.3.6, PostgreSQL 16.15):
- `alembic upgrade head` on an empty database exits 0, recording `alembic_version = wfc_0001` and creating 73 tables (72 + `alembic_version`).
- Re-running it is a no-op (exit 0).
- On a database containing one table it exits 1 with "wfc_0001 requires an empty database; found 1 existing table(s)".

Constraints, functions and triggers are verified by `tests/sql/test_pg_schema_and_concurrency.py`.

## Existing VECTA data: separate adoption path (not a migration)
The WFC instance is a **fresh, isolated database**. VECTA 2.9.0 data is never migrated in place, never stamped, and sports enum values are never reinterpreted as freight categories. If any legacy material is wanted:
1. Restore a copy of the legacy database to a scratch server. Never use production.
2. Export the needed rows to CSV with an explicit query per dataset, mapping fields to the WFC import contracts (`docs/CONNECTORS_AND_DATASETS.md`).
3. Run each file through **Data Sources and Imports**: dry run, review the quarantine, then commit. Every row gets provenance and is reversible.
4. Compare row counts and reconciliation totals against the export, and keep the comparison with the import job.

Supported upgrade rehearsal for later revisions: restore last production backup to staging → `alembic upgrade head` → run `tests/sql` against it → compare per-table row counts before and after → keep the report.

## Later revisions

**Release 4.1.0-wfc.11 adds `wfc_0012`** (complete, evidence-backed relationship research; additive and idempotent).
Upgrade from 4.0.0-wfc.10: back up, deploy the new images, run `alembic upgrade head` (the `migrate` service does this),
then check `/health/ready` reports `wfc_0015`. No worker job is queued. From an earlier release, apply each revision below
in order (`alembic upgrade head` does this).

### What wfc_0012 does to existing data (migration summary)

| Existing data | After the upgrade |
|---|---|
| People with a recorded title | Kept unchanged. Each title also becomes an evidence-backed role row marked "recorded before the 28 Oct 2026 evidence rules", with no passage attached, so it is never mistaken for a sourced binding. Its affiliation is "works at the organisation" only when an organisation was recorded with it |
| People who share a name | Kept. Every pair whose organisation is unknown on at least one side, or differs, becomes a **possible duplicate** for review. **Nothing is merged** |
| Earlier research runs | Kept; their outcome is recorded as **incomplete** (they read only the opportunity's documents and fixed company-page addresses), never as "no people found" |
| Evidence, relationships, routes, engagements, opportunities, history | Unchanged |

New: organisation research pages (`newsroom_url`, `leadership_url`); `research_documents` (every document or page research
read, skipped or could not fetch, with sections read by the rules and by the AI extractor); research outcome, coverage and
searches on each run; evidence of an organisation binding and evidence from research documents; `person_roles`;
`people.merged_into_id`; `person_duplicate_candidates`; `person_merges` (every moved row listed, so a merge can be undone).
The views `person_state` and `opportunity_relationship_coverage` no longer count merged records. Re-running the file
changes nothing (`tests/sql/test_migration_0012.py`).

**Release 4.0.0-wfc.10 adds `wfc_0011`** (relationship intelligence; additive and idempotent). Upgrade from
3.6.0-wfc.8 or 3.7.0-wfc.9: back up, deploy the new images, run `alembic upgrade head` (the `migrate` service does this),
then check `/health/ready` reports `wfc_0011`. No worker job is queued; nothing needs re-checking. An installation on an
earlier release follows the steps of each revision below, in order.

### What wfc_0011 does to existing data (migration summary)

| Existing data | After the upgrade |
|---|---|
| Opportunities | All kept, with their evidence, checks and history. New `record_type`: `commercial` when the opportunity came from WFC's own records (`origin_ref`), otherwise `tender`. New `progress` from the earlier stage: new → New; reviewing, qualified → Reviewing; pursuing, proposal, negotiation → Pursuing; deferred → On hold; won, lost, expired → Closed (with that word kept as the closed reason). The earlier `commercial_stage` value and its history stay unchanged |
| Opportunity owners | The owner's name is copied to the new descriptive `owner_label`; the link to the person record is kept |
| Contacts imported from WFC relationship records | Kept; marked `origin = import` and treated as identity confirmed, with that basis recorded ("Imported from WFC relationship records before the 28 Oct 2026 upgrade") |
| Contacts with recorded engagements | Kept; one existing-relationship record is created whose basis is that history ("N engagement(s), latest YYYY-MM-DD"), so they show as existing relationships |
| Contacts added by hand | Kept; they are research candidates until a person confirms them (nothing is assumed) |
| Internal people (WFC staff) | Kept; never shown as research targets |
| Engagements | All kept; new optional fields: recorded by, outcome, next step |
| Signals, documents, claims, imports, audit | Unchanged |

New tables: `opportunity_notes`, `person_evidence`, `opportunity_people`, `person_relationships`, `introduction_routes`,
`relationship_research_runs`; views `person_state` and `opportunity_relationship_coverage`. Re-running the file changes
nothing (`tests/sql/test_migration_0011.py`).

| Revision | File | Contents |
|---|---|---|
| `wfc_0002` | `sql/wfc_0002_directive.sql` | Directive of 26 Oct 2026: discovery, sources, schedules, tender identity, per-field claims, review workflow, capability areas, import datasets. |
| `wfc_0004` | `sql/wfc_0004_amendments.sql` then `sql/wfc_0004_legacy_deadlines.sql` | Amendments of 26 Oct 2026, additive: `read_progress` and status `incomplete` (complete reading in sections; long documents an earlier version marked read become `incomplete`); claim-field support `review_required`; `status_contradiction`; `discovery_link_queue`; job type `deadline_revalidation`. The second file (idempotent) takes every legacy deadline out of "exact" status — 00:00 UTC or local midnight becomes date-only, any other time a local time with the recorded zone as an assumption — and queues one revalidation job when there is anything to revalidate. |
| `wfc_0012` | `sql/wfc_0012_relationship_research.sql` | 28 Oct 2026 (second continuation: complete, evidence-backed relationship research), additive and idempotent. Research documents and their sectioned, resumable reading; research outcome, coverage and searches; organisation research pages; evidence binding a person to an organisation; evidence-backed roles (current, former, incoming; affiliation); possible duplicates and reversible merges. Carries existing values over as summarised above. |
| `wfc_0013` | `sql/wfc_0013_open_market_relationships.sql` | 29 Oct 2026 (relationships to the ATLAS v1.0 parameters, open-market discovery), additive and idempotent. People: stakeholder type, decision authority, posture, judgement basis, key interests, strategic account, capability area (defaults: not judged). Engagements: `no_response` outcome, more kinds, direction (existing rows: outbound). New tables: contact discoveries and their people (relevance), outreach drafts. Research documents may belong to a discovery instead of an opportunity. Existing values are kept. |
| `wfc_0015` | `sql/wfc_0015_company_intelligence.sql` | 29 Oct 2026 (research purposes; company intelligence; supplied data), additive and idempotent. Organisation kinds extended (handler, technology provider, charter broker, integrator, authority); organisation profile columns (origin, description, services, locations, parent group, airport, carrier type, supplied/verified/researched timestamps, capability areas). New tables `organisation_contacts`, `organisation_evidence`, `organisation_relationships`, `supplied_imports`, `supplied_rows`, `discovery_organisations`. `discovery_searches.purpose` ('opportunities' default, 'market') and `brief`; `contact_discoveries.purpose` ('people' default, 'companies'), `brief_text`, `airport_iata`, `organisation_kinds`, outcomes `companies_found` / `no_companies_found`. `opportunities.origin_organisation_id`, `origin_interpretation`. Existing organisations become origin 'manual'; nothing supplied or verified; existing discoveries and searches keep their default purposes. |
| `wfc_0014` | `sql/wfc_0014_open_web_discovery.sql` | 29 Oct 2026 (open-web discovery as the default), additive and idempotent. Source type `web_search` and the built-in, enabled "Open web (authorised search)" source (inserted once; `sources.builtin`). Per-document publisher family and authority and the access restriction on `source_documents`. Run outcomes `search_not_configured` and `search_failure`. Existing sources, documents and runs are unchanged. |
| `wfc_0011` | `sql/wfc_0011_relationship_intelligence.sql` | 28 Oct 2026 (refocus on discovery and relationship intelligence), additive and idempotent. Record types, the New/Reviewing/Pursuing/On hold/Closed progress flow, descriptive owner, saved flag, next action, notes; people research facts, evidence, opportunity links, existing relationships, introduction routes, research runs; derived views. Carries existing values over as summarised above. |
| `wfc_0010` | `sql/wfc_0010_status_chronology_v7.sql` | 27 Oct 2026 (fifth instruction), additive and idempotent. Claim type `tender_context` (supporting information about an established tender, e.g. a contact update; never a status statement). Signal classification `historical_record` (a cancellation, award or closure of a tender that is not tracked: kept as intelligence, outside the actionable pipeline and the live counts). Validation rules v7. Queues one re-check job (`field-revalidation:wfc_0010`, payload `{"to_version": 7}`) when any live material-field assessment is below v7 or any live tender signal exists. The worker:
- re-evaluates every live tender signal with the status chronology. Status follows the publication dates of status statements; retrieval never places one after another; a terminal status yields only to a dated, explicit reopening.
- returns an opportunity that was open or actionable only because an undated notice was retrieved after a terminal statement to the terminal (or contradictory) status, and flags it `status_chronology_revalidated` (and `status_conflict`).
- classifies terminal-only tender records that are not tracked as historical records.
- keeps claims, documents, reviewer decisions and history; a second run changes nothing.

Opportunities created by earlier releases from terminal-only notices are kept, with their terminal status. They are never live.

**Upgrade steps:**
1. Back up (`pg_dump -Fc`, see `RESTORE_RUNBOOK.md`).
2. `alembic upgrade head`.
3. Start or restart the worker.
4. Wait for `SELECT status FROM jobs WHERE execution_key = 'field-revalidation:wfc_0010'` to be `succeeded`.
5. Review the opportunities flagged `status_chronology_revalidated` or `status_conflict`. |
| `wfc_0009` | `sql/wfc_0009_status_freshness_v6.sql` | 27 Oct 2026 (fourth instruction), additive and idempotent. Publication-date provenance on `source_documents`: `published_at_source` may now also be `document_text` (the notice's own stated issue date) or `pdf_metadata`. New columns `publication_flag` (`future` or `inconsistent`: a stated date that was not used), `publication_note` and `publication_version`. Validation rules v6. Queues one re-check job (`field-revalidation:wfc_0009`, payload `{"to_version": 6}`) when any live material-field assessment is below v6, any stored publication date was set by earlier rules, or any live tender signal exists. The worker:
- re-reads every stored publication date with the current rules (a future date or disagreeing sources are flagged and left unknown; the previous value is kept in a `publication_date_revalidated` audit event);
- re-evaluates every live tender signal with the status-freshness rule: an open status kept 'fresh' only by a newer document that states no status becomes `unverified`, its opportunity is flagged `status_revalidated` and it leaves the live counts;
- moves route launches without road-feeder scope to capacity and trade lanes (`capability_area_revalidated`);
- keeps claims, documents, reviewer decisions and audit history; a second run changes nothing.

Rejected proposals stored by earlier releases (for example a passenger lot rejected before field validation) stay in the rejection queue with their reason. Only new extractions keep such lots as excluded tender records.

**Upgrade steps:**
1. Back up (`pg_dump -Fc`, see `RESTORE_RUNBOOK.md`).
2. `alembic upgrade head`.
3. Start or restart the worker.
4. Wait for `SELECT status FROM jobs WHERE execution_key = 'field-revalidation:wfc_0009'` to be `succeeded`.
5. Review the opportunities flagged `status_revalidated`, and the documents with a publication flag (Evidence review). |
| `wfc_0008` | `sql/wfc_0008_meaning_relevance_v5.sql` | 27 Oct 2026 (third instruction), additive and idempotent. Freight readings `not_freight` (cargo explicitly excluded, or work outside the freight capability scope) and `conflicting` (cargo required in one passage and excluded in another), on `signals.freight_scope` and `opportunities.freight_scope`. Signal classification `freight_candidate`: a reviewable candidate, never a qualified freight opportunity. Effective tender status `announced`: a title or heading establishes that the notice exists, and nothing states that it is open; it is never counted as live. History field `capability_area`. Validation rules v5. Queues one re-check job (`field-revalidation:wfc_0008`, payload `{"to_version": 5}`) when any live material-field assessment is below v5 or a live route/representation signal exists. The worker:
- re-reads every derived freight-scope reading against the whole document; reviewer readings are kept;
- supersedes and links the previous assessment, so evidence, decisions and audit events stay;
- moves excluded records out of qualification, counts, country matches, briefings and exports, with the reason kept;
- holds conflicting or unestablished scope for review;
- re-checks status, so title-only notices become `announced`;
- re-checks route origin and destination, so multi-stop rotations go to review;
- re-checks the capability area of route signals, so road-feeder launches and appointments move to trucking gateways;
- flags changed opportunities (`freight_scope_excluded`, `freight_scope_review`, `status_revalidated`).

**Upgrade steps:**
1. Back up (`pg_dump -Fc`, see `RESTORE_RUNBOOK.md`).
2. `alembic upgrade head`.
3. Start or restart the worker.
4. Wait for `SELECT status FROM jobs WHERE execution_key = 'field-revalidation:wfc_0008'` to be `succeeded`.
5. Review the flagged opportunities and the *Unresolved fields* tab. |
| `wfc_0007` | `sql/wfc_0007_relevance_v4.sql` | 27 Oct 2026 (second instruction), additive and idempotent: freight relevance (`claim_fields` field `freight_scope`; `signals.freight_scope`/`freight_scope_reason`; signal classification `excluded`; `opportunities.freight_scope`), the stated basis of the tender status (`opportunities.tender_status_basis`; effective statuses `unverified` and `historical`), document-wide geography conflicts (`source_documents.geography_conflict`), history field `freight_scope`. Validation rules v4. Queues one re-check job (`field-revalidation:wfc_0007`, payload `{"to_version": 4}`) when any live material-field assessment is below v4 or any live anchor claim has no freight-scope reading. The worker re-checks the fields, adds freight-scope readings, re-evaluates every live tender signal (passenger-only records leave the freight pipeline; old notices without a closing date or status wording become `unverified`/`historical`; geography follows the live verdicts), re-checks stored country matches of past runs (a match that no longer holds is marked withdrawn with its reason and the previous geography), keeps originals, decisions and audit events, and flags changed opportunities. **Upgrade steps:** back up (`pg_dump -Fc`, see `RESTORE_RUNBOOK.md`); `alembic upgrade head`; set `NOTICE_AGE_REVIEW_DAYS` on the API and worker if 90 days is not wanted; start the worker; wait for `SELECT status FROM jobs WHERE execution_key = 'field-revalidation:wfc_0007'` to be `succeeded`; review the flagged opportunities and the *Unresolved fields* tab (freight scope, geography conflicts). |
| `wfc_0006` | `sql/wfc_0006_revalidation_v3.sql` | 27 Oct 2026, additive and idempotent: validation rules v3 (interpretation gaps). Queues one re-check job (`eligibility_revalidation`, now covering every material field: eligibility, deadline, status, country, issuer country, contract territory, origin, destination) when any live assessment is below version 3. The worker keeps originals (superseded, linked), withdraws facts that no longer hold (a deadline whose zone abbreviation is not established becomes a local time; a status that is not stated is cleared), reopens claims whose 'supported' verdict was withdrawn with the previous decision recorded, and flags affected opportunities. **Upgrade steps:** back up; `alembic upgrade head`; start the worker; wait for `SELECT status FROM jobs WHERE execution_key = 'field-revalidation:wfc_0006'` to be `succeeded`; work through the review queue's *Unresolved fields* tab. |
| `wfc_0005` | `sql/wfc_0005_validation_version.sql` | Evening amendments of 26 Oct 2026, additive and idempotent: `claim_fields.validation_version` (rules that produced each field assessment; rows from before are version 1), `recheck_of` and `superseded_reason` (a re-check keeps the original row and links to it), `opportunities.review_flags`, history field `eligibility_evidence`, job type `eligibility_revalidation`. Queues one `eligibility_revalidation` job when any live eligibility assessment is below the current version (fresh installs queue nothing). The worker re-checks those assessments under validation rules v2 (relationship-level), supersedes changed ones, reopens claims whose 'supported' verdict was withdrawn (previous decision kept in `audit_events` and the claim note) and flags affected opportunities. **Upgrade steps:** back up; `alembic upgrade head`; start the worker; wait for the job to succeed (`SELECT status FROM jobs WHERE job_type = 'eligibility_revalidation'`); review the flagged opportunities in Evidence Review. |
| `wfc_0003` | `sql/wfc_0003_review.sql` | Review of 26 Oct 2026, additive only: (1) deadline precision (`deadline_info`, earliest/latest bounds, backfill); (2) `partial` run-source/ingestion status and per-target `issues`; (3) cumulative per-run AI ceiling (`budget_root_id`, `budget_cap_usd`, `budget_reservations.run_id`, function `reserve_run_budget`); (4) publication-date provenance, `date_filter`, `coverage_cursor`; (5) partner-fit basis columns for invalidation and reassessment. |

Each revision executes its SQL file; the PostgreSQL test suite applies the same files in order. `/health/ready` reports the expected revision (`wfc_0012`) and refuses readiness on a mismatch. No revision has a downgrade: restore from backup (`RESTORE_RUNBOOK.md`).
