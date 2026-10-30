# Migration notes — release 4.9.0-wfc.20 (schema `wfc_0019`, 30 October 2026)

One additive, idempotent migration: `backend/migrations/sql/wfc_0019_contact_involvement.sql` (Alembic wrapper
`backend/migrations/alembic/versions/wfc_0019_contact_involvement.py`, revises `wfc_0018`).

## Upgrade steps

1. Back up the database (`docs/RESTORE_RUNBOOK.md`).
2. `alembic upgrade head`. `/health/ready` must report `wfc_0019`.
3. Start the API. On its first start it re-classifies, once (rule version 4.9.0), the involvement of every person recorded by research and
   logs `Person involvement re-check 4.9.0: N examined, C changed (P press contacts, A external advisers), L opportunity links moved`.

## Schema

| Change | Detail |
|---|---|
| `people.involvement` | `employee`, `appointed_representative`, `external_adviser`, `press_contact`, `unresolved` (default). With `involvement_basis`, `involvement_org` (the outside organisation) and `involvement_set_by` (`research` or `person`). |
| `opportunity_people.status` | Adds `external_contact`: kept on the opportunity with the actual role, not a commercial contact. |
| `opportunity_relationship_coverage` (view) | Counts only `candidate` and `relevant` links, and never a press contact or external adviser. |
| `schema_meta.revision` | `wfc_0019`. |

No row is deleted. The one-time re-check changes `people.involvement` for research-recorded people and moves their opportunity links between
`candidate` and `external_contact`; a person's own decision (a link marked relevant or not relevant, an involvement set by a person) is never
changed. Every change is an evidence note ("involvement re-check 4.9.0: …") and the run is audited (`person_involvement_recheck`).

## Behaviour changes

* Press / media contacts and external advisers are kept with their actual role and organisation, listed as **external contacts**, and
  excluded from relationship coverage, the priority order, discovery's people ranking and the research file's commercial people and gaps.
* A person can correct someone's involvement (`POST /people/{id}/involvement`, person page → Correct the involvement); research never
  changes it afterwards.
* The `api` pre-deploy command loads the airport directory (`docs/DEPLOY_RAILWAY_SUPABASE.md`).

## Rollback

Restore from backup; there is no downgrade script, as for every earlier revision.
