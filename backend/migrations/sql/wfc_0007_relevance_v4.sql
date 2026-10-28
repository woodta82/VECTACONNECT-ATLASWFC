-- VECTA Connect | ATLAS | DYNAMIC MARKET INTELLIGENCE — wfc_0007 (27 Oct 2026, second instruction). Additive and idempotent.
UPDATE schema_meta SET value = 'wfc_0007' WHERE key = 'revision';

-- Freight relevance (item 1): every tender anchor claim carries a derived 'freight_scope' field assessment (cargo / passenger /
-- mixed / unclear) with the wording that produced it; passenger-only mandates are EXCLUDED from the freight pipeline (signal
-- classification 'excluded', reason kept), mixed and unclear ones wait for a person.
ALTER TABLE claim_fields DROP CONSTRAINT IF EXISTS claim_fields_field_check;
ALTER TABLE claim_fields ADD CONSTRAINT claim_fields_field_check
    CHECK (field IN ('organisation','airline','opportunity_type','country','issuer_country','contract_territory','origin','destination',
                     'tender_ref','procurement_cycle','status','deadline','eligibility','published_value','service','freight_scope'));
ALTER TABLE signals DROP CONSTRAINT IF EXISTS signals_classification_check;
ALTER TABLE signals ADD CONSTRAINT signals_classification_check
    CHECK (classification IN ('market_signal','unverified_lead','qualified_opportunity','risk_alert','research_item','excluded'));
ALTER TABLE signals ADD COLUMN IF NOT EXISTS freight_scope text CHECK (freight_scope IN ('cargo','passenger','mixed','unclear'));
ALTER TABLE signals ADD COLUMN IF NOT EXISTS freight_scope_reason text;
ALTER TABLE opportunities ADD COLUMN IF NOT EXISTS freight_scope text CHECK (freight_scope IN ('cargo','passenger','mixed','unclear'));
-- Publication age, deadline and verified live status are separate (item 3): the effective tender status may now be 'unverified'
-- (open wording, no closing date, older than the review threshold) or 'historical' (no supported status, older than the threshold);
-- the basis is recorded in words so lists, exports and briefings show why.
ALTER TABLE opportunities ADD COLUMN IF NOT EXISTS tender_status_basis text;
-- Geography across the whole document (item 2): a notice whose title/territory definition and another passage name different
-- territories is flagged; the conflicting country is never a supported delivery country.
ALTER TABLE source_documents ADD COLUMN IF NOT EXISTS geography_conflict text;
ALTER TABLE opportunity_status_history DROP CONSTRAINT IF EXISTS opportunity_status_history_field_check;
ALTER TABLE opportunity_status_history ADD CONSTRAINT opportunity_status_history_field_check
    CHECK (field IN ('commercial_stage','qualification_status','deadline','tender_status','scope','owner','merge','eligibility_evidence','evidence',
                     'freight_scope'));

-- Validation rules v4: every live material-field assessment below v4 is re-checked, every anchor claim without a freight-scope
-- reading gets one, every live tender signal is re-evaluated (effective status with the age rule, geography from live verdicts,
-- freight relevance), stored country matches of past runs are re-checked, originals kept and linked, withdrawn facts leave
-- summaries, scores, country matches, briefings and exports, affected opportunities flagged for review.
INSERT INTO jobs (job_type, execution_key, payload)
SELECT 'eligibility_revalidation', 'field-revalidation:wfc_0007', '{"to_version": 4}'::jsonb
 WHERE EXISTS (SELECT 1 FROM claim_fields WHERE superseded_at IS NULL AND validation_version < 4
                 AND field IN ('eligibility','deadline','status','country','issuer_country','contract_territory','origin','destination'))
    OR EXISTS (SELECT 1 FROM claims c WHERE c.claim_type IN ('gssa_tender','service_tender','tcm_signal','representation_change')
                 AND c.review_status NOT IN ('rejected','corrected')
                 AND NOT EXISTS (SELECT 1 FROM claim_fields cf WHERE cf.claim_id = c.id AND cf.field = 'freight_scope' AND cf.superseded_at IS NULL))
ON CONFLICT (execution_key) DO NOTHING;
