-- =====================================================================
-- wfc_0004: amendments of 26 October 2026 (additive only)
-- =====================================================================

UPDATE schema_meta SET value = 'wfc_0004' WHERE key = 'revision';

-- 1. COMPLETE READING: progress through a document's sections, and the 'incomplete' state (partly read).
ALTER TABLE source_documents ADD COLUMN read_progress jsonb;   -- {"total": n, "done": [...], "section_bytes": b, "fingerprint": sha256}
ALTER TABLE source_documents DROP CONSTRAINT IF EXISTS source_documents_extraction_status_check;
ALTER TABLE source_documents ADD CONSTRAINT source_documents_extraction_status_check
    CHECK (extraction_status IN ('pending','extracted','no_claims','partial','incomplete','failed','not_connected','budget_refused','manual'));
-- Documents an earlier version marked as read, but which are longer than one extraction call: that version cut them
-- to a fixed length, so they were NOT read in full. They become 'incomplete' and are read again completely (by the
-- next run that meets them, or "Continue reading" in Evidence Review). Documents whose text is not retained are
-- caught at run time instead (discovery.process_document compares the fetched text with the section size).
UPDATE source_documents SET extraction_status = 'incomplete',
       extraction_detail = 'read by an earlier version that cut long documents to a fixed length; it will be read again in full'
 WHERE read_progress IS NULL AND extraction_status IN ('extracted','partial','no_claims')
   AND body_text IS NOT NULL AND octet_length(body_text) > 17000;

-- 3. ELIGIBILITY: a reading that may be fair but reshapes the requirement (dropped condition, dropped alternative,
-- comparator not in the source) is 'review_required' — shown to a person, never used as a fact.
ALTER TABLE claim_fields DROP CONSTRAINT IF EXISTS claim_fields_support_check;
ALTER TABLE claim_fields ADD CONSTRAINT claim_fields_support_check
    CHECK (support IN ('supported','unsupported','not_applicable','review_required'));

-- 4. CONTRADICTIONS: a document that both announces an opportunity and says the process has ended. Its tender
-- observation becomes 'contradictory' (never open) until a person reviews it.
ALTER TABLE source_documents ADD COLUMN status_contradiction text;

-- 5. DISCOVERY LINK QUEUE: relevant article links that one run could not process (per-run document limit, feed or
-- listing overflow, a failed fetch) are queued for the same search (or, for a single-source run, the same source)
-- and read FIRST by its next run. A run never reports completion while relevant queued links remain.
CREATE TABLE discovery_link_queue (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    scope_key       text NOT NULL,                       -- 'search:<uuid>' or 'source:<uuid>'
    source_id       uuid NOT NULL REFERENCES sources(id),
    url             text NOT NULL,
    title           text,
    country         char(2),
    published_hint  timestamptz,                         -- from the feed item, when it had one
    reason          text NOT NULL CHECK (reason IN ('not_fetched_limit','feed_overflow','listing_overflow','retrieval_failed',
                                                    'partially_read','unextracted')),
    status          text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','done','gave_up')),
    attempts        integer NOT NULL DEFAULT 0,
    first_run_id    uuid REFERENCES discovery_runs(id),
    last_run_id     uuid REFERENCES discovery_runs(id),
    last_error      text,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    UNIQUE (scope_key, source_id, url)
);
CREATE INDEX ix_link_queue_pending ON discovery_link_queue (scope_key, source_id, created_at) WHERE status = 'pending';
CREATE TRIGGER trg_touch_discovery_link_queue BEFORE UPDATE ON discovery_link_queue FOR EACH ROW EXECUTE FUNCTION touch_updated_at();

-- 6. MIGRATED DEADLINES: see wfc_0004_legacy_deadlines.sql (applied right after this file; it is idempotent, so the
-- test suite can re-apply it to rows it creates in the legacy shape).
ALTER TABLE schedules DROP CONSTRAINT schedules_job_type_check;
ALTER TABLE schedules ADD CONSTRAINT schedules_job_type_check
    CHECK (job_type IN ('discovery','discovery_search','import','briefing','connector_health','deadline_revalidation'));
