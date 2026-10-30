# Migration notes — release 4.7.0-wfc.18 (schema `wfc_0017`, 30 October 2026)

One additive, idempotent migration: `backend/migrations/sql/wfc_0017_research_queue.sql` (Alembic wrapper
`backend/migrations/alembic/versions/wfc_0017_research_queue.py`, revises `wfc_0016`). Re-running it changes nothing.

## Upgrade steps

1. Back up the database (`docs/RESTORE_RUNBOOK.md`).
2. `alembic upgrade head` (the `migrate` service). `/health/ready` must report `wfc_0017`.
3. The `airports` service runs after the migration and loads the full airport directory (below). It never blocks the application.
4. Start the API. On its first start it re-checks, once, the person e-mail addresses assigned by the earlier rule (below) and logs
   `Person e-mail re-check: N examined, C confirmed, F flagged for review`.
5. Review the flagged addresses: a person page shows them as **under review** with the reason; the research file lists them under
   "What remains uncertain".

## Schema

| Change | Detail |
|---|---|
| New table `research_stage_items` | The persisted work queue of each organisation-scoped research stage: one row per (entity, stage, organisation) with status `pending` / `attempted` / `done` / `failed` / `skipped`, attempts, detail, timestamps. Unique on (entity_type, entity_id, stage, organisation_id); partial index on pending rows. |
| `people.published_email_status` | Check constraint now allows `under_review` (besides `published`, `verified`, `lapsed`). |
| `schema_meta.revision` | `wfc_0017`. |

No existing row is changed or deleted by the migration.

## Data changes at first start (re-check of earlier e-mail assignments)

Release 4.6.0 assigned a person's e-mail as the first address in the sentence containing the name (plus a short following sentence).
That could give one person another's address (Jane Smith receiving John Brown's). The re-check (`deep_research.recheck_published_emails`)
examines every address assigned by that rule against the new attribution rule on the passage it came from:

* **confirmed** — the address is the person's own name, or the passage ties it to that person: the address stays and gains its basis;
* **uncertain** — anything else: the address and all previous evidence are kept, the status becomes `under_review`, the reason is recorded
  in the person's research status and as a new evidence note. A person decides. An address a person marked `verified` keeps that status.

It runs once (system flag `email_attribution_recheck`) and is idempotent if run again.

## Airport directory at deployment

`docker-compose.yml` gains an `airports` one-shot service: `python -m app.airports_cli load --auto --if-stale 30 --optional`.

* With `AIRPORTS_PACKAGE=/srv/airports-package` and a package mounted from `AIRPORTS_PACKAGE_DIR` (default `./deploy/airports-package`),
  it loads that **verified import package** (`airports.csv.gz` + `manifest.json`; SHA-256, row and code counts recomputed; a mismatch
  is refused).
* Otherwise it downloads OurAirports' `airports.csv` (public domain).
* It is skipped when the full directory was loaded fewer than 30 days ago; a failure (no outbound access) is reported and the application
  runs on what is loaded. Settings → Data sources → Airport directory states **Bundled seed only**, **Partial directory** (a maintained
  file with fewer than 40,000 rows) or **Full directory**, with source, version, publisher refresh date, load time and total records.

Build a package where the publisher is reachable: `python -m app.airports_cli package --file airports.csv --version <date>
--refreshed-at <date> --out deploy/airports-package`, then `python -m app.airports_cli verify deploy/airports-package`.
**No package is included in this release**: the build environment had no outbound access to the publisher.

## Behaviour changes to note

* A research stage is never `done` while an organisation in its queue is pending; at most six organisations per stage per run; a
  continuation takes the pending ones first. Stage rows carry `progress` ("6 of 9 organisation(s) done, 3 pending").
* Research candidates no longer rank above "nobody identified" in the priority order: unconfirmed people are research completeness, not a
  relationship.
* A website corrected by a person is never overwritten by research; a page presenting a different site sets the field to
  **Changed evidence — re-check** until a person decides (edit or verify).

## Rollback

Restore from backup; there is no downgrade script, as for every earlier revision.
