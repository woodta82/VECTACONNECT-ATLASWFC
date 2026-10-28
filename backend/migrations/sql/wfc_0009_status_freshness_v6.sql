-- VECTA Connect | ATLAS | DYNAMIC MARKET INTELLIGENCE — wfc_0009 (27 Oct 2026, fourth instruction). Additive and idempotent.
UPDATE schema_meta SET value = 'wfc_0009' WHERE key = 'revision';

-- Item 2: truthful publication dates. Where a publication date comes from ('document_text' = the notice's own stated issue
-- date, 'page' = HTML metadata, 'pdf_metadata' = the PDF's creation date, 'feed' = the RSS/Atom item); a stated date that was
-- NOT used is flagged ('future': later than retrieval; 'inconsistent': sources disagree) with a note. Retrieval time is never a
-- publication date. publication_version: the date rules that produced the stored date (6 = this revision).
ALTER TABLE source_documents DROP CONSTRAINT IF EXISTS source_documents_published_at_source_check;
ALTER TABLE source_documents ADD CONSTRAINT source_documents_published_at_source_check
    CHECK (published_at_source IN ('page','feed','pdf_metadata','document_text'));
ALTER TABLE source_documents ADD COLUMN IF NOT EXISTS publication_flag text;
ALTER TABLE source_documents DROP CONSTRAINT IF EXISTS source_documents_publication_flag_check;
ALTER TABLE source_documents ADD CONSTRAINT source_documents_publication_flag_check CHECK (publication_flag IN ('future','inconsistent'));
ALTER TABLE source_documents ADD COLUMN IF NOT EXISTS publication_note text;
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'source_documents' AND column_name = 'publication_version') THEN
    ALTER TABLE source_documents ADD COLUMN publication_version int;
    UPDATE source_documents SET publication_version = 5;
    ALTER TABLE source_documents ALTER COLUMN publication_version SET DEFAULT 6;
    ALTER TABLE source_documents ALTER COLUMN publication_version SET NOT NULL;
  END IF;
END $$;

-- Items 1 and 3: validation rules v6 (status freshness is the date of the latest document that STATES the status; documents
-- with no status never renew it; unknown publication dates give no age). Queue one re-check when any live material-field
-- assessment is below v6, any document's publication date was set by earlier rules, or any live tender or route signal exists.
INSERT INTO jobs (job_type, execution_key, payload)
SELECT 'eligibility_revalidation', 'field-revalidation:wfc_0009', '{"to_version": 6}'::jsonb
 WHERE EXISTS (SELECT 1 FROM claim_fields WHERE superseded_at IS NULL AND validation_version < 6
                 AND field IN ('eligibility','deadline','status','country','issuer_country','contract_territory','origin','destination','freight_scope'))
    OR EXISTS (SELECT 1 FROM source_documents WHERE publication_version < 6)
    OR EXISTS (SELECT 1 FROM signals s WHERE s.merged_into_id IS NULL AND s.tender_state IS NOT NULL)
ON CONFLICT (execution_key) DO NOTHING;
