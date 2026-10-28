-- VECTA Connect | ATLAS | DYNAMIC MARKET INTELLIGENCE — wfc_0006 (27 Oct 2026, items 3-4). Additive and idempotent.
UPDATE schema_meta SET value = 'wfc_0006' WHERE key = 'revision';

-- Validation rules v3 (interpretation gaps of 27 Oct 2026) change how eligibility, deadlines (context-dependent zone
-- abbreviations), tender status (withdrawn/annulled/terminated) and geography (table cells, parentheses, cities) are
-- assessed. Every live material-field assessment made under an earlier version is re-checked by the worker
-- ('eligibility_revalidation' job, generalised to all material fields): originals kept and linked, withdrawn
-- 'supported' verdicts reopen the claim with the previous decision recorded, affected opportunities flagged.
ALTER TABLE opportunity_status_history DROP CONSTRAINT IF EXISTS opportunity_status_history_field_check;
ALTER TABLE opportunity_status_history ADD CONSTRAINT opportunity_status_history_field_check
    CHECK (field IN ('commercial_stage','qualification_status','deadline','tender_status','scope','owner','merge','eligibility_evidence','evidence'));

INSERT INTO jobs (job_type, execution_key, payload)
SELECT 'eligibility_revalidation', 'field-revalidation:wfc_0006', '{"to_version": 3}'::jsonb
 WHERE EXISTS (SELECT 1 FROM claim_fields WHERE superseded_at IS NULL AND validation_version < 3
                 AND field IN ('eligibility','deadline','status','country','issuer_country','contract_territory','origin','destination'))
ON CONFLICT (execution_key) DO NOTHING;
