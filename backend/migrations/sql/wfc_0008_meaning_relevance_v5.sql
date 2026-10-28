-- VECTA Connect | ATLAS | DYNAMIC MARKET INTELLIGENCE — wfc_0008 (27 Oct 2026, third instruction). Additive and idempotent.
UPDATE schema_meta SET value = 'wfc_0008' WHERE key = 'revision';

-- Freight relevance at the meaning level (items 1-2): two further readings, 'not_freight' (cargo explicitly excluded, or work
-- outside the freight capability scope) and 'conflicting' (cargo required in one passage and excluded in another); a
-- reviewable candidate is classified 'freight_candidate' (never a qualified freight opportunity).
ALTER TABLE signals DROP CONSTRAINT IF EXISTS signals_freight_scope_check;
ALTER TABLE signals ADD CONSTRAINT signals_freight_scope_check
    CHECK (freight_scope IN ('cargo','passenger','mixed','unclear','not_freight','conflicting'));
ALTER TABLE opportunities DROP CONSTRAINT IF EXISTS opportunities_freight_scope_check;
ALTER TABLE opportunities ADD CONSTRAINT opportunities_freight_scope_check
    CHECK (freight_scope IN ('cargo','passenger','mixed','unclear','not_freight','conflicting'));
ALTER TABLE signals DROP CONSTRAINT IF EXISTS signals_classification_check;
ALTER TABLE signals ADD CONSTRAINT signals_classification_check
    CHECK (classification IN ('market_signal','unverified_lead','qualified_opportunity','risk_alert','research_item','excluded','freight_candidate'));
-- Item 3: the effective tender status may now be 'announced' (the notice exists; nothing states it is still open). The column is
-- free text; no constraint change is needed. Item 4: the capability area of a route or representation signal may change on
-- re-check (road-feeder launches and appointments -> trucking_gateways); the change is audited.
ALTER TABLE opportunity_status_history DROP CONSTRAINT IF EXISTS opportunity_status_history_field_check;
ALTER TABLE opportunity_status_history ADD CONSTRAINT opportunity_status_history_field_check
    CHECK (field IN ('commercial_stage','qualification_status','deadline','tender_status','scope','owner','merge','eligibility_evidence','evidence',
                     'freight_scope','capability_area'));

-- Validation rules v5: queue one re-check when any live material-field or freight-scope assessment is below v5.
INSERT INTO jobs (job_type, execution_key, payload)
SELECT 'eligibility_revalidation', 'field-revalidation:wfc_0008', '{"to_version": 5}'::jsonb
 WHERE EXISTS (SELECT 1 FROM claim_fields WHERE superseded_at IS NULL AND validation_version < 5
                 AND field IN ('eligibility','deadline','status','country','issuer_country','contract_territory','origin','destination','freight_scope'))
    OR EXISTS (SELECT 1 FROM signals s WHERE s.merged_into_id IS NULL AND s.signal_key NOT LIKE 'tender|%'
                 AND EXISTS (SELECT 1 FROM signal_claims sc JOIN claims c ON c.id = sc.claim_id
                             WHERE sc.signal_id = s.id AND c.claim_type IN ('route_launch','route_suspension','representation_change')))
ON CONFLICT (execution_key) DO NOTHING;
