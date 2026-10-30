-- wfc_0018 — contact currency and truthful stage outcomes (30 Oct 2026, release 4.8.0). Additive, idempotent.
--
-- * organisation_contacts.status gains 'historical' (a page says the address is obsolete, replaced, withdrawn or a former employee's:
--   kept as evidence, never offered as a current route) and 'under_review' (sources conflict: one presents the address as current,
--   another as obsolete; a person decides). Publication is never a claim of deliverability.
-- * people.published_email_status gains 'historical' (same meaning, for a person's address).
-- * research_stages.status gains 'done_with_failures': the stage finished its queue, but one or more organisations failed and remain
--   retryable. A stage is never shown as plainly 'done' while a failure is unresolved.
-- * research_stage_items.last_error keeps the reason of the last failure, for the retry action.

UPDATE schema_meta SET value = 'wfc_0018' WHERE key = 'revision';

ALTER TABLE organisation_contacts DROP CONSTRAINT IF EXISTS organisation_contacts_status_check;
ALTER TABLE organisation_contacts ADD CONSTRAINT organisation_contacts_status_check
    CHECK (status IN ('supplied','published','verified','lapsed','historical','under_review'));

ALTER TABLE people DROP CONSTRAINT IF EXISTS people_published_email_status_check;
ALTER TABLE people ADD CONSTRAINT people_published_email_status_check
    CHECK (published_email_status IS NULL OR published_email_status IN ('published','verified','lapsed','under_review','historical'));

ALTER TABLE research_stages DROP CONSTRAINT IF EXISTS research_stages_status_check;
ALTER TABLE research_stages ADD CONSTRAINT research_stages_status_check
    CHECK (status IN ('not_run','running','done','done_with_failures','incomplete','failed','not_applicable'));

ALTER TABLE research_stage_items ADD COLUMN IF NOT EXISTS last_error text;
