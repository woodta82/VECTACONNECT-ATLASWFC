# Backup and restore runbook

## Targets (proposed, to be agreed with WFC)
- **RPO 24 hours:** nightly `pg_dump -Fc`, plus continuous WAL archiving if the hosting provider offers point-in-time recovery, which tightens RPO to minutes.
- **RTO 4 hours:** restore to a new database, point the API at it, verify, reopen.

## What is backed up
- The PostgreSQL database. It holds every table, including source documents, claims, derived intelligence, audit, imports, jobs and budget records.
- `SNAPSHOT_DIR`: retained source snapshots, only for sources that permit retention.
- Retention follows the dataset contracts. Deleting a source's data means deleting its snapshots too, plus the documents, claims and evidence that came only from it.
- Secrets are **not** in backups. They live in the deployment's secret store.

## Backup
```
pg_dump "$DATABASE_URL_PSQL" -Fc -f atlas-wfc-$(date -u +%Y%m%dT%H%MZ).dump
tar -czf snapshots-$(date -u +%Y%m%d).tgz -C "$SNAPSHOT_DIR" .
```
Store both encrypted, off-host, for 35 days.

## Restore
1. Pause the worker (`docker compose stop worker`) so no jobs write mid-restore.
2. `createdb atlas_wfc_restore`
3. `pg_restore --exit-on-error -d atlas_wfc_restore atlas-wfc-<stamp>.dump`
4. Verify:
   ```
   psql -d atlas_wfc_restore -Atc "SELECT value FROM schema_meta WHERE key='revision'"
   psql -d atlas_wfc_restore -Atc "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'"
   psql -d atlas_wfc_restore -Atc "SELECT count(*), sum(revenue) FROM bookings"
   ```
   Compare against the figures recorded at backup time.
5. Restore snapshots into `SNAPSHOT_DIR`.
6. Point `DATABASE_URL` at the restored database and restart api and worker.
7. Check that `/health/ready` reports `ready`.
8. Sign in and open Executive Briefing and Data Sources.
9. Expired sessions are expected; sign in again.

## Rehearsal evidence (this build, 26 Oct 2026)
- **Environment:** PostgreSQL 16.15, 2 vCPU, 7 GB RAM, local socket.
- **Dataset:** the full WFC schema plus 5,000 bookings.

| Check | Source | Restored |
|---|---|---|
| Tables | 71 | 71 |
| Bookings | 5,000 | 5,000 |
| Sum of revenue | 1,253,375,625.0000 | 1,253,375,625.0000 |
| Schema revision | wfc_0001 | wfc_0001 |
| Queue/budget functions | 3 | 3 |
| updated_at triggers | 13 | 13 |

- **Timings:** `pg_dump` 0.10 s, `pg_restore` 0.55 s, dump size 359,789 bytes.
- **CI:** the same rehearsal runs in the `backend-postgres` job.
- **Caveat:** these timings are for a tiny dataset and say nothing about production-scale RTO.
