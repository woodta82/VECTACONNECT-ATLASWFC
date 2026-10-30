# Migration notes — release 4.8.0-wfc.19 (schema `wfc_0018`, 30 October 2026)

One additive, idempotent migration: `backend/migrations/sql/wfc_0018_contact_currency.sql` (Alembic wrapper
`backend/migrations/alembic/versions/wfc_0018_contact_currency.py`, revises `wfc_0017`). Re-running it changes nothing.

## Upgrade steps

1. Back up the database (`docs/RESTORE_RUNBOOK.md`).
2. `alembic upgrade head` (the `migrate` service). `/health/ready` must report `wfc_0018`.
3. The `airports` deployment step runs (unchanged from 4.7.0). `/health/ready` now also reports `airport_directory.full`: a healthy start
   with `"full": false` means the full directory is NOT in use — load it (see below) before relying on airport coverage.
4. Start the API. On its first start it re-checks, once for rule version 4.8.0, every recorded person address (below) and logs
   `Person e-mail re-check 4.8.0: N examined, C confirmed, H historical, F flagged for review, V verified kept`.
5. Review the outcome: person pages show **under review**, **historical** or a re-check note; the research file lists them under
   "What remains uncertain"; company contacts in conflict show **Sources conflict — review before use**.

## Schema

| Change | Detail |
|---|---|
| `organisation_contacts.status` | Adds `historical` (a source says the address is obsolete, replaced, withdrawn or a former employee's — kept as evidence, not a current route) and `under_review` (sources conflict). |
| `people.published_email_status` | Adds `historical`. |
| `research_stages.status` | Adds `done_with_failures` (the stage finished its queue but some organisations failed; retryable). |
| `research_stage_items.last_error` | The reason of the last failure, kept for the retry. |
| `schema_meta.revision` | `wfc_0018`. |

No existing row is changed or deleted by the migration.

## Data changes at first start (re-check 4.8.0)

Every recorded person address (status published, under review or verified) not yet re-checked under 4.8.0, with the passage it came from:

* **confirmed** — the passage ties the address to the person (explicit statement, contact block, table row): kept, basis recorded;
* **historical** — the passage says it is obsolete, replaced, withdrawn or a former employee's: status `historical`, kept as evidence;
* **under review** — anything else, including addresses assigned in 4.7.0 because the local part matched the name: value and evidence kept;
* **verified by a person** — never changed; a contradicting passage adds an evidence note and a re-check flag only.

Each outcome is written as an evidence note on the person ("re-check 4.8.0: …") and summarised in the audit log (`person_email_recheck`).
System flag `email_attribution_recheck` records the rule version applied.

## Behaviour changes

* A matching local part is supporting evidence only; it never assigns an address on its own.
* An address on a domain other than the organisation's is assigned only when the passage explains the relationship; otherwise it is
  pending review ("investigate"). Supplier, partner and third-party press contacts are never a person's at the company.
* Stage outcomes: Complete · Complete with unresolved failures · Incomplete (pending work) · Failed · Not run — with completed / failed /
  pending counts on the research file, the company page and the Dashboard. **Retry failed** (`POST /opportunities/{id}/deep-research/retry-failed`,
  `POST /companies/{id}/deep-research/retry-failed`) re-queues only failed organisations; Continue never retries a failure.
* A search result page that could not be read makes the organisation's identity step **failed** (retryable), never "not found after research".

## Rollback

Restore from backup; there is no downgrade script, as for every earlier revision.
