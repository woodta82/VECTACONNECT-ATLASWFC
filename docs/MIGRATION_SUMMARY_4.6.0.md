# Migration summary — release 4.6.0-wfc.17 (schema `wfc_0016`, 30 October 2026)

One additive, idempotent migration: `backend/migrations/sql/wfc_0016_workspace_research.sql` (Alembic wrapper
`backend/migrations/alembic/versions/wfc_0016_workspace_research.py`, revises `wfc_0015`). Apply with `alembic upgrade head` (the
`migrate` service), then check `/health/ready` reports `wfc_0016`. No worker job is queued. No row of any existing table is changed or
deleted; every new column has a safe default. Re-running the file changes nothing (`tests/sql/test_migration_0016.py`).

## New tables

| Table | Purpose |
|---|---|
| `reference_datasets` | Provenance of reference data: key, name, source, URL, licence, version, publisher refresh date, load time, rows loaded, notes. |
| `airport_directory` | The global airport directory: `ident` (ICAO where one exists, else the dataset's identifier), IATA, ICAO, name, city, country, ISO region, type, status (open/closed/unknown), scheduled service, coordinates, aliases, dataset key and id, refresh date; generated `search_text` for name/IATA/ICAO/city/country search. |
| `organisation_airports` | A company's airports, each a distinct fact with status and basis: office, station (operates here), served (from elsewhere), gateway, hub, destination. |
| `opportunity_airports` | An opportunity's airport scope: scope, origin, destination, gateway, station; with support (supported / unverified / internal record). |
| `research_stages` | Staged, resumable research: one row per entity (opportunity, organisation, person) and stage (identify, identity, company, people, relationships, relevance) with status (not run, running, done, incomplete, failed, not applicable), detail, counts, attempts, timestamps. |
| `company_duplicates` | Possible duplicate company records flagged for a person's review (reason, status open / dismissed / merged, note). |
| `company_merge_log` | Reversible company merges: kept and merged ids, note, what was re-pointed, merged / undone timestamps. |

## New columns

| Table | Columns | Default |
|---|---|---|
| `organisations` | `freight_scope` (freighter, belly, mixed, cargo_services, passenger_only, unresolved), `freight_scope_basis`, `contact_url`, `website_basis`, `research_status` (per-field status: found / not searched / not found after research / inaccessible / incomplete) | `unresolved`, NULL, NULL, NULL, `{}` |
| `organisation_contacts` | `department` | NULL |
| `people` | `published_email`, `published_email_status` (published / verified / lapsed), `published_email_source_url`, `research_status` | NULL, NULL, NULL, `{}` |
| `discovery_searches` | `airports` (directory idents) | `{}` |
| `contact_discoveries` | `airports` (directory idents) | `{}` |
| `research_documents` | `research_organisation_id` (a company's own research scope) | NULL |

## Constraints and indexes

- `research_documents_scope_check` now requires exactly one of `opportunity_id`, `discovery_id`, `research_organisation_id`
  (previously one of the first two). Existing rows satisfy it.
- Unique: `(research_organisation_id, url)` on research documents; `(organisation_id, airport_ident, role)` on company airports;
  `(entity_type, entity_id, stage)` on research stages; one open pair per company duplicate.
- Indexes on the directory (IATA, country/type, search text), company airports, research stages.

## Data loaded

- The API loads the **bundled airport seed** (424 airports) once at start-up under `reference_datasets.key = 'airport_seed'`; the
  Settings → Data sources → Airport directory page says so until the maintained dataset is loaded.
- The **maintained dataset** (OurAirports `airports.csv`, public domain) is loaded by `python tools/load_airports.py --download`
  (or `--file`) with `DATABASE_URL` set, or by upload on that page; its provenance, version and refresh date are recorded and every
  seed row it covers is replaced. The full dataset could not be downloaded in the build environment (no outbound access); the loader
  is tested against a sample in the dataset's own format.

## What is not touched

The WFC `airports` table (stations used by WFC data), the existing `organisation_merges` / `merge_candidates` of the WFC data
resolution, every opportunity, signal, person, discovery, search, run and audit row. Rollback: restore from backup
(`docs/RESTORE_RUNBOOK.md`); there is no downgrade script, as for every earlier revision.
