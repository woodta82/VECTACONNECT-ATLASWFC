-- VECTA Connect | ATLAS | DYNAMIC MARKET INTELLIGENCE — wfc_0010 (27 Oct 2026, fifth instruction). Additive and idempotent.
UPDATE schema_meta SET value = 'wfc_0010' WHERE key = 'revision';

-- Item 5: supporting information about an established tender (a contact update, a clarification) that announces nothing.
ALTER TABLE claims DROP CONSTRAINT IF EXISTS claims_claim_type_check;
ALTER TABLE claims ADD CONSTRAINT claims_claim_type_check CHECK (claim_type IN (
    'route_launch','route_suspension','gssa_tender','tender_deadline','tender_scope','tender_status','representation_change',
    'tcm_signal','capacity_statement','partnership','eligibility','service_tender','tender_context','other'));

-- Item 4: a cancellation, award or closure of a tender that is not tracked is HISTORICAL INTELLIGENCE: the tender record keeps
-- its evidence and terminal status, outside the actionable pipeline and the live counts.
ALTER TABLE signals DROP CONSTRAINT IF EXISTS signals_classification_check;
ALTER TABLE signals ADD CONSTRAINT signals_classification_check
    CHECK (classification IN ('market_signal','unverified_lead','qualified_opportunity','risk_alert','research_item','excluded',
                              'freight_candidate','historical_record'));

-- Items 1 and 3: validation rules v7 (status follows the publication dates of status statements; retrieval never places one
-- after another; a terminal status yields only to a dated, explicit reopening). Queue one re-check when any live material-field
-- assessment is below v7 or any live tender signal exists.
INSERT INTO jobs (job_type, execution_key, payload)
SELECT 'eligibility_revalidation', 'field-revalidation:wfc_0010', '{"to_version": 7}'::jsonb
 WHERE EXISTS (SELECT 1 FROM claim_fields WHERE superseded_at IS NULL AND validation_version < 7
                 AND field IN ('eligibility','deadline','status','country','issuer_country','contract_territory','origin','destination','freight_scope'))
    OR EXISTS (SELECT 1 FROM signals s WHERE s.merged_into_id IS NULL AND s.tender_state IS NOT NULL)
ON CONFLICT (execution_key) DO NOTHING;
