-- VECTA Connect | ATLAS | DYNAMIC MARKET INTELLIGENCE — wfc_0005 (amendments of 26 Oct 2026, evening, items 1-3).
-- Additive and idempotent.
UPDATE schema_meta SET value = 'wfc_0005' WHERE key = 'revision';

-- 1-2. VALIDATION VERSION. Every field assessment records the rule version that produced it. Rows written before this
-- revision were checked by version 1 (words, numbers, units, comparators), which could accept a reading that binds the
-- right numbers to the wrong requirement, swaps country roles or changes a date boundary. A one-off job
-- ('eligibility_revalidation') re-checks every live eligibility assessment made under an earlier version with the
-- current rules. The original row is kept (superseded, linked from the re-check through recheck_of), the decision
-- history is kept in audit_events and opportunity_status_history, and an obsolete 'supported' label is never left in place.
ALTER TABLE claim_fields ADD COLUMN IF NOT EXISTS validation_version integer NOT NULL DEFAULT 1;
ALTER TABLE claim_fields ADD COLUMN IF NOT EXISTS recheck_of uuid REFERENCES claim_fields(id);
ALTER TABLE claim_fields ADD COLUMN IF NOT EXISTS superseded_reason text;
CREATE INDEX IF NOT EXISTS ix_claim_fields_recheck ON claim_fields (field, validation_version) WHERE superseded_at IS NULL;

-- Opportunities affected by a re-check carry a visible flag until a reviewer has looked at the evidence again.
ALTER TABLE opportunities ADD COLUMN IF NOT EXISTS review_flags jsonb NOT NULL DEFAULT '[]'::jsonb;

ALTER TABLE opportunity_status_history DROP CONSTRAINT IF EXISTS opportunity_status_history_field_check;
ALTER TABLE opportunity_status_history ADD CONSTRAINT opportunity_status_history_field_check
    CHECK (field IN ('commercial_stage','qualification_status','deadline','tender_status','scope','owner','merge','eligibility_evidence'));

ALTER TABLE schedules DROP CONSTRAINT IF EXISTS schedules_job_type_check;
ALTER TABLE schedules ADD CONSTRAINT schedules_job_type_check
    CHECK (job_type IN ('discovery','discovery_search','import','briefing','connector_health','deadline_revalidation','eligibility_revalidation'));

-- 3. EVIDENCE INSPECTION. The document version (content hash) and retrieval time already live on source_documents;
-- claim_evidence.page_ref holds "page p, chars a-b". Nothing to add here; the API exposes them.

-- Queued only when there is something to re-check (a fresh install has nothing).
INSERT INTO jobs (job_type, execution_key, payload)
SELECT 'eligibility_revalidation', 'eligibility-revalidation:wfc_0005', '{"to_version": 2}'::jsonb
 WHERE EXISTS (SELECT 1 FROM claim_fields WHERE field = 'eligibility' AND superseded_at IS NULL AND validation_version < 2)
ON CONFLICT (execution_key) DO NOTHING;
