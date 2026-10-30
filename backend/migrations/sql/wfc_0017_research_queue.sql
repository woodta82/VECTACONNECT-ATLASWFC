-- wfc_0017 — truthful, resumable research and person-to-e-mail attribution (30 Oct 2026, amendment items 1–2). Additive, idempotent.
--
-- * research_stage_items: the persisted work queue of each organisation-scoped research stage — one row per (entity, stage, organisation)
--   with its status, so a run with a per-run limit continues with the PENDING organisations instead of starting again with the first few,
--   and a stage is never 'done' while an organisation is pending. Counts per stage (total / attempted / completed / failed / pending) are
--   derived from these rows.
-- * people.published_email_status gains 'under_review': an address assigned under the earlier first-address-in-the-sentence rule that the
--   attribution rule cannot confirm, or one a later page contradicts, keeps its value and evidence and is flagged for a person's decision.

UPDATE schema_meta SET value = 'wfc_0017' WHERE key = 'revision';

CREATE TABLE IF NOT EXISTS research_stage_items (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_type     text NOT NULL CHECK (entity_type IN ('opportunity','organisation','person')),
    entity_id       uuid NOT NULL,
    stage           text NOT NULL CHECK (stage IN ('identify','identity','company','people','relationships','relevance')),
    organisation_id uuid NOT NULL REFERENCES organisations(id),
    status          text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','attempted','done','failed','skipped')),
    attempts        int  NOT NULL DEFAULT 0,
    detail          text,
    queued_at       timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    session_ref     text
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_research_stage_items ON research_stage_items (entity_type, entity_id, stage, organisation_id);
CREATE INDEX IF NOT EXISTS ix_research_stage_items_pending ON research_stage_items (entity_type, entity_id, stage, queued_at) WHERE status = 'pending';

ALTER TABLE people DROP CONSTRAINT IF EXISTS people_published_email_status_check;
ALTER TABLE people ADD CONSTRAINT people_published_email_status_check
    CHECK (published_email_status IS NULL OR published_email_status IN ('published','verified','lapsed','under_review'));

