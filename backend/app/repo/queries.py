"""Every SQL statement the API and worker run, in one place.

Each statement is PREPAREd against a real PostgreSQL database built from
`migrations/sql/wfc_0001_schema.sql` by tests/sql/test_pg_queries.py, so a
typo in a column name or a type mismatch fails CI before deployment.

Parameters use SQLAlchemy's `:name` style. Ambiguous parameters carry an
explicit CAST so PostgreSQL can infer types at PREPARE time.
"""

Q: dict[str, str] = {}

# ---------------------------------------------------------------- auth
Q["cred_get"] = "SELECT username, password_hash, sessions_valid_after FROM auth_credential WHERE singleton"
Q["cred_bootstrap"] = """
INSERT INTO auth_credential (username, password_hash) VALUES (CAST(:username AS text), CAST(:hash AS text))
ON CONFLICT (singleton) DO NOTHING"""
Q["cred_set_password"] = """
UPDATE auth_credential SET password_hash = CAST(:hash AS text), password_changed_at = now(), sessions_valid_after = now()
WHERE singleton"""
Q["cred_invalidate_sessions"] = "UPDATE auth_credential SET sessions_valid_after = now() WHERE singleton"
Q["sessions_revoke_all"] = "UPDATE auth_sessions SET revoked_at = now() WHERE revoked_at IS NULL"
Q["session_insert"] = """
INSERT INTO auth_sessions (token_hash, csrf_token_hash, expires_at, ip, user_agent)
VALUES (CAST(:token_hash AS text), CAST(:csrf_hash AS text), CAST(:expires_at AS timestamptz), CAST(:ip AS text), CAST(:ua AS text))"""
Q["session_get"] = """
SELECT s.id, s.token_hash, s.csrf_token_hash, s.created_at, s.last_used_at, s.expires_at, s.revoked_at, c.sessions_valid_after
FROM auth_sessions s CROSS JOIN auth_credential c
WHERE s.token_hash = CAST(:token_hash AS text)"""
Q["session_touch"] = """
UPDATE auth_sessions SET last_used_at = now()
WHERE token_hash = CAST(:token_hash AS text) AND last_used_at < now() - interval '1 minute'"""
Q["session_revoke"] = "UPDATE auth_sessions SET revoked_at = now() WHERE token_hash = CAST(:token_hash AS text) AND revoked_at IS NULL"
Q["sessions_active_count"] = """
SELECT count(*) FROM auth_sessions s CROSS JOIN auth_credential c
WHERE s.revoked_at IS NULL AND s.expires_at > now() AND s.created_at >= c.sessions_valid_after"""
Q["throttle_add"] = "INSERT INTO login_throttle (throttle_key) VALUES (CAST(:key AS text))"
Q["throttle_recent"] = """
SELECT failed_at FROM login_throttle WHERE throttle_key = CAST(:key AS text) AND failed_at > now() - interval '15 minutes'"""
Q["throttle_clear"] = "DELETE FROM login_throttle WHERE throttle_key = CAST(:key AS text)"
Q["throttle_prune"] = "DELETE FROM login_throttle WHERE failed_at < now() - interval '1 day'"
Q["audit"] = """
INSERT INTO audit_events (event_type, session_ref, request_id, ip, user_agent, entity_type, entity_id, detail)
VALUES (CAST(:event_type AS text), CAST(:session_ref AS text), CAST(:request_id AS text), CAST(:ip AS text),
        CAST(:ua AS text), CAST(:entity_type AS text), CAST(:entity_id AS text), CAST(:detail AS jsonb))"""
Q["audit_list"] = """
SELECT id, occurred_at, event_type, actor, session_ref, entity_type, entity_id, detail
FROM audit_events ORDER BY occurred_at DESC LIMIT CAST(:limit AS int) OFFSET CAST(:offset AS int)"""

# ---------------------------------------------------------------- health
Q["schema_revision"] = "SELECT value FROM schema_meta WHERE key = 'revision'"

# ---------------------------------------------------------------- briefing
Q["briefing_pipeline"] = """
SELECT o.module, o.commercial_stage, o.qualification_status, count(*) AS n
FROM opportunities o GROUP BY 1, 2, 3 ORDER BY 1, 2, 3"""
Q["briefing_deadlines"] = """
SELECT o.id, o.title, o.module, o.deadline_utc, o.deadline_source_tz, o.deadline_info, o.qualification_status, o.commercial_stage
FROM opportunities o
WHERE o.deadline_latest_utc >= now() AND o.deadline_earliest_utc <= now() + make_interval(days => CAST(:days AS int))
  AND o.commercial_stage NOT IN ('won','lost','expired','deferred')
ORDER BY o.deadline_latest_utc LIMIT 50"""
Q["briefing_signals"] = """
SELECT s.id, s.module, s.classification, s.title, s.summary, s.gaps, s.created_at
FROM signals s ORDER BY s.created_at DESC LIMIT CAST(:limit AS int)"""
Q["briefing_exceptions"] = """
SELECT severity, count(*) AS n FROM operational_exceptions WHERE status <> 'resolved' GROUP BY severity"""
Q["source_health"] = """
SELECT s.id, s.name, s.family, s.authority, s.enabled, s.freshness_sla_hours, c.code AS connector_code, c.status AS connector_status,
       (SELECT max(r.finished_at) FROM ingestion_runs r WHERE r.source_id = s.id AND r.status = 'succeeded') AS last_success_at,
       (SELECT max(r.finished_at) FROM ingestion_runs r WHERE r.source_id = s.id AND r.status = 'failed') AS last_failure_at
FROM sources s LEFT JOIN connectors c ON c.id = s.connector_id ORDER BY s.name"""

# ---------------------------------------------------------------- opportunities
Q["opportunity_list"] = """
SELECT o.id, o.module, o.title, o.commercial_stage, o.qualification_status, o.deadline_utc, o.deadline_source_tz, o.deadline_info,
       s.classification, oc.name AS operating_company, org.canonical_name AS organisation, t.code AS territory,
       sv.code AS service, p.full_name AS owner, o.updated_at,
       count(*) OVER () AS total
FROM opportunities o
LEFT JOIN signals s ON s.id = o.signal_id
LEFT JOIN operating_companies oc ON oc.id = o.operating_company_id
LEFT JOIN organisations org ON org.id = coalesce(o.airline_id, o.organisation_id)
LEFT JOIN territories t ON t.id = o.territory_id
LEFT JOIN services sv ON sv.id = o.service_id
LEFT JOIN people p ON p.id = o.owner_person_id
WHERE (CAST(:module AS text) IS NULL OR o.module = CAST(:module AS text))
  AND (CAST(:stage AS text) IS NULL OR o.commercial_stage = CAST(:stage AS text))
  AND (CAST(:qual AS text) IS NULL OR o.qualification_status = CAST(:qual AS text))
  AND (CAST(:company AS uuid) IS NULL OR o.operating_company_id = CAST(:company AS uuid))
  AND (CAST(:q AS text) IS NULL OR o.title ILIKE '%' || CAST(:q AS text) || '%')
ORDER BY o.deadline_latest_utc NULLS LAST, o.updated_at DESC
LIMIT CAST(:limit AS int) OFFSET CAST(:offset AS int)"""
Q["opportunity_get"] = """
SELECT o.*, s.classification, s.gaps, s.title AS signal_title, oc.name AS operating_company, org.canonical_name AS organisation,
       t.code AS territory, sv.code AS service, p.full_name AS owner
FROM opportunities o
LEFT JOIN signals s ON s.id = o.signal_id
LEFT JOIN operating_companies oc ON oc.id = o.operating_company_id
LEFT JOIN organisations org ON org.id = coalesce(o.airline_id, o.organisation_id)
LEFT JOIN territories t ON t.id = o.territory_id
LEFT JOIN services sv ON sv.id = o.service_id
LEFT JOIN people p ON p.id = o.owner_person_id
WHERE o.id = CAST(:id AS uuid)"""
Q["opportunity_checks"] = """
SELECT check_code, result, blocking, rationale, evidence_refs, evaluated_at, reviewer_note
FROM qualification_checks WHERE opportunity_id = CAST(:id AS uuid) ORDER BY check_code"""
Q["opportunity_overrides"] = """
SELECT id, check_code, override_result, reason, session_ref, created_at, expires_at, revoked_at
FROM qualification_overrides WHERE opportunity_id = CAST(:id AS uuid) ORDER BY created_at"""
Q["opportunity_history"] = """
SELECT field, from_value, to_value, reason, session_ref, changed_at
FROM opportunity_status_history WHERE opportunity_id = CAST(:id AS uuid) ORDER BY changed_at"""
Q["opportunity_claims"] = """
SELECT c.id AS claim_id, c.claim_type, c.status, c.value, c.deadline_utc, c.deadline_source_tz,
       ce.stance, ce.excerpt, ce.page_ref, ce.assessed_by,
       d.id AS document_id, d.canonical_url, d.publisher, d.published_at, d.retrieved_at, d.content_hash,
       f.family_key, coalesce(d.doc_authority, src.authority) AS authority
FROM opportunities o
JOIN signal_claims sc ON sc.signal_id = o.signal_id
JOIN claims c ON c.id = sc.claim_id
LEFT JOIN claim_evidence ce ON ce.claim_id = c.id
LEFT JOIN source_documents d ON d.id = ce.source_document_id
LEFT JOIN announcement_families f ON f.id = d.announcement_family_id
LEFT JOIN sources src ON src.id = d.source_id
WHERE o.id = CAST(:id AS uuid)
ORDER BY c.claim_type, d.published_at NULLS LAST"""
Q["opportunity_assessments"] = """
SELECT DISTINCT ON (a.dimension) a.dimension, a.score, a.coverage, a.status, a.factors, a.computed_at, mv.version, mv.provisional
FROM assessments a JOIN scoring_model_versions mv ON mv.id = a.model_version_id
WHERE a.opportunity_id = CAST(:id AS uuid)
ORDER BY a.dimension, a.computed_at DESC"""
Q["opportunity_value"] = "SELECT * FROM commercial_values WHERE opportunity_id = CAST(:id AS uuid)"
Q["opportunity_lock"] = "SELECT commercial_stage, qualification_status, approval_basis FROM opportunities WHERE id = CAST(:id AS uuid) FOR UPDATE"
Q["opportunity_set_stage"] = """
UPDATE opportunities SET commercial_stage = CAST(:to AS text) WHERE id = CAST(:id AS uuid)"""
Q["opportunity_set_qual"] = """
UPDATE opportunities SET qualification_status = CAST(:to AS text) WHERE id = CAST(:id AS uuid)"""
Q["opportunity_set_owner"] = "UPDATE opportunities SET owner_person_id = CAST(:person AS uuid) WHERE id = CAST(:id AS uuid)"
Q["opportunity_history_add"] = """
INSERT INTO opportunity_status_history (opportunity_id, field, from_value, to_value, reason, session_ref)
VALUES (CAST(:id AS uuid), CAST(:field AS text), CAST(:from AS text), CAST(:to AS text), CAST(:reason AS text), CAST(:session_ref AS text))"""
Q["override_insert"] = """
INSERT INTO qualification_overrides (opportunity_id, check_code, override_result, reason, session_ref, expires_at)
VALUES (CAST(:id AS uuid), CAST(:check_code AS text), CAST(:result AS text), CAST(:reason AS text), CAST(:session_ref AS text),
        CAST(:expires_at AS timestamptz))
RETURNING id"""
Q["check_upsert"] = """
INSERT INTO qualification_checks (opportunity_id, check_code, result, blocking, rationale, evidence_refs)
VALUES (CAST(:id AS uuid), CAST(:code AS text), CAST(:result AS text), CAST(:blocking AS boolean), CAST(:rationale AS text),
        CAST(:evidence AS jsonb))
ON CONFLICT (opportunity_id, check_code) DO UPDATE
SET result = EXCLUDED.result, blocking = EXCLUDED.blocking, rationale = EXCLUDED.rationale,
    evidence_refs = EXCLUDED.evidence_refs, evaluated_at = now()"""
Q["expire_past_deadlines"] = """
WITH expired AS (
  UPDATE opportunities SET commercial_stage = 'expired'
  WHERE coalesce(deadline_latest_utc, deadline_utc) < now() AND commercial_stage IN ('new','reviewing','qualified','pursuing','proposal')
  RETURNING id
)
INSERT INTO opportunity_status_history (opportunity_id, field, from_value, to_value, reason)
SELECT id, 'commercial_stage', NULL, 'expired', 'deadline passed (automatic)' FROM expired"""

# ---------------------------------------------------------------- intelligence ingestion
Q["family_candidates"] = """
SELECT f.family_key, d.excerpt FROM announcement_families f
JOIN source_documents d ON d.announcement_family_id = f.id
WHERE d.retrieved_at > now() - interval '120 days'"""
Q["family_upsert"] = """
INSERT INTO announcement_families (family_key) VALUES (CAST(:key AS text))
ON CONFLICT (family_key) DO UPDATE SET family_key = EXCLUDED.family_key RETURNING id"""
Q["document_upsert"] = """
INSERT INTO source_documents (source_id, ingestion_run_id, announcement_family_id, original_url, canonical_url, publisher,
    published_at, event_date, retrieved_at, content_hash, content_type, byte_size, title, excerpt, page_ref, snapshot_path,
    parser_version, language, body_text, published_at_source, publication_flag, publication_note)
VALUES (CAST(:source_id AS uuid), CAST(:run_id AS uuid), CAST(:family_id AS uuid), CAST(:original_url AS text),
    CAST(:canonical_url AS text), CAST(:publisher AS text), CAST(:published_at AS timestamptz), CAST(:event_date AS date),
    now(), CAST(:content_hash AS text), CAST(:content_type AS text), CAST(:byte_size AS int), CAST(:title AS text),
    CAST(:excerpt AS text), CAST(:page_ref AS text), CAST(:snapshot_path AS text), CAST(:parser_version AS text),
    CAST(:language AS text), CAST(:body_text AS text), CAST(:published_at_source AS text), CAST(:publication_flag AS text),
    CAST(:publication_note AS text))
ON CONFLICT (canonical_url, content_hash) DO UPDATE SET retrieved_at = now(),
    published_at = coalesce(source_documents.published_at, EXCLUDED.published_at),
    published_at_source = CASE WHEN source_documents.published_at IS NULL THEN EXCLUDED.published_at_source
                               ELSE source_documents.published_at_source END,
    publication_flag = CASE WHEN source_documents.published_at IS NULL THEN EXCLUDED.publication_flag
                            ELSE source_documents.publication_flag END,
    publication_note = CASE WHEN source_documents.published_at IS NULL THEN EXCLUDED.publication_note
                            ELSE source_documents.publication_note END
RETURNING id, (xmax = 0) AS inserted"""
Q["document_check_add"] = """
INSERT INTO document_checks (source_document_id, check_type, result, detail)
VALUES (CAST(:doc AS uuid), CAST(:check_type AS text), CAST(:result AS text), CAST(:detail AS text))"""
# A corrected or rejected claim is never reused as the home of new evidence: a reviewer's replacement gets its own claim.
Q["claim_find"] = """SELECT id FROM claims WHERE claim_key = CAST(:key AS text) AND status <> 'superseded'
  AND review_status NOT IN ('corrected', 'rejected') ORDER BY created_at DESC LIMIT 1"""
Q["claim_insert"] = """
INSERT INTO claims (claim_type, claim_key, airline_id, territory_id, trade_lane_id, value, deadline_utc, deadline_source_tz)
VALUES (CAST(:claim_type AS text), CAST(:key AS text), CAST(:airline_id AS uuid), CAST(:territory_id AS uuid),
        CAST(:lane_id AS uuid), CAST(:value AS jsonb), CAST(:deadline AS timestamptz), CAST(:tz AS text))
RETURNING id"""
Q["claim_set_status"] = "UPDATE claims SET status = CAST(:status AS text) WHERE id = CAST(:id AS uuid)"
Q["claim_evidence_add"] = """
INSERT INTO claim_evidence (claim_id, source_document_id, stance, excerpt, page_ref, assessed_by)
VALUES (CAST(:claim AS uuid), CAST(:doc AS uuid), CAST(:stance AS text), CAST(:excerpt AS text), CAST(:page_ref AS text),
        CAST(:assessed_by AS text))
ON CONFLICT (claim_id, source_document_id, stance) DO NOTHING"""
Q["claim_links"] = """
SELECT ce.source_document_id::text AS document_id, f.family_key, coalesce(d.doc_authority, s.authority, 'unverified') AS authority, ce.stance,
       d.published_at,
       coalesce((SELECT dc.result FROM document_checks dc WHERE dc.source_document_id = d.id AND dc.check_type = 'authenticity'
                 ORDER BY dc.checked_at DESC LIMIT 1), 'unknown') AS authentic
FROM claim_evidence ce JOIN source_documents d ON d.id = ce.source_document_id
LEFT JOIN announcement_families f ON f.id = d.announcement_family_id
LEFT JOIN sources s ON s.id = d.source_id
WHERE ce.claim_id = CAST(:claim AS uuid) AND ce.excluded_at IS NULL"""
Q["signal_claim_evidence"] = """
SELECT c.id::text AS claim_id, c.claim_type, c.value, c.deadline_utc, c.deadline_source_tz, ce.stance,
       d.id::text AS document_id, d.published_at, d.retrieved_at, f.family_key, coalesce(d.doc_family, s.family, 'unknown') AS source_family,
       coalesce(d.doc_authority, s.authority, 'unverified') AS authority,
       coalesce((SELECT dc.result FROM document_checks dc WHERE dc.source_document_id = d.id AND dc.check_type = 'authenticity'
                 ORDER BY dc.checked_at DESC LIMIT 1), 'unknown') AS authentic
FROM signal_claims sc JOIN claims c ON c.id = sc.claim_id
JOIN claim_evidence ce ON ce.claim_id = c.id JOIN source_documents d ON d.id = ce.source_document_id
LEFT JOIN announcement_families f ON f.id = d.announcement_family_id LEFT JOIN sources s ON s.id = d.source_id
WHERE sc.signal_id = CAST(:signal AS uuid)
ORDER BY coalesce(d.published_at, d.retrieved_at)"""
Q["agreement_cells_for"] = """
SELECT ra.exclusivity, ra.appointment_rights, ra.status, ra.effective_from, ra.effective_to, oc.name AS operating_company
FROM representation_agreements ra JOIN operating_companies oc ON oc.id = ra.operating_company_id
JOIN agreement_territories at ON at.agreement_id = ra.id
WHERE ra.airline_id = CAST(:airline AS uuid) AND at.territory_id = CAST(:territory AS uuid)"""
Q["third_party_cells_for"] = """
SELECT tp.exclusivity, tp.valid_to, org.canonical_name AS holder, s.code AS service
FROM third_party_appointments tp LEFT JOIN organisations org ON org.id = tp.holder_organisation_id
LEFT JOIN services s ON s.id = tp.service_id
WHERE tp.airline_id = CAST(:airline AS uuid) AND tp.territory_id = CAST(:territory AS uuid)"""
Q["signal_upsert"] = """
INSERT INTO signals (module, classification, signal_key, title, summary, gaps)
VALUES (CAST(:module AS text), CAST(:classification AS text), CAST(:key AS text), CAST(:title AS text), CAST(:summary AS text),
        CAST(:gaps AS jsonb))
ON CONFLICT (module, signal_key) DO UPDATE
SET classification = EXCLUDED.classification, summary = EXCLUDED.summary, gaps = EXCLUDED.gaps
RETURNING id"""
Q["signal_claim_link"] = """
INSERT INTO signal_claims (signal_id, claim_id) VALUES (CAST(:signal AS uuid), CAST(:claim AS uuid)) ON CONFLICT DO NOTHING"""
Q["opportunity_by_key"] = """
SELECT id FROM opportunities WHERE module = CAST(:module AS text) AND dedup_key = CAST(:key AS text)"""
Q["opportunity_scope"] = """
SELECT o.id, o.deadline_utc, o.deadline_info, o.deadline_earliest_utc, o.deadline_latest_utc, o.operating_company_id, o.service_id,
       o.territory_id, o.station_airport_id, ap.iata_code AS station_code,
       o.delivery_start, o.required_credentials, o.signal_id, o.tender_status, o.module, o.freight_scope, o.tender_status_basis
FROM opportunities o LEFT JOIN airports ap ON ap.id = o.station_airport_id WHERE o.id = CAST(:id AS uuid)"""
Q["opportunity_set_scope"] = """
UPDATE opportunities SET operating_company_id = CAST(:company AS uuid), service_id = CAST(:service AS uuid)
WHERE id = CAST(:id AS uuid) RETURNING id"""
Q["capability_for_scope"] = """
SELECT oc.name AS operating_company, s.code AS service_code, ap.iata_code AS station, cr.status, cr.valid_from, cr.valid_to
FROM capability_records cr JOIN operating_companies oc ON oc.id = cr.operating_company_id JOIN services s ON s.id = cr.service_id
LEFT JOIN airports ap ON ap.id = cr.station_airport_id
WHERE cr.operating_company_id = CAST(:company AS uuid) AND cr.service_id = CAST(:service AS uuid)"""
Q["credentials_for_company"] = """
SELECT oc.name AS operating_company, tc.credential_type, tc.expires_on, tc.issued_on, ap.iata_code AS station
FROM training_credentials tc JOIN operating_companies oc ON oc.id = tc.operating_company_id
LEFT JOIN airports ap ON ap.id = tc.station_airport_id
WHERE tc.operating_company_id = CAST(:company AS uuid) AND (tc.service_id IS NULL OR tc.service_id = CAST(:service AS uuid))"""
Q["services_list"] = "SELECT id, code, name, category FROM services ORDER BY code"
Q["opportunity_upsert_from_signal"] = """
INSERT INTO opportunities (module, signal_id, dedup_key, title, airline_id, territory_id, service_id, deadline_utc, deadline_source_tz)
VALUES (CAST(:module AS text), CAST(:signal AS uuid), CAST(:key AS text), CAST(:title AS text), CAST(:airline_id AS uuid),
        CAST(:territory_id AS uuid), CAST(:service_id AS uuid), CAST(:deadline AS timestamptz), CAST(:tz AS text))
ON CONFLICT (module, dedup_key) DO UPDATE
SET deadline_utc = EXCLUDED.deadline_utc, deadline_source_tz = EXCLUDED.deadline_source_tz
RETURNING id, (xmax = 0) AS inserted"""

# ---------------------------------------------------------------- organisations / airlines & forwarders
Q["organisation_list"] = """
SELECT o.id, o.canonical_name, o.kind, o.country, a.iata_code, a.icao_code,
       (SELECT count(*) FROM representation_agreements ra WHERE ra.airline_id = o.id AND ra.status = 'active') AS active_agreements,
       (SELECT count(*) FROM bookings b WHERE b.forwarder_id = o.id)
         + (SELECT count(*) FROM bookings b WHERE b.airline_id = o.id) AS bookings,
       count(*) OVER () AS total
FROM organisations o LEFT JOIN airlines a ON a.organisation_id = o.id
WHERE o.merged_into_id IS NULL
  AND (CAST(:kind AS text) IS NULL OR o.kind = CAST(:kind AS text))
  AND (CAST(:q AS text) IS NULL OR o.canonical_name ILIKE '%' || CAST(:q AS text) || '%'
       OR EXISTS (SELECT 1 FROM organisation_aliases al WHERE al.organisation_id = o.id AND al.alias ILIKE '%' || CAST(:q AS text) || '%'))
ORDER BY o.canonical_name LIMIT CAST(:limit AS int) OFFSET CAST(:offset AS int)"""
Q["organisation_get"] = """
SELECT o.*, a.iata_code, a.icao_code, a.awb_prefix,
       (SELECT coalesce(json_agg(al.alias ORDER BY al.alias), '[]'::json) FROM organisation_aliases al WHERE al.organisation_id = o.id) AS aliases
FROM organisations o LEFT JOIN airlines a ON a.organisation_id = o.id WHERE o.id = CAST(:id AS uuid)"""
Q["agreements_for_airline"] = """
SELECT ra.id, ra.external_id, oc.name AS operating_company, ra.effective_from, ra.effective_to, ra.renewal_date, ra.notice_date,
       ra.exclusivity, ra.appointment_rights, ra.remuneration_model, ra.status,
       (SELECT coalesce(json_agg(t.code ORDER BY t.code), '[]'::json) FROM agreement_territories at JOIN territories t ON t.id = at.territory_id
         WHERE at.agreement_id = ra.id) AS territories,
       (SELECT coalesce(json_agg(s.code ORDER BY s.code), '[]'::json) FROM agreement_services asv JOIN services s ON s.id = asv.service_id
         WHERE asv.agreement_id = ra.id) AS services
FROM representation_agreements ra JOIN operating_companies oc ON oc.id = ra.operating_company_id
WHERE ra.airline_id = CAST(:airline AS uuid) ORDER BY ra.effective_from NULLS LAST"""
Q["third_party_for_airline"] = """
SELECT t.code AS territory, s.code AS service, org.canonical_name AS holder, tp.exclusivity, tp.valid_to
FROM third_party_appointments tp JOIN territories t ON t.id = tp.territory_id
LEFT JOIN services s ON s.id = tp.service_id LEFT JOIN organisations org ON org.id = tp.holder_organisation_id
WHERE tp.airline_id = CAST(:airline AS uuid)"""
Q["capabilities_all"] = """
SELECT cr.id, oc.name AS operating_company, s.code AS service_code, s.category, ap.iata_code AS station, cr.status,
       cr.verification_owner, cr.verified_at, cr.valid_from, cr.valid_to, cr.languages, cr.commodity_restrictions,
       cr.resource_constraints, cr.capacity_note
FROM capability_records cr JOIN operating_companies oc ON oc.id = cr.operating_company_id
JOIN services s ON s.id = cr.service_id LEFT JOIN airports ap ON ap.id = cr.station_airport_id
WHERE (CAST(:company AS uuid) IS NULL OR cr.operating_company_id = CAST(:company AS uuid))
ORDER BY oc.name, s.code, ap.iata_code NULLS FIRST"""
Q["credentials_all"] = """
SELECT tc.id, oc.name AS operating_company, tc.credential_type, tc.holder_description, tc.issued_on, tc.expires_on
FROM training_credentials tc JOIN operating_companies oc ON oc.id = tc.operating_company_id ORDER BY oc.name, tc.credential_type"""
Q["forwarder_monthly"] = """
SELECT date_trunc('month', b.flight_date)::date AS month, b.currency,
       sum(b.chargeable_weight_kg) FILTER (WHERE b.status <> 'cancelled') AS chargeable_kg,
       count(*) FILTER (WHERE b.status <> 'cancelled' AND b.chargeable_weight_kg IS NULL) AS missing_weight,
       sum(b.revenue) FILTER (WHERE b.status <> 'cancelled') AS revenue,
       count(*) FILTER (WHERE b.status <> 'cancelled') AS bookings
FROM bookings b WHERE b.forwarder_id = CAST(:forwarder AS uuid) AND b.flight_date IS NOT NULL
GROUP BY 1, 2 ORDER BY 1, 2"""
Q["forwarder_daily_weight"] = """
SELECT b.flight_date AS day,
       CASE WHEN bool_or(b.chargeable_weight_kg IS NULL) THEN NULL ELSE sum(b.chargeable_weight_kg) END AS kg
FROM bookings b WHERE b.forwarder_id = CAST(:forwarder AS uuid) AND b.status <> 'cancelled' AND b.flight_date IS NOT NULL
GROUP BY 1 ORDER BY 1"""
Q["forwarder_lost_reasons"] = """
SELECT coalesce(lost_reason, 'not recorded') AS reason, count(*) AS n FROM quotes
WHERE forwarder_id = CAST(:forwarder AS uuid) AND status = 'lost' AND quoted_at >= CAST(:since AS timestamptz)
GROUP BY 1 ORDER BY 2 DESC"""
Q["forwarder_accounts"] = """
SELECT o.id, o.canonical_name, min(b.flight_date) AS first_flight, max(b.flight_date) AS last_flight, count(b.id) AS bookings
FROM organisations o JOIN forwarders f ON f.organisation_id = o.id LEFT JOIN bookings b ON b.forwarder_id = o.id
GROUP BY o.id, o.canonical_name ORDER BY o.canonical_name"""

# ---------------------------------------------------------------- lanes and capacity
Q["lane_summary"] = """
SELECT l.id, oa.iata_code AS origin, da.iata_code AS destination,
       sum(b.chargeable_weight_kg) FILTER (WHERE b.status <> 'cancelled') AS chargeable_kg,
       sum(b.actual_weight_kg) FILTER (WHERE b.status <> 'cancelled') AS actual_kg,
       sum(b.volume_m3) FILTER (WHERE b.status <> 'cancelled') AS volume_m3,
       count(b.id) FILTER (WHERE b.status <> 'cancelled') AS bookings,
       count(b.id) FILTER (WHERE b.status <> 'cancelled' AND b.chargeable_weight_kg IS NULL) AS missing_chargeable,
       count(b.id) FILTER (WHERE b.status <> 'cancelled' AND b.actual_weight_kg IS NULL) AS missing_actual,
       count(b.id) FILTER (WHERE b.status <> 'cancelled' AND b.volume_m3 IS NULL) AS missing_volume,
       (SELECT count(*) FROM bookings u WHERE u.trade_lane_id = l.id AND u.flight_date IS NULL AND u.status <> 'cancelled') AS undated
FROM trade_lanes l JOIN airports oa ON oa.id = l.origin_airport_id JOIN airports da ON da.id = l.destination_airport_id
LEFT JOIN bookings b ON b.trade_lane_id = l.id AND b.flight_date BETWEEN CAST(:start AS date) AND CAST(:end AS date)
GROUP BY l.id, oa.iata_code, da.iata_code ORDER BY oa.iata_code, da.iata_code"""
Q["lane_bookings"] = """
SELECT b.external_id, b.flight_date, b.status, b.actual_weight_kg, b.chargeable_weight_kg, b.volume_m3, b.revenue, b.currency,
       b.fx_rate_to_reporting, b.fx_source, b.fx_date
FROM bookings b WHERE b.trade_lane_id = CAST(:lane AS uuid)
  AND (b.flight_date BETWEEN CAST(:start AS date) AND CAST(:end AS date) OR b.flight_date IS NULL)"""
Q["lane_capacity"] = """
SELECT c.period_start, c.period_end, c.basis, c.capacity_type, c.amount, c.snapshot_at, a.iata_code AS airline
FROM capacity_snapshots c LEFT JOIN airlines a ON a.organisation_id = c.airline_id
WHERE c.trade_lane_id = CAST(:lane AS uuid) AND c.period_start <= CAST(:end AS date) AND c.period_end >= CAST(:start AS date)
ORDER BY c.period_start"""
Q["lane_get"] = """
SELECT l.id, oa.iata_code AS origin, da.iata_code AS destination FROM trade_lanes l
JOIN airports oa ON oa.id = l.origin_airport_id JOIN airports da ON da.id = l.destination_airport_id WHERE l.id = CAST(:lane AS uuid)"""

# ---------------------------------------------------------------- service and operations
Q["exceptions_list"] = """
SELECT e.id, e.exception_type, e.severity, e.description, e.status, e.deadline_utc, e.opened_at, e.resolved_at,
       org.canonical_name AS customer, oc.name AS operating_company, e.owner_person_id, own.full_name AS owner, count(*) OVER () AS total
FROM operational_exceptions e LEFT JOIN organisations org ON org.id = e.customer_organisation_id
LEFT JOIN operating_companies oc ON oc.id = e.operating_company_id LEFT JOIN people own ON own.id = e.owner_person_id
WHERE (CAST(:status AS text) IS NULL OR (CAST(:status AS text) = 'active' AND e.status <> 'resolved') OR e.status = CAST(:status AS text))
ORDER BY CASE e.severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END, e.deadline_utc NULLS LAST
LIMIT CAST(:limit AS int) OFFSET CAST(:offset AS int)"""
Q["exception_history"] = """
SELECT from_status, to_status, note, changed_at FROM operational_exception_history
WHERE exception_id = CAST(:id AS uuid) ORDER BY changed_at"""
Q["exception_open"] = """
INSERT INTO operational_exceptions (source_id, external_id, dedup_key, exception_type, severity, customer_organisation_id,
    operating_company_id, description, deadline_utc)
VALUES (CAST(:source_id AS uuid), CAST(:external_id AS text), CAST(:key AS text), CAST(:type AS text), CAST(:severity AS text),
    CAST(:customer AS uuid), CAST(:company AS uuid), CAST(:description AS text), CAST(:deadline AS timestamptz))
ON CONFLICT (dedup_key) WHERE status <> 'resolved' DO UPDATE
SET severity = CASE WHEN array_position(ARRAY['low','medium','high','critical'], EXCLUDED.severity)
                       > array_position(ARRAY['low','medium','high','critical'], operational_exceptions.severity)
                    THEN EXCLUDED.severity ELSE operational_exceptions.severity END
RETURNING id, (xmax = 0) AS inserted"""
Q["exception_history_add"] = """
INSERT INTO operational_exception_history (exception_id, from_status, to_status, note)
VALUES (CAST(:id AS uuid), CAST(:from AS text), CAST(:to AS text), CAST(:note AS text))"""
Q["exception_resolve"] = """
UPDATE operational_exceptions SET status = 'resolved', resolved_at = now()
WHERE id = CAST(:id AS uuid) AND status <> 'resolved' RETURNING status"""
Q["task_upsert"] = """
INSERT INTO tasks (dedup_key, title, source_type, source_id, owner_person_id, due_at_utc)
VALUES (CAST(:key AS text), CAST(:title AS text), CAST(:source_type AS text), CAST(:source_id AS uuid),
        CAST(:owner AS uuid), CAST(:due AS timestamptz))
ON CONFLICT (dedup_key) DO NOTHING RETURNING id"""
Q["task_close_for_source"] = """
UPDATE tasks SET status = 'done', completed_at = now()
WHERE source_type = CAST(:source_type AS text) AND source_id = CAST(:source_id AS uuid) AND status IN ('open','in_progress')"""
Q["notification_upsert"] = """
INSERT INTO notifications (dedup_key, kind, title, body, entity_type, entity_id)
VALUES (CAST(:key AS text), CAST(:kind AS text), CAST(:title AS text), CAST(:body AS text), CAST(:entity_type AS text),
        CAST(:entity_id AS uuid))
ON CONFLICT (dedup_key) DO NOTHING RETURNING id"""
Q["notifications_list"] = """
SELECT id, kind, title, body, entity_type, entity_id, delivery_state, created_at, read_at
FROM notifications ORDER BY created_at DESC LIMIT CAST(:limit AS int)"""

Q["existing_exception_reports"] = """
SELECT external_id, report FROM exception_reports WHERE source_id = CAST(:source AS uuid)"""
Q["exception_report_upsert"] = """
INSERT INTO exception_reports (source_id, external_id, exception_id, report)
VALUES (CAST(:source AS uuid), CAST(:external_id AS text), CAST(:exception AS uuid), CAST(:report AS jsonb))
ON CONFLICT (source_id, external_id) DO UPDATE SET exception_id = EXCLUDED.exception_id, report = EXCLUDED.report, updated_at = now()"""
Q["exception_for_report"] = """
SELECT exception_id FROM exception_reports WHERE source_id = CAST(:source AS uuid) AND external_id = CAST(:external_id AS text)"""

# ---------------------------------------------------------------- trucking
Q["feeders_list"] = """
SELECT r.id, org.canonical_name AS provider, st.code AS origin_station, st.is_offline, ap.iata_code AS gateway,
       r.departure_days, r.departure_time_local, r.transit_minutes, r.restrictions
FROM road_feeder_services r JOIN stations st ON st.id = r.origin_station_id JOIN airports ap ON ap.id = r.gateway_airport_id
LEFT JOIN organisations org ON org.id = r.provider_organisation_id ORDER BY st.code, ap.iata_code"""
Q["gateway_connections_for"] = """
SELECT gc.id, ap.iata_code AS gateway, gc.departure_days, gc.departure_time_local, gc.connection_cutoff_minutes,
       a.iata_code AS airline
FROM gateway_connections gc JOIN airports ap ON ap.id = gc.gateway_airport_id LEFT JOIN airlines a ON a.organisation_id = gc.airline_id
WHERE ap.iata_code = CAST(:gateway AS text)"""

# ---------------------------------------------------------------- relationships
Q["people_list"] = """
SELECT p.id, p.full_name, p.role_title, p.is_internal, org.canonical_name AS organisation, oc.name AS operating_company,
       (SELECT max(e.occurred_at) FROM engagements e WHERE e.person_id = p.id) AS last_engagement,
       count(*) OVER () AS total
FROM people p LEFT JOIN organisations org ON org.id = p.organisation_id LEFT JOIN operating_companies oc ON oc.id = p.operating_company_id
WHERE (CAST(:q AS text) IS NULL OR p.full_name ILIKE '%' || CAST(:q AS text) || '%')
ORDER BY p.full_name LIMIT CAST(:limit AS int) OFFSET CAST(:offset AS int)"""
Q["person_insert"] = """
INSERT INTO people (full_name, role_title, organisation_id, operating_company_id, email, is_internal)
VALUES (CAST(:full_name AS text), CAST(:role_title AS text), CAST(:organisation_id AS uuid), CAST(:company_id AS uuid),
        CAST(:email AS text), CAST(:is_internal AS boolean)) RETURNING id"""
Q["engagements_for_org"] = """
SELECT e.id, e.occurred_at, e.kind, e.summary, p.full_name AS person FROM engagements e LEFT JOIN people p ON p.id = e.person_id
WHERE e.organisation_id = CAST(:org AS uuid) ORDER BY e.occurred_at DESC LIMIT 100"""
Q["engagement_insert"] = """
INSERT INTO engagements (organisation_id, person_id, opportunity_id, occurred_at, kind, summary)
VALUES (CAST(:org AS uuid), CAST(:person AS uuid), CAST(:opp AS uuid), CAST(:at AS timestamptz), CAST(:kind AS text),
        CAST(:summary AS text)) RETURNING id"""
Q["tasks_list"] = """
SELECT t.id, t.title, t.source_type, t.source_id, t.status, t.due_at_utc, p.full_name AS owner, t.created_at
FROM tasks t LEFT JOIN people p ON p.id = t.owner_person_id
WHERE (CAST(:status AS text) IS NULL OR t.status = CAST(:status AS text))
ORDER BY t.due_at_utc NULLS LAST, t.created_at LIMIT CAST(:limit AS int)"""
Q["task_set_status"] = """
UPDATE tasks SET status = CAST(:status AS text),
       completed_at = CASE WHEN CAST(:status AS text) IN ('done','cancelled') THEN now() ELSE NULL END
WHERE id = CAST(:id AS uuid) RETURNING id"""

# ---------------------------------------------------------------- network development
Q["network_list"] = """
SELECT n.id, n.kind, n.title, n.status, n.organisation_id, org.canonical_name AS organisation, t.code AS territory, s.code AS service,
       (SELECT row_to_json(fa) FROM (SELECT id, result, rationale, assessed_at, trigger, organisation_id, gaps, basis FROM fit_assessments f
         WHERE f.network_candidate_id = n.id ORDER BY assessed_at DESC LIMIT 1) fa) AS latest_fit,
       (SELECT coalesce(json_agg(json_build_object('signal_id', sg.id, 'title', sg.title, 'classification', sg.classification)), '[]'::json)
          FROM network_candidate_signals ns JOIN signals sg ON sg.id = ns.signal_id WHERE ns.candidate_id = n.id) AS evidence
FROM network_candidates n LEFT JOIN organisations org ON org.id = n.organisation_id
LEFT JOIN territories t ON t.id = n.territory_id LEFT JOIN services s ON s.id = n.service_id
WHERE (CAST(:kind AS text) IS NULL OR n.kind = CAST(:kind AS text)) ORDER BY n.created_at DESC"""
Q["network_insert"] = """
INSERT INTO network_candidates (kind, organisation_id, territory_id, service_id, title)
VALUES (CAST(:kind AS text), CAST(:org AS uuid), CAST(:territory AS uuid), CAST(:service AS uuid), CAST(:title AS text))
RETURNING id"""
Q["fit_insert2"] = """
INSERT INTO fit_assessments (network_candidate_id, result, rationale, evidence_claim_ids, organisation_id, gaps, basis, trigger, supersedes_id)
VALUES (CAST(:id AS uuid), CAST(:result AS text), CAST(:rationale AS jsonb), CAST(:claims AS uuid[]), CAST(:org AS uuid),
        CAST(:gaps AS jsonb), CAST(:basis AS jsonb), CAST(:trigger AS text), CAST(:supersedes AS uuid)) RETURNING id"""
Q["fit_latest_all"] = """
SELECT DISTINCT ON (f.network_candidate_id) f.id, f.network_candidate_id, f.organisation_id, f.gaps, f.basis, f.result, f.assessed_at
FROM fit_assessments f WHERE f.organisation_id IS NOT NULL ORDER BY f.network_candidate_id, f.assessed_at DESC, f.id"""
Q["fit_latest"] = """
SELECT f.id, f.network_candidate_id, f.organisation_id, f.gaps, f.basis, f.result, f.rationale, f.assessed_at, f.trigger
FROM fit_assessments f WHERE f.network_candidate_id = CAST(:id AS uuid) ORDER BY f.assessed_at DESC, f.id LIMIT 1"""
Q["network_candidate_get"] = "SELECT id, kind, organisation_id FROM network_candidates WHERE id = CAST(:id AS uuid)"
# (territory code, service code) pairs WFC's own ACTIVE agreements cover today.
Q["agreement_coverage_pairs"] = """
SELECT DISTINCT t.code AS territory, s.code AS service
FROM representation_agreements a JOIN agreement_territories at ON at.agreement_id = a.id JOIN territories t ON t.id = at.territory_id
JOIN agreement_services asv ON asv.agreement_id = a.id JOIN services s ON s.id = asv.service_id
WHERE a.status = 'active' AND (a.effective_from IS NULL OR a.effective_from <= current_date)
  AND (a.effective_to IS NULL OR a.effective_to >= current_date)"""
Q["fit_insert"] = """
INSERT INTO fit_assessments (network_candidate_id, result, rationale, evidence_claim_ids)
VALUES (CAST(:id AS uuid), CAST(:result AS text), CAST(:rationale AS jsonb), CAST(:claims AS uuid[])) RETURNING id"""
Q["partner_claims"] = """
SELECT c.id::text AS claim_id, c.value->>'kind' AS claim_kind, c.value->>'value' AS value, c.status
FROM claims c WHERE c.subject_organisation_id = CAST(:org AS uuid) AND c.claim_type = 'partnership'"""

# ---------------------------------------------------------------- reports
Q["values_for_pipeline"] = """
SELECT o.id::text AS opportunity_id, cv.currency, cv.airline_revenue, cv.wfc_remuneration, cv.incremental_costs,
       cv.guarantee_exposure, cv.basis, cv.assumptions, cv.value_kind, o.competition_group_id::text AS competition_group,
       o.module, oc.name AS operating_company
FROM opportunities o JOIN commercial_values cv ON cv.opportunity_id = o.id
LEFT JOIN operating_companies oc ON oc.id = o.operating_company_id
WHERE (CAST(:company AS uuid) IS NULL OR o.operating_company_id = CAST(:company AS uuid))
  AND (CAST(:module AS text) IS NULL OR o.module = CAST(:module AS text))"""
Q["referral_receivers"] = "SELECT opportunity_id::text, to_company_id::text FROM referrals WHERE status IN ('accepted','closed')"
Q["operating_companies"] = "SELECT id, name, legal_entity_name, country FROM operating_companies ORDER BY name"

# ---------------------------------------------------------------- data sources and imports
Q["connectors_list"] = """
SELECT id, code, name, kind, status, credential_ref, permitted_scope, capabilities, last_success_at, last_error FROM connectors ORDER BY name"""
Q["connector_upsert"] = """
INSERT INTO connectors (code, name, kind, status, credential_ref, permitted_scope, capabilities)
VALUES (CAST(:code AS text), CAST(:name AS text), CAST(:kind AS text), CAST(:status AS text), CAST(:credential_ref AS text),
        CAST(:scope AS text), CAST(:capabilities AS jsonb))
ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name, kind = EXCLUDED.kind, capabilities = EXCLUDED.capabilities,
    credential_ref = EXCLUDED.credential_ref, permitted_scope = EXCLUDED.permitted_scope
RETURNING id"""
Q["connector_set_status"] = """
UPDATE connectors SET status = CAST(:status AS text), last_error = CAST(:error AS text),
       last_success_at = CASE WHEN CAST(:status AS text) = 'healthy' THEN now() ELSE last_success_at END
WHERE code = CAST(:code AS text)"""
Q["source_for_dataset"] = """
SELECT id FROM sources WHERE name = CAST(:name AS text) LIMIT 1"""
Q["source_insert"] = """
INSERT INTO sources (connector_id, name, family, base_url, authority, authorisation_note, retention_permitted, enabled,
                     freshness_sla_hours)
VALUES (CAST(:connector_id AS uuid), CAST(:name AS text), CAST(:family AS text), CAST(:base_url AS text), CAST(:authority AS text),
        CAST(:note AS text), CAST(:retention AS boolean), CAST(:enabled AS boolean), CAST(:sla AS int))
RETURNING id"""
Q["source_get"] = "SELECT * FROM sources WHERE id = CAST(:id AS uuid)"
Q["source_set_enabled"] = "UPDATE sources SET enabled = CAST(:enabled AS boolean) WHERE id = CAST(:id AS uuid) RETURNING id"
Q["ingestion_run_start"] = "INSERT INTO ingestion_runs (source_id, job_id) VALUES (CAST(:source AS uuid), CAST(:job AS uuid)) RETURNING id"
Q["ingestion_run_finish"] = """
UPDATE ingestion_runs SET finished_at = now(), status = CAST(:status AS text), stats = CAST(:stats AS jsonb)
WHERE id = CAST(:id AS uuid)"""
Q["import_job_insert"] = """
INSERT INTO import_jobs (dataset, source_id, file_name, file_sha256, schema_version, mapping, mode, status, totals, session_ref)
VALUES (CAST(:dataset AS text), CAST(:source_id AS uuid), CAST(:file_name AS text), CAST(:sha AS text), CAST(:schema_version AS text),
        CAST(:mapping AS jsonb), CAST(:mode AS text), CAST(:status AS text), CAST(:totals AS jsonb), CAST(:session_ref AS text))
RETURNING id"""
Q["import_job_committed"] = """
UPDATE import_jobs SET status = 'committed', committed_at = now(), totals = CAST(:totals AS jsonb) WHERE id = CAST(:id AS uuid)"""
Q["import_job_reversed"] = """
UPDATE import_jobs SET status = 'reversed', reversed_at = now(), reversal_reason = CAST(:reason AS text)
WHERE id = CAST(:id AS uuid) AND status = 'committed' RETURNING id"""
Q["import_jobs_list"] = """
SELECT id, dataset, file_name, file_sha256, mode, status, totals, created_at, committed_at, reversed_at, partial, preview_job_id,
       (SELECT c.id FROM import_jobs c WHERE c.preview_job_id = j.id AND c.mode = 'commit' LIMIT 1) AS committed_as
FROM import_jobs j WHERE (CAST(:dataset AS text) IS NULL OR dataset = CAST(:dataset AS text))
ORDER BY created_at DESC LIMIT CAST(:limit AS int)"""
Q["import_job_get"] = "SELECT * FROM import_jobs WHERE id = CAST(:id AS uuid)"
Q["import_error_add"] = """
INSERT INTO import_row_errors (import_job_id, row_number, field, error_code, message, raw_row)
VALUES (CAST(:job AS uuid), CAST(:row AS int), CAST(:field AS text), CAST(:code AS text), CAST(:message AS text), CAST(:raw AS jsonb))"""
Q["import_errors"] = """
SELECT row_number, field, error_code, message, raw_row FROM import_row_errors WHERE import_job_id = CAST(:job AS uuid)
ORDER BY row_number LIMIT 1000"""
Q["import_effect_add"] = """
INSERT INTO import_row_effects (import_job_id, row_number, target_table, target_id, action, previous)
VALUES (CAST(:job AS uuid), CAST(:row AS int), CAST(:table AS text), CAST(:target AS uuid), CAST(:action AS text),
        CAST(:previous AS jsonb))"""
Q["import_later_conflicts"] = """
SELECT count(*) AS n FROM import_row_effects e
JOIN import_jobs j ON j.id = e.import_job_id
WHERE j.status = 'committed' AND j.created_at > (SELECT created_at FROM import_jobs WHERE id = CAST(:job AS uuid))
  AND e.target_id IN (SELECT target_id FROM import_row_effects WHERE import_job_id = CAST(:job AS uuid))
  AND e.action <> 'unchanged'"""
Q["import_effects"] = """
SELECT row_number, target_table, target_id, action, previous FROM import_row_effects WHERE import_job_id = CAST(:job AS uuid)
ORDER BY row_number"""
Q["provenance_insert"] = """
INSERT INTO provenance (kind, import_job_id, import_row_number, source_document_id, note)
VALUES (CAST(:kind AS text), CAST(:job AS uuid), CAST(:row AS int), CAST(:doc AS uuid), CAST(:note AS text)) RETURNING id"""
Q["existing_bookings"] = """
SELECT b.id, b.external_id, f.canonical_name AS forwarder, a.iata_code AS airline_iata, oa.iata_code AS origin,
       da.iata_code AS destination, b.flight_date, b.booked_at, b.status, b.actual_weight_kg AS actual_weight,
       b.chargeable_weight_kg AS chargeable_weight, b.volume_m3 AS volume, b.revenue, b.currency,
       oc.name AS operating_company
FROM bookings b LEFT JOIN organisations f ON f.id = b.forwarder_id LEFT JOIN airlines a ON a.organisation_id = b.airline_id
LEFT JOIN trade_lanes l ON l.id = b.trade_lane_id LEFT JOIN airports oa ON oa.id = l.origin_airport_id
LEFT JOIN airports da ON da.id = l.destination_airport_id LEFT JOIN operating_companies oc ON oc.id = b.operating_company_id
WHERE b.source_id = CAST(:source AS uuid)"""
Q["airport_id"] = "SELECT id FROM airports WHERE iata_code = CAST(:code AS text)"
Q["airport_ensure_unknown"] = """
SELECT id FROM airports WHERE iata_code = CAST(:code AS text)"""
Q["lane_ensure"] = """
INSERT INTO trade_lanes (origin_airport_id, destination_airport_id) VALUES (CAST(:o AS uuid), CAST(:d AS uuid))
ON CONFLICT (origin_airport_id, destination_airport_id) DO UPDATE SET origin_airport_id = EXCLUDED.origin_airport_id
RETURNING id"""
Q["org_by_name"] = """
SELECT o.id FROM organisations o WHERE o.merged_into_id IS NULL AND (lower(o.canonical_name) = lower(CAST(:name AS text))
   OR EXISTS (SELECT 1 FROM organisation_aliases al WHERE al.organisation_id = o.id AND al.alias_norm = CAST(:norm AS text)))
ORDER BY o.created_at LIMIT 1"""
Q["org_insert"] = """
INSERT INTO organisations (canonical_name, kind, provenance_id) VALUES (CAST(:name AS text), CAST(:kind AS text), CAST(:prov AS uuid))
RETURNING id"""
Q["alias_insert"] = """
INSERT INTO organisation_aliases (organisation_id, alias, alias_norm, provenance_id)
VALUES (CAST(:org AS uuid), CAST(:alias AS text), CAST(:norm AS text), CAST(:prov AS uuid)) ON CONFLICT DO NOTHING"""
Q["forwarder_ensure"] = "INSERT INTO forwarders (organisation_id) VALUES (CAST(:org AS uuid)) ON CONFLICT DO NOTHING"
Q["airline_by_iata"] = "SELECT organisation_id AS id FROM airlines WHERE iata_code = CAST(:code AS text) LIMIT 1"
Q["company_by_name"] = "SELECT id FROM operating_companies WHERE lower(name) = lower(CAST(:name AS text))"
Q["booking_upsert"] = """
INSERT INTO bookings (source_id, external_id, forwarder_id, airline_id, trade_lane_id, operating_company_id, flight_date, booked_at,
    status, actual_weight_kg, chargeable_weight_kg, volume_m3, revenue, currency, provenance_id)
VALUES (CAST(:source AS uuid), CAST(:external_id AS text), CAST(:forwarder AS uuid), CAST(:airline AS uuid), CAST(:lane AS uuid),
    CAST(:company AS uuid), CAST(:flight_date AS date), CAST(:booked_at AS timestamptz), CAST(:status AS text),
    CAST(:actual AS numeric), CAST(:chargeable AS numeric), CAST(:volume AS numeric), CAST(:revenue AS numeric),
    CAST(:currency AS text), CAST(:prov AS uuid))
ON CONFLICT (source_id, external_id) DO UPDATE SET
    forwarder_id = EXCLUDED.forwarder_id, airline_id = EXCLUDED.airline_id, trade_lane_id = EXCLUDED.trade_lane_id,
    operating_company_id = EXCLUDED.operating_company_id, flight_date = EXCLUDED.flight_date, booked_at = EXCLUDED.booked_at,
    status = EXCLUDED.status, actual_weight_kg = EXCLUDED.actual_weight_kg, chargeable_weight_kg = EXCLUDED.chargeable_weight_kg,
    volume_m3 = EXCLUDED.volume_m3, revenue = EXCLUDED.revenue, currency = EXCLUDED.currency, provenance_id = EXCLUDED.provenance_id
RETURNING id"""
Q["booking_delete"] = "DELETE FROM bookings WHERE id = CAST(:id AS uuid)"

Q["service_by_code"] = "SELECT id FROM services WHERE code = upper(CAST(:code AS text))"
Q["territory_ensure"] = """
INSERT INTO territories (code, name, kind) VALUES (upper(CAST(:code AS text)), upper(CAST(:code AS text)), CAST(:kind AS text))
ON CONFLICT (code) DO UPDATE SET code = EXCLUDED.code RETURNING id"""
Q["company_ensure"] = """
INSERT INTO operating_companies (name, provenance_id) VALUES (CAST(:name AS text), CAST(:prov AS uuid))
ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name RETURNING id"""
Q["airline_insert"] = """
INSERT INTO airlines (organisation_id, iata_code) VALUES (CAST(:org AS uuid), upper(CAST(:iata AS text))) ON CONFLICT DO NOTHING"""
Q["agreement_upsert"] = """
INSERT INTO representation_agreements (external_id, airline_id, operating_company_id, effective_from, effective_to, renewal_date,
    notice_date, exclusivity, appointment_rights, remuneration_model, provenance_id)
VALUES (CAST(:external_id AS text), CAST(:airline AS uuid), CAST(:company AS uuid), CAST(:effective_from AS date),
    CAST(:effective_to AS date), CAST(:renewal_date AS date), CAST(:notice_date AS date), coalesce(CAST(:exclusivity AS text), 'unknown'),
    coalesce(CAST(:appointment_rights AS text), 'unknown'), coalesce(CAST(:remuneration_model AS text), 'unknown'), CAST(:prov AS uuid))
ON CONFLICT (external_id) DO UPDATE SET airline_id = EXCLUDED.airline_id, operating_company_id = EXCLUDED.operating_company_id,
    effective_from = EXCLUDED.effective_from, effective_to = EXCLUDED.effective_to, renewal_date = EXCLUDED.renewal_date,
    notice_date = EXCLUDED.notice_date, exclusivity = EXCLUDED.exclusivity, appointment_rights = EXCLUDED.appointment_rights,
    remuneration_model = EXCLUDED.remuneration_model, provenance_id = EXCLUDED.provenance_id
RETURNING id"""
Q["agreement_clear_scope"] = """
WITH t AS (DELETE FROM agreement_territories WHERE agreement_id = CAST(:id AS uuid) RETURNING 1)
DELETE FROM agreement_services WHERE agreement_id = CAST(:id AS uuid)"""
Q["agreement_add_territory"] = """
INSERT INTO agreement_territories (agreement_id, territory_id) VALUES (CAST(:id AS uuid), CAST(:territory AS uuid)) ON CONFLICT DO NOTHING"""
Q["agreement_add_service"] = """
INSERT INTO agreement_services (agreement_id, service_id) VALUES (CAST(:id AS uuid), CAST(:service AS uuid)) ON CONFLICT DO NOTHING"""
Q["existing_agreements"] = """
SELECT ra.external_id, a.iata_code AS airline_iata, org.canonical_name AS airline_name, oc.name AS operating_company,
       (SELECT string_agg(t.code, ';' ORDER BY t.code) FROM agreement_territories x JOIN territories t ON t.id = x.territory_id WHERE x.agreement_id = ra.id) AS territories,
       (SELECT string_agg(s.code, ';' ORDER BY s.code) FROM agreement_services x JOIN services s ON s.id = x.service_id WHERE x.agreement_id = ra.id) AS services,
       ra.effective_from, ra.effective_to, ra.renewal_date, ra.notice_date, NULLIF(ra.exclusivity, 'unknown') AS exclusivity,
       NULLIF(ra.appointment_rights, 'unknown') AS appointment_rights, NULLIF(ra.remuneration_model, 'unknown') AS remuneration_model
FROM representation_agreements ra JOIN airlines a ON a.organisation_id = ra.airline_id JOIN organisations org ON org.id = ra.airline_id
JOIN operating_companies oc ON oc.id = ra.operating_company_id WHERE ra.external_id IS NOT NULL"""
Q["capability_upsert"] = """
INSERT INTO capability_records (operating_company_id, service_id, station_airport_id, status, verification_owner, valid_from, valid_to,
    languages, commodity_restrictions, provenance_id)
VALUES (CAST(:company AS uuid), CAST(:service AS uuid), CAST(:station AS uuid), CAST(:status AS text), CAST(:owner AS text),
    CAST(:valid_from AS date), CAST(:valid_to AS date), CAST(:languages AS text[]), CAST(:restrictions AS text), CAST(:prov AS uuid))
ON CONFLICT (operating_company_id, service_id, (coalesce(station_airport_id, '00000000-0000-0000-0000-000000000000'::uuid)))
DO UPDATE SET status = EXCLUDED.status, verification_owner = EXCLUDED.verification_owner, valid_from = EXCLUDED.valid_from,
    valid_to = EXCLUDED.valid_to, languages = EXCLUDED.languages, commodity_restrictions = EXCLUDED.commodity_restrictions,
    provenance_id = EXCLUDED.provenance_id
RETURNING id"""
Q["existing_capabilities"] = """
SELECT oc.name AS operating_company, s.code AS service_code, ap.iata_code AS station, cr.status, cr.verification_owner,
       cr.valid_from, cr.valid_to, array_to_string(cr.languages, ';') AS languages, cr.commodity_restrictions
FROM capability_records cr JOIN operating_companies oc ON oc.id = cr.operating_company_id JOIN services s ON s.id = cr.service_id
LEFT JOIN airports ap ON ap.id = cr.station_airport_id"""
Q["capacity_upsert"] = """
INSERT INTO capacity_snapshots (source_id, external_id, airline_id, trade_lane_id, flight_number, period_start, period_end, basis,
    capacity_type, amount, snapshot_at, provenance_id)
VALUES (CAST(:source AS uuid), CAST(:external_id AS text), CAST(:airline AS uuid), CAST(:lane AS uuid), CAST(:flight_number AS text),
    CAST(:period_start AS date), CAST(:period_end AS date), CAST(:basis AS text), CAST(:capacity_type AS text), CAST(:amount AS numeric),
    CAST(:snapshot_at AS timestamptz), CAST(:prov AS uuid))
ON CONFLICT (source_id, external_id) DO UPDATE SET airline_id = EXCLUDED.airline_id, trade_lane_id = EXCLUDED.trade_lane_id,
    flight_number = EXCLUDED.flight_number, period_start = EXCLUDED.period_start, period_end = EXCLUDED.period_end,
    basis = EXCLUDED.basis, capacity_type = EXCLUDED.capacity_type, amount = EXCLUDED.amount, snapshot_at = EXCLUDED.snapshot_at,
    provenance_id = EXCLUDED.provenance_id
RETURNING id"""
Q["existing_capacity"] = """
SELECT c.external_id, a.iata_code AS airline_iata, oa.iata_code AS origin, da.iata_code AS destination, c.flight_number,
       c.period_start, c.period_end, c.basis, c.capacity_type, c.amount, c.snapshot_at
FROM capacity_snapshots c LEFT JOIN airlines a ON a.organisation_id = c.airline_id JOIN trade_lanes l ON l.id = c.trade_lane_id
JOIN airports oa ON oa.id = l.origin_airport_id JOIN airports da ON da.id = l.destination_airport_id
WHERE c.source_id = CAST(:source AS uuid)"""
Q["quote_upsert"] = """
INSERT INTO quotes (source_id, external_id, forwarder_id, trade_lane_id, quoted_at, status, lost_reason, chargeable_weight_kg, amount,
    currency, owner_person_id, provenance_id)
VALUES (CAST(:source AS uuid), CAST(:external_id AS text), CAST(:forwarder AS uuid), CAST(:lane AS uuid), CAST(:quoted_at AS timestamptz),
    CAST(:status AS text), CAST(:lost_reason AS text), CAST(:chargeable AS numeric), CAST(:amount AS numeric), CAST(:currency AS text),
    CAST(:owner AS uuid), CAST(:prov AS uuid))
ON CONFLICT (source_id, external_id) DO UPDATE SET forwarder_id = EXCLUDED.forwarder_id, trade_lane_id = EXCLUDED.trade_lane_id,
    quoted_at = EXCLUDED.quoted_at, status = EXCLUDED.status, lost_reason = EXCLUDED.lost_reason,
    chargeable_weight_kg = EXCLUDED.chargeable_weight_kg, amount = EXCLUDED.amount, currency = EXCLUDED.currency,
    owner_person_id = EXCLUDED.owner_person_id, provenance_id = EXCLUDED.provenance_id
RETURNING id"""
Q["existing_quotes"] = """
SELECT q.external_id, f.canonical_name AS forwarder, oa.iata_code AS origin, da.iata_code AS destination, q.quoted_at, q.status,
       q.lost_reason, q.chargeable_weight_kg AS chargeable_weight, q.amount, q.currency, p.full_name AS owner
FROM quotes q LEFT JOIN organisations f ON f.id = q.forwarder_id LEFT JOIN trade_lanes l ON l.id = q.trade_lane_id
LEFT JOIN airports oa ON oa.id = l.origin_airport_id LEFT JOIN airports da ON da.id = l.destination_airport_id
LEFT JOIN people p ON p.id = q.owner_person_id WHERE q.source_id = CAST(:source AS uuid)"""
Q["person_by_name"] = "SELECT id FROM people WHERE lower(full_name) = lower(CAST(:name AS text)) ORDER BY created_at LIMIT 1"

# ---------------------------------------------------------------- settings, automation
Q["schedules_list"] = """
SELECT s.id, s.name, s.job_type, src.name AS source, s.scope_source_id, ds.name AS search, s.scope_search_id, s.scope_region,
       s.scope_module, s.interval_minutes, s.timezone, s.overlap_policy, s.enabled, s.next_run_at, s.last_success_at, s.last_failure_at
FROM schedules s LEFT JOIN sources src ON src.id = s.scope_source_id LEFT JOIN discovery_searches ds ON ds.id = s.scope_search_id
ORDER BY s.job_type, coalesce(s.name, src.name)"""
Q["schedule_set_enabled"] = "UPDATE schedules SET enabled = CAST(:enabled AS boolean) WHERE id = CAST(:id AS uuid) RETURNING id"
Q["schedules_due"] = """
SELECT s.id, s.job_type, s.scope_source_id, s.scope_search_id, s.scope_module, s.interval_minutes, s.timezone, s.overlap_policy
FROM schedules s WHERE s.enabled AND (s.next_run_at IS NULL OR s.next_run_at <= now())"""
Q["schedule_has_running"] = """
SELECT EXISTS (SELECT 1 FROM jobs WHERE schedule_id = CAST(:id AS uuid) AND status IN ('queued','running'))"""
Q["schedule_advance"] = """
UPDATE schedules SET next_run_at = CAST(:next AS timestamptz) WHERE id = CAST(:id AS uuid)"""
Q["schedule_mark"] = """
UPDATE schedules SET last_success_at = CASE WHEN CAST(:ok AS boolean) THEN now() ELSE last_success_at END,
       last_failure_at = CASE WHEN CAST(:ok AS boolean) THEN last_failure_at ELSE now() END
WHERE id = CAST(:id AS uuid)"""
Q["job_enqueue"] = """
INSERT INTO jobs (job_type, execution_key, schedule_id, payload, run_after, estimated_cost)
VALUES (CAST(:job_type AS text), CAST(:key AS text), CAST(:schedule AS uuid), CAST(:payload AS jsonb),
        coalesce(CAST(:run_after AS timestamptz), now()), CAST(:estimated_cost AS numeric))
ON CONFLICT (execution_key) DO NOTHING RETURNING id"""
Q["job_claim"] = "SELECT * FROM claim_next_job(CAST(:worker AS text), CAST(:lease AS int))"
Q["job_attempt_start"] = """
INSERT INTO job_attempts (job_id, attempt, worker) VALUES (CAST(:job AS uuid), CAST(:attempt AS int), CAST(:worker AS text))
ON CONFLICT (job_id, attempt) DO NOTHING"""
Q["job_attempt_finish"] = """
UPDATE job_attempts SET finished_at = now(), outcome = CAST(:outcome AS text), error = CAST(:error AS text)
WHERE job_id = CAST(:job AS uuid) AND attempt = CAST(:attempt AS int)"""
Q["job_succeed"] = """
UPDATE jobs SET status = 'succeeded', finished_at = now(), lease_owner = NULL, lease_expires_at = NULL, checkpoint = CAST(:checkpoint AS jsonb)
WHERE id = CAST(:job AS uuid) AND lease_owner = CAST(:worker AS text) AND status = 'running' RETURNING id"""
Q["job_fail"] = """
UPDATE jobs SET status = CASE WHEN attempts >= max_attempts THEN 'dead' ELSE 'queued' END,
       run_after = now() + make_interval(secs => CAST(:backoff AS int)), last_error = CAST(:error AS text),
       lease_owner = NULL, lease_expires_at = NULL, checkpoint = coalesce(CAST(:checkpoint AS jsonb), checkpoint)
WHERE id = CAST(:job AS uuid) AND lease_owner = CAST(:worker AS text) AND status = 'running' RETURNING status"""
Q["job_heartbeat"] = """
UPDATE jobs SET lease_expires_at = now() + make_interval(secs => CAST(:lease AS int)), checkpoint = CAST(:checkpoint AS jsonb)
WHERE id = CAST(:job AS uuid) AND lease_owner = CAST(:worker AS text) AND status = 'running' RETURNING id"""
Q["job_cancel"] = """
UPDATE jobs SET status = 'cancelled', finished_at = now(), lease_owner = NULL, lease_expires_at = NULL
WHERE id = CAST(:job AS uuid) AND status IN ('queued','running') RETURNING id"""
Q["jobs_list"] = """
SELECT id, job_type, execution_key, status, attempts, max_attempts, run_after, lease_owner, last_error, created_at, finished_at
FROM jobs WHERE (CAST(:status AS text) IS NULL OR status = CAST(:status AS text))
ORDER BY created_at DESC LIMIT CAST(:limit AS int)"""
Q["queue_stats"] = """
SELECT status, count(*) AS n, extract(epoch FROM (now() - min(run_after))) AS oldest_seconds FROM jobs GROUP BY status"""
Q["budget_current"] = """
SELECT p.period_month, p.cap_usd, p.warn_at_usd, p.per_run_cap_usd,
       coalesce(sum(CASE WHEN r.status = 'reserved' THEN r.reserved_usd ELSE 0 END), 0) AS reserved_usd,
       coalesce(sum(CASE WHEN r.status = 'settled' THEN r.actual_usd ELSE 0 END), 0) AS spent_usd
FROM budget_periods p LEFT JOIN budget_reservations r ON r.period_month = p.period_month
WHERE p.period_month = date_trunc('month', now() AT TIME ZONE 'UTC')::date
GROUP BY p.period_month"""
Q["budget_set"] = """
INSERT INTO budget_periods (period_month, cap_usd, warn_at_usd, per_run_cap_usd)
VALUES (date_trunc('month', now() AT TIME ZONE 'UTC')::date, CAST(:cap AS numeric), CAST(:warn AS numeric), CAST(:per_run AS numeric))
ON CONFLICT (period_month) DO UPDATE SET cap_usd = EXCLUDED.cap_usd, warn_at_usd = EXCLUDED.warn_at_usd,
    per_run_cap_usd = EXCLUDED.per_run_cap_usd"""
Q["budget_reserve"] = "SELECT reserve_budget(CAST(:job AS uuid), CAST(:amount AS numeric))"
# Cumulative per-run ceiling (review §2). :at defaults to now(); tests pass it to cross a month boundary.
Q["budget_reserve_run"] = """
SELECT reserve_run_budget(CAST(:job AS uuid), CAST(:run AS uuid), CAST(:amount AS numeric),
                          coalesce(CAST(:at AS timestamptz), now()))"""
Q["budget_per_run_cap"] = """
SELECT per_run_cap_usd FROM budget_periods WHERE period_month = date_trunc('month', now() AT TIME ZONE 'UTC')::date"""
Q["run_set_budget"] = """
UPDATE discovery_runs SET budget_root_id = CAST(:root AS uuid), budget_cap_usd = CAST(:cap AS numeric) WHERE id = CAST(:id AS uuid)"""
Q["run_plan_set_cap"] = """
UPDATE discovery_runs SET plan = jsonb_set(plan, '{run_budget_cap_usd}', to_jsonb(CAST(:cap AS text))) WHERE id = CAST(:id AS uuid)"""
Q["run_budget_state"] = """
SELECT root.id AS root_id, root.budget_cap_usd AS cap_usd,
       coalesce((SELECT sum(CASE WHEN r.status = 'reserved' THEN r.reserved_usd WHEN r.status = 'settled' THEN greatest(r.actual_usd, 0)
                                 ELSE 0 END)
                   FROM budget_reservations r JOIN discovery_runs d ON d.id = r.run_id
                  WHERE coalesce(d.budget_root_id, d.id) = root.id), 0) AS committed_usd
FROM discovery_runs me JOIN discovery_runs root ON root.id = coalesce(me.budget_root_id, me.id) WHERE me.id = CAST(:id AS uuid)"""
Q["run_raise_cap"] = """
UPDATE discovery_runs SET budget_cap_usd = coalesce(budget_cap_usd, 0) + CAST(:amount AS numeric)
WHERE id = (SELECT coalesce(budget_root_id, id) FROM discovery_runs WHERE id = CAST(:id AS uuid)) RETURNING budget_cap_usd"""
Q["document_claim_state"] = """
SELECT (SELECT count(*) FROM claim_evidence ce JOIN claims c ON c.id = ce.claim_id
         WHERE ce.source_document_id = CAST(:id AS uuid) AND ce.excluded_at IS NULL AND c.review_status <> 'rejected') AS claims,
       (SELECT count(*) FROM extraction_rejections r WHERE r.source_document_id = CAST(:id AS uuid) AND r.status = 'open') AS rejected,
       (SELECT published_at FROM source_documents WHERE id = CAST(:id AS uuid)) AS published_at"""
Q["document_set_feed_date"] = """
UPDATE source_documents SET published_at = CAST(:published AS timestamptz), published_at_source = 'feed'
WHERE id = CAST(:id AS uuid) AND published_at IS NULL AND publication_flag IS NULL
  AND CAST(:published AS timestamptz) <= retrieved_at + interval '1 day' RETURNING id"""
Q["fit_tick_lock"] = "SELECT pg_try_advisory_xact_lock(hashtext('atlas:fit_reassess'))"
Q["organisation_canonical"] = """
WITH RECURSIVE chain(id, merged_into_id, depth) AS (
  SELECT id, merged_into_id, 0 FROM organisations WHERE id = CAST(:id AS uuid)
  UNION ALL SELECT o.id, o.merged_into_id, c.depth + 1 FROM organisations o JOIN chain c ON o.id = c.merged_into_id WHERE c.depth < 10)
SELECT id FROM chain WHERE merged_into_id IS NULL LIMIT 1"""
Q["document_run"] = """
SELECT ir.discovery_run_id FROM source_documents d JOIN ingestion_runs ir ON ir.id = d.ingestion_run_id
WHERE d.id = CAST(:id AS uuid)"""
Q["budget_settle"] = """
UPDATE budget_reservations SET status = 'settled', actual_usd = CAST(:actual AS numeric), settled_at = now()
WHERE id = CAST(:id AS uuid) AND status = 'reserved'"""
Q["budget_settle_abandoned"] = """
UPDATE budget_reservations SET status = 'settled', actual_usd = reserved_usd, settled_at = now()
WHERE job_id = CAST(:job AS uuid) AND status = 'reserved' RETURNING id"""
Q["budget_release"] = """
UPDATE budget_reservations SET status = 'released', settled_at = now() WHERE id = CAST(:id AS uuid) AND status = 'reserved'"""
Q["flag_get"] = "SELECT value FROM system_flags WHERE key = CAST(:key AS text)"
Q["flag_set"] = """
INSERT INTO system_flags (key, value) VALUES (CAST(:key AS text), CAST(:value AS jsonb))
ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()"""
Q["ai_call_insert"] = """
INSERT INTO ai_calls (job_id, provider, model, prompt_version, schema_version, input_tokens, output_tokens, estimated_cost_usd,
                      actual_cost_usd, status, error)
VALUES (CAST(:job AS uuid), CAST(:provider AS text), CAST(:model AS text), CAST(:prompt_version AS text),
        CAST(:schema_version AS text), CAST(:input_tokens AS int), CAST(:output_tokens AS int), CAST(:estimated AS numeric),
        CAST(:actual AS numeric), CAST(:status AS text), CAST(:error AS text)) RETURNING id"""
Q["ai_quarantine_insert"] = """
INSERT INTO ai_quarantine (ai_call_id, reason, raw_output) VALUES (CAST(:call AS uuid), CAST(:reason AS text), CAST(:raw AS text))"""
Q["model_versions"] = "SELECT module, version, provisional, definition, created_at FROM scoring_model_versions ORDER BY module, created_at"
Q["model_version_ensure"] = """
INSERT INTO scoring_model_versions (module, version, definition, provisional)
VALUES (CAST(:module AS text), CAST(:version AS text), CAST(:definition AS jsonb), CAST(:provisional AS boolean))
ON CONFLICT (module, version) DO NOTHING"""
Q["model_version_get"] = """
SELECT id, definition FROM scoring_model_versions WHERE module = CAST(:module AS text) AND version = CAST(:version AS text)"""
Q["assessment_insert"] = """
INSERT INTO assessments (opportunity_id, model_version_id, dimension, score, coverage, status, factors)
VALUES (CAST(:opp AS uuid), CAST(:model AS uuid), CAST(:dimension AS text), CAST(:score AS numeric), CAST(:coverage AS numeric),
        CAST(:status AS text), CAST(:factors AS jsonb))"""

Q["channel_events_period"] = """
SELECT event_type, session_key, booking_external_id, occurred_at, channel FROM channel_events
WHERE occurred_at >= CAST(:start AS timestamptz) AND occurred_at < CAST(:end AS timestamptz)
  AND channel = CAST(:channel AS text)"""
Q["channel_list"] = "SELECT channel, count(*) AS events, max(occurred_at) AS latest FROM channel_events GROUP BY channel ORDER BY channel"
Q["integration_failures"] = """
SELECT channel, count(*) AS failures FROM channel_events
WHERE event_type = 'integration_failure' AND occurred_at >= CAST(:start AS timestamptz) AND occurred_at < CAST(:end AS timestamptz)
GROUP BY channel ORDER BY channel"""

# ---------------------------------------------------------------- search
Q["search"] = """
SELECT 'opportunity' AS kind, id::text, title AS label, module AS detail FROM opportunities WHERE title ILIKE '%' || CAST(:q AS text) || '%'
UNION ALL
SELECT 'organisation', id::text, canonical_name, kind FROM organisations
  WHERE merged_into_id IS NULL AND canonical_name ILIKE '%' || CAST(:q AS text) || '%'
UNION ALL
SELECT 'person', id::text, full_name, coalesce(role_title, '') FROM people WHERE full_name ILIKE '%' || CAST(:q AS text) || '%'
LIMIT 30"""


# ---------------------------------------------------------------- directive wfc_0002: evidence pipeline
Q["airport_country"] = "SELECT country FROM airports WHERE iata_code = CAST(:code AS text)"
Q["organisations_by_kind"] = """
SELECT id::text AS id, canonical_name FROM organisations WHERE kind = CAST(:kind AS text) AND merged_into_id IS NULL"""
Q["merge_candidate_add"] = """
INSERT INTO merge_candidates (entity_type, left_id, right_id, reason, score)
VALUES (CAST(:entity_type AS text), CAST(:left AS uuid), CAST(:right AS uuid), CAST(:reason AS text), CAST(:score AS numeric))
ON CONFLICT (entity_type, left_id, right_id) DO NOTHING"""
Q["merge_candidate_find"] = """
SELECT id FROM merge_candidates WHERE entity_type = CAST(:entity_type AS text) AND left_id = CAST(:left AS uuid) AND right_id = CAST(:right AS uuid)"""
Q["opportunity_signal"] = "SELECT signal_id FROM opportunities WHERE id = CAST(:id AS uuid) AND merged_into_id IS NULL"
Q["org_insert_auto"] = """
INSERT INTO organisations (canonical_name, kind, provenance_id, country, resolution_status)
VALUES (CAST(:name AS text), CAST(:kind AS text), CAST(:prov AS uuid), CAST(:country AS text), 'auto_created') RETURNING id"""
Q["airline_ensure"] = """
INSERT INTO airlines (organisation_id, iata_code) VALUES (CAST(:org AS uuid), CAST(:iata AS text))
ON CONFLICT (organisation_id) DO UPDATE SET iata_code = coalesce(airlines.iata_code, EXCLUDED.iata_code)"""
Q["territory_ensure_country"] = """
INSERT INTO territories (code, name, kind, country_code) VALUES (CAST(:code AS text), CAST(:name AS text), 'country', CAST(:code AS text))
ON CONFLICT (code) DO UPDATE SET country_code = EXCLUDED.country_code RETURNING id"""
Q["document_set_extraction"] = """
UPDATE source_documents SET extraction_status = CAST(:status AS text), extraction_detail = CAST(:detail AS text), extracted_at = now()
WHERE id = CAST(:id AS uuid)"""
Q["legacy_deadline_claims"] = """
SELECT c.id::text AS claim_id, c.deadline_info, c.deadline_source_tz, cf.value, cf.quote,
       ARRAY(SELECT sc.signal_id::text FROM signal_claims sc WHERE sc.claim_id = c.id) AS signal_ids
FROM claims c
LEFT JOIN LATERAL (SELECT f.value, f.quote FROM claim_fields f WHERE f.claim_id = c.id AND f.field = 'deadline' AND f.superseded_at IS NULL
                   ORDER BY (f.support = 'supported') DESC, f.quote IS NULL LIMIT 1) cf ON true
WHERE coalesce((c.deadline_info->>'migrated')::boolean, false) AND NOT coalesce((c.deadline_info->>'revalidated')::boolean, false)"""
Q["claim_set_deadline"] = """
UPDATE claims SET deadline_utc = CAST(:deadline AS timestamptz), deadline_source_tz = CAST(:tz AS text), deadline_info = CAST(:info AS jsonb)
WHERE id = CAST(:id AS uuid)"""
Q["legacy_deadline_manual_opportunities"] = """
SELECT id::text AS id, deadline_info FROM opportunities
WHERE signal_id IS NULL AND coalesce((deadline_info->>'migrated')::boolean, false) AND NOT coalesce((deadline_info->>'revalidated')::boolean, false)"""
Q["opportunity_set_deadline_info"] = """
UPDATE opportunities SET deadline_info = CAST(:info AS jsonb),
       deadline_utc = CASE WHEN CAST(:info AS jsonb)->>'precision' = 'instant' THEN (CAST(:info AS jsonb)->>'exact_utc')::timestamptz END,
       deadline_earliest_utc = (CAST(:info AS jsonb)->>'earliest_utc')::timestamptz,
       deadline_latest_utc = (CAST(:info AS jsonb)->>'latest_utc')::timestamptz
WHERE id = CAST(:id AS uuid)"""
Q["queue_pending"] = """
SELECT url, title, country::text AS country, published_hint, reason, attempts FROM discovery_link_queue
WHERE scope_key = CAST(:scope AS text) AND source_id = CAST(:source AS uuid) AND status = 'pending' ORDER BY created_at, url"""
Q["queue_add"] = """
INSERT INTO discovery_link_queue (scope_key, source_id, url, title, country, published_hint, reason, first_run_id, last_run_id, last_error,
                                  attempts)
VALUES (CAST(:scope AS text), CAST(:source AS uuid), CAST(:url AS text), CAST(:title AS text), CAST(:country AS text),
        CAST(:published AS timestamptz), CAST(:reason AS text), CAST(:run AS uuid), CAST(:run AS uuid), CAST(:error AS text),
        CASE WHEN CAST(:reason AS text) = 'retrieval_failed' THEN 1 ELSE 0 END)
ON CONFLICT (scope_key, source_id, url) DO UPDATE SET
    status = CASE WHEN discovery_link_queue.status = 'done' THEN 'done' ELSE 'pending' END,
    reason = EXCLUDED.reason, last_run_id = EXCLUDED.last_run_id, last_error = EXCLUDED.last_error,
    published_hint = coalesce(discovery_link_queue.published_hint, EXCLUDED.published_hint),
    attempts = discovery_link_queue.attempts + CASE WHEN EXCLUDED.reason = 'retrieval_failed' THEN 1 ELSE 0 END"""
Q["queue_mark_gave_up"] = """
UPDATE discovery_link_queue SET status = 'gave_up' WHERE scope_key = CAST(:scope AS text) AND source_id = CAST(:source AS uuid)
  AND url = CAST(:url AS text)"""
Q["documents_reset_failures"] = """
UPDATE source_documents SET read_progress = read_progress - 'failures'
WHERE read_progress IS NOT NULL AND original_url = ANY(ARRAY(SELECT jsonb_array_elements_text(CAST(:urls AS jsonb))))"""
Q["queue_retry_given_up"] = """
UPDATE discovery_link_queue SET status = 'pending', attempts = 0 WHERE scope_key = CAST(:scope AS text) AND status = 'gave_up' RETURNING url"""
Q["queue_done"] = """
INSERT INTO discovery_link_queue (scope_key, source_id, url, reason, status, first_run_id, last_run_id)
VALUES (CAST(:scope AS text), CAST(:source AS uuid), CAST(:url AS text), 'not_fetched_limit', 'done', CAST(:run AS uuid), CAST(:run AS uuid))
ON CONFLICT (scope_key, source_id, url) DO UPDATE SET status = 'done', last_run_id = EXCLUDED.last_run_id, last_error = NULL"""
Q["queue_states"] = """
SELECT url, status FROM discovery_link_queue WHERE scope_key = CAST(:scope AS text) AND source_id = CAST(:source AS uuid)"""
Q["queue_give_up"] = """
UPDATE discovery_link_queue SET status = 'gave_up' WHERE status = 'pending' AND attempts >= CAST(:max AS int)
  AND scope_key = CAST(:scope AS text) AND source_id = CAST(:source AS uuid) RETURNING url"""
Q["queue_remaining"] = """
SELECT count(*) FILTER (WHERE status = 'pending') AS pending, count(*) FILTER (WHERE status = 'gave_up') AS gave_up
FROM discovery_link_queue WHERE scope_key = CAST(:scope AS text)"""
Q["queue_list"] = """
SELECT q.url, q.title, q.country::text AS country, q.reason, q.status, q.attempts, q.last_error, s.name AS source_name, q.updated_at
FROM discovery_link_queue q JOIN sources s ON s.id = q.source_id
WHERE q.scope_key = CAST(:scope AS text) AND q.status <> 'done' ORDER BY q.created_at LIMIT 500"""
Q["document_set_contradiction"] = "UPDATE source_documents SET status_contradiction = CAST(:text AS text) WHERE id = CAST(:id AS uuid)"
Q["document_anchor_claims"] = """
SELECT c.id::text AS claim_id, c.claim_type, ce.excerpt AS quote, ce.assessed_by, c.value->>'summary' AS summary,
       (SELECT coalesce(json_agg(json_build_object('field', f.field, 'value', f.value, 'quote', f.quote)), '[]'::json)
          FROM claim_fields f WHERE f.claim_id = c.id AND f.source_document_id = ce.source_document_id AND f.superseded_at IS NULL
           AND f.field NOT IN ('opportunity_type')) AS fields
FROM claim_evidence ce JOIN claims c ON c.id = ce.claim_id
WHERE ce.source_document_id = CAST(:id AS uuid) AND ce.excluded_at IS NULL AND ce.stance = 'supports'
  AND c.claim_type IN ('gssa_tender','service_tender') AND c.review_status <> 'rejected'
ORDER BY c.created_at"""
Q["document_set_progress"] = "UPDATE source_documents SET read_progress = CAST(:progress AS jsonb) WHERE id = CAST(:id AS uuid)"
Q["document_claim_count"] = """
SELECT count(*) FROM claim_evidence ce JOIN claims c ON c.id = ce.claim_id
WHERE ce.source_document_id = CAST(:id AS uuid) AND ce.excluded_at IS NULL AND c.review_status <> 'rejected'"""
Q["document_text"] = "SELECT body_text, excerpt, source_id FROM source_documents WHERE id = CAST(:id AS uuid)"
Q["rejection_add"] = """
INSERT INTO extraction_rejections (source_document_id, ai_call_id, claim_index, reason, raw)
VALUES (CAST(:doc AS uuid), CAST(:call AS uuid), CAST(:idx AS int), CAST(:reason AS text), CAST(:raw AS jsonb))"""
Q["claim_insert2"] = """
INSERT INTO claims (claim_type, claim_key, signal_key, airline_id, subject_organisation_id, territory_id, trade_lane_id, value,
                    deadline_utc, deadline_source_tz, deadline_info, tender_ref, procurement_cycle, subject_label, review_status)
VALUES (CAST(:claim_type AS text), CAST(:key AS text), CAST(:signal_key AS text), CAST(:airline_id AS uuid), CAST(:subject_org AS uuid),
        CAST(:territory_id AS uuid), CAST(:lane_id AS uuid), CAST(:value AS jsonb), CAST(:deadline AS timestamptz), CAST(:tz AS text),
        CAST(:info AS jsonb), CAST(:tender_ref AS text), CAST(:cycle AS text), CAST(:label AS text), CAST(:review AS text))
RETURNING id"""
Q["claim_field_add"] = """
INSERT INTO claim_fields (claim_id, source_document_id, field, value, normalised, quote, support, reason, assessed_by, validation_version)
VALUES (CAST(:claim AS uuid), CAST(:doc AS uuid), CAST(:field AS text), CAST(:value AS text), CAST(:normalised AS text),
        CAST(:quote AS text), CAST(:support AS text), CAST(:reason AS text), CAST(:assessed_by AS text), CAST(:version AS int))
ON CONFLICT (claim_id, source_document_id, field, normalised) WHERE superseded_at IS NULL DO NOTHING"""
# --- re-check of assessments made under earlier validation rules (wfc_0005)
Q["fields_to_recheck"] = """
SELECT cf.id::text AS field_id, cf.claim_id::text AS claim_id, cf.source_document_id::text AS document_id, cf.field, cf.value, cf.normalised,
       cf.quote, cf.support, cf.reason, cf.assessed_by, cf.validation_version, c.review_status, c.claim_type, c.deadline_source_tz, c.deadline_info,
       d.body_text AS document_text, d.title AS document_title,
       (SELECT ce.excerpt FROM claim_evidence ce WHERE ce.claim_id = c.id AND ce.source_document_id = cf.source_document_id LIMIT 1) AS claim_quote,
       ARRAY(SELECT sc.signal_id::text FROM signal_claims sc WHERE sc.claim_id = c.id) AS signal_ids
FROM claim_fields cf JOIN claims c ON c.id = cf.claim_id JOIN source_documents d ON d.id = cf.source_document_id
WHERE cf.field = CAST(:field AS text) AND cf.superseded_at IS NULL AND cf.validation_version < CAST(:version AS int)
  AND c.review_status NOT IN ('rejected', 'corrected')
ORDER BY cf.created_at"""
Q["claim_field_supersede"] = """
UPDATE claim_fields SET superseded_at = now(), superseded_reason = CAST(:reason AS text) WHERE id = CAST(:id AS uuid) AND superseded_at IS NULL"""
Q["claim_field_add_recheck"] = """
INSERT INTO claim_fields (claim_id, source_document_id, field, value, normalised, quote, support, reason, assessed_by, validation_version, recheck_of)
VALUES (CAST(:claim AS uuid), CAST(:doc AS uuid), CAST(:field AS text), CAST(:value AS text), CAST(:normalised AS text),
        CAST(:quote AS text), CAST(:support AS text), CAST(:reason AS text), 'rule', CAST(:version AS int), CAST(:recheck_of AS uuid))
RETURNING id"""
Q["claim_field_set_version"] = "UPDATE claim_fields SET validation_version = CAST(:version AS int) WHERE id = CAST(:id AS uuid)"
Q["opportunities_of_claim"] = """
SELECT DISTINCT o.id::text AS id FROM opportunities o JOIN signal_claims sc ON sc.signal_id = o.signal_id WHERE sc.claim_id = CAST(:claim AS uuid)"""
Q["opportunity_add_review_flag"] = """
UPDATE opportunities SET review_flags = review_flags || CAST(:flag AS jsonb) WHERE id = CAST(:id AS uuid)"""
Q["signal_withdrawn_verdicts"] = """
SELECT cf.id::text AS field_id, cf.claim_id::text AS claim_id, cf.field, cf.support, cf.reason, prev.support AS previous_support
FROM signal_claims sc JOIN claims c ON c.id = sc.claim_id
JOIN claim_fields cf ON cf.claim_id = c.id AND cf.superseded_at IS NULL AND cf.recheck_of IS NOT NULL AND cf.support <> 'supported'
JOIN claim_fields prev ON prev.id = cf.recheck_of
WHERE sc.signal_id = CAST(:signal AS uuid) AND c.review_status NOT IN ('rejected', 'corrected') AND prev.support = 'supported'"""
Q["signal_field_support"] = """
SELECT cf.support, count(*) AS n FROM signal_claims sc JOIN claims c ON c.id = sc.claim_id
JOIN claim_fields cf ON cf.claim_id = c.id AND cf.superseded_at IS NULL AND cf.field = CAST(:field AS text)
JOIN claim_evidence ce ON ce.claim_id = c.id AND ce.source_document_id = cf.source_document_id AND ce.excluded_at IS NULL
WHERE sc.signal_id = CAST(:signal AS uuid) AND c.review_status NOT IN ('rejected', 'corrected') GROUP BY cf.support"""
# Every unresolved MATERIAL field, for the review workflow: its reason, the source passage and where it sits.
Q["review_fields"] = """
SELECT cf.id::text AS field_id, cf.field, cf.value, cf.support, cf.reason, cf.quote, cf.assessed_by, cf.validation_version, cf.created_at,
       c.id::text AS claim_id, c.claim_type, c.review_status, c.subject_label, c.tender_ref,
       ce.page_ref AS location, d.id::text AS document_id, d.title AS document_title, d.canonical_url, d.retrieved_at, d.content_hash AS document_version,
       (SELECT s.title FROM signal_claims sc JOIN signals s ON s.id = sc.signal_id WHERE sc.claim_id = c.id LIMIT 1) AS signal_title,
       (SELECT o.id::text FROM signal_claims sc JOIN opportunities o ON o.signal_id = sc.signal_id WHERE sc.claim_id = c.id LIMIT 1) AS opportunity_id
FROM claim_fields cf JOIN claims c ON c.id = cf.claim_id
JOIN claim_evidence ce ON ce.claim_id = c.id AND ce.source_document_id = cf.source_document_id AND ce.excluded_at IS NULL
JOIN source_documents d ON d.id = cf.source_document_id
WHERE cf.superseded_at IS NULL AND cf.support IN ('unsupported', 'review_required')
  AND cf.field IN ('status', 'deadline', 'eligibility', 'country', 'issuer_country', 'contract_territory', 'origin', 'destination', 'tender_ref', 'service',
                   'freight_scope')
  AND c.review_status NOT IN ('rejected', 'corrected')
ORDER BY CASE cf.support WHEN 'review_required' THEN 0 ELSE 1 END, cf.created_at DESC LIMIT CAST(:limit AS int)"""
Q["claim_clear_status"] = """UPDATE claims SET value = value - 'status' WHERE id = CAST(:id AS uuid)"""
Q["audit_system"] = """
INSERT INTO audit_events (event_type, actor, entity_type, entity_id, detail)
VALUES (CAST(:event_type AS text), 'system', CAST(:entity_type AS text), CAST(:entity_id AS text), CAST(:detail AS jsonb))"""
Q["claim_review_state"] = "SELECT review_status FROM claims WHERE id = CAST(:id AS uuid)"
Q["signal_upsert2"] = """
INSERT INTO signals (module, classification, signal_key, title, summary, gaps, identity_basis, tender_ref, procurement_cycle,
                     subject_organisation_id, related_modules)
VALUES (CAST(:module AS text), CAST(:classification AS text), CAST(:key AS text), CAST(:title AS text), CAST(:summary AS text),
        CAST(:gaps AS jsonb), CAST(:basis AS text), CAST(:tender_ref AS text), CAST(:cycle AS text), CAST(:subject AS uuid),
        ARRAY(SELECT jsonb_array_elements_text(CAST(:related AS jsonb))))
ON CONFLICT (module, signal_key) DO UPDATE
SET tender_ref = coalesce(signals.tender_ref, EXCLUDED.tender_ref),
    procurement_cycle = coalesce(signals.procurement_cycle, EXCLUDED.procurement_cycle),
    subject_organisation_id = coalesce(signals.subject_organisation_id, EXCLUDED.subject_organisation_id),
    updated_at = now()
RETURNING id, (xmax = 0) AS inserted"""
Q["signal_geo_add"] = """
INSERT INTO signal_geography (signal_id, country_code, role, support)
VALUES (CAST(:signal AS uuid), CAST(:country AS text), CAST(:role AS text), CAST(:support AS text))
ON CONFLICT (signal_id, country_code, role) DO UPDATE
SET support = CASE WHEN signal_geography.support = 'supported' OR EXCLUDED.support = 'supported' THEN 'supported' ELSE 'unverified' END"""
Q["tender_signals_for_subject"] = """
SELECT s.id::text AS id, s.title,
       ARRAY(SELECT g.country_code::text FROM signal_geography g WHERE g.signal_id = s.id AND g.support = 'supported'
             AND g.role IN ('delivery','contract_territory','origin','destination')) AS countries
FROM signals s
WHERE s.subject_organisation_id = CAST(:subject AS uuid) AND s.id <> CAST(:id AS uuid) AND s.module = CAST(:module AS text)
  AND s.signal_key LIKE 'tender|%' AND s.merged_into_id IS NULL"""
Q["signal_get"] = "SELECT * FROM signals WHERE id = CAST(:id AS uuid)"
Q["document_published_at"] = "SELECT published_at FROM source_documents WHERE id = CAST(:id AS uuid)"
Q["signal_survivor"] = """
WITH RECURSIVE chain(id, merged_into_id, depth) AS (
  SELECT id, merged_into_id, 0 FROM signals WHERE id = CAST(:id AS uuid)
  UNION ALL SELECT s.id, s.merged_into_id, c.depth + 1 FROM signals s JOIN chain c ON s.id = c.merged_into_id WHERE c.depth < 20)
SELECT id FROM chain WHERE merged_into_id IS NULL LIMIT 1"""
Q["tender_signals_by_ref"] = """
SELECT s.id::text AS id, s.signal_key, s.module, s.related_modules FROM signals s
WHERE s.merged_into_id IS NULL AND s.signal_key LIKE 'tender|%' AND s.tender_ref IS NOT NULL
  AND regexp_replace(upper(s.tender_ref), '[^A-Z0-9]', '', 'g') = CAST(:ref AS text)
  AND (CAST(:subject AS uuid) IS NULL OR s.subject_organisation_id IS NULL OR s.subject_organisation_id = CAST(:subject AS uuid))"""
Q["family_has_other_doc_same_source"] = """
SELECT EXISTS (SELECT 1 FROM source_documents me JOIN announcement_families f ON f.family_key = CAST(:family AS text)
               JOIN source_documents o ON o.announcement_family_id = f.id
               WHERE me.id = CAST(:doc AS uuid) AND o.id <> me.id AND o.source_id = me.source_id
                 AND o.canonical_url <> me.canonical_url)"""
Q["signal_adopt_identifiers"] = """
UPDATE signals a SET tender_ref = coalesce(a.tender_ref, b.tender_ref), procurement_cycle = coalesce(a.procurement_cycle, b.procurement_cycle),
                     subject_organisation_id = coalesce(a.subject_organisation_id, b.subject_organisation_id)
FROM signals b WHERE a.id = CAST(:id AS uuid) AND b.id = CAST(:src AS uuid)"""
Q["signal_claim_evidence2"] = """
SELECT c.id::text AS claim_id, c.claim_type, c.value, c.deadline_utc, c.deadline_source_tz, c.deadline_info, c.review_status, ce.stance,
       ce.assessed_by, ce.excluded_at, d.id::text AS document_id, d.published_at, d.retrieved_at, f.family_key, d.status_contradiction,
       coalesce(d.doc_family, s.family, 'unknown') AS source_family, coalesce(d.doc_authority, s.authority, 'unverified') AS authority,
       coalesce((SELECT dc.result FROM document_checks dc WHERE dc.source_document_id = d.id AND dc.check_type = 'authenticity'
                 ORDER BY dc.checked_at DESC LIMIT 1), 'unknown') AS authentic,
       ce.excerpt, (SELECT cf.quote FROM claim_fields cf WHERE cf.claim_id = c.id AND cf.field = 'status' AND cf.superseded_at IS NULL
                    ORDER BY cf.created_at DESC LIMIT 1) AS status_quote
FROM signal_claims sc JOIN claims c ON c.id = sc.claim_id
JOIN claim_evidence ce ON ce.claim_id = c.id JOIN source_documents d ON d.id = ce.source_document_id
LEFT JOIN announcement_families f ON f.id = d.announcement_family_id LEFT JOIN sources s ON s.id = d.source_id
WHERE sc.signal_id = CAST(:signal AS uuid)
ORDER BY coalesce(d.published_at, d.retrieved_at), d.id"""
Q["signal_geo"] = """
SELECT country_code::text AS country_code, role, support FROM signal_geography WHERE signal_id = CAST(:signal AS uuid)
ORDER BY role, country_code"""
Q["signal_deadline_field_notes"] = """
SELECT cf.reason FROM claim_fields cf JOIN signal_claims sc ON sc.claim_id = cf.claim_id
WHERE sc.signal_id = CAST(:signal AS uuid) AND cf.field = 'deadline' AND cf.support = 'supported' AND cf.superseded_at IS NULL"""
Q["signal_update_eval"] = """
UPDATE signals SET classification = CAST(:classification AS text), summary = CAST(:summary AS text), gaps = CAST(:gaps AS jsonb),
       tender_state = CAST(:tender_state AS jsonb), first_published_at = CAST(:first_published AS timestamptz),
       last_evidence_at = CAST(:last_evidence AS timestamptz)
WHERE id = CAST(:id AS uuid)"""
Q["opportunity_by_signal"] = "SELECT id FROM opportunities WHERE signal_id = CAST(:signal AS uuid) AND merged_into_id IS NULL"
Q["is_airline"] = "SELECT EXISTS (SELECT 1 FROM airlines WHERE organisation_id = CAST(:id AS uuid))"
Q["opportunity_upsert_from_signal2"] = """
INSERT INTO opportunities (module, signal_id, dedup_key, title, airline_id, organisation_id, territory_id, service_id, deadline_utc,
                           deadline_source_tz, deadline_info, deadline_earliest_utc, deadline_latest_utc)
VALUES (CAST(:module AS text), CAST(:signal AS uuid), CAST(:key AS text), CAST(:title AS text), CAST(:airline_id AS uuid),
        CAST(:organisation_id AS uuid), CAST(:territory_id AS uuid), CAST(:service_id AS uuid), CAST(:deadline AS timestamptz),
        CAST(:tz AS text), CAST(:info AS jsonb), CAST(:earliest AS timestamptz), CAST(:latest AS timestamptz))
ON CONFLICT (module, dedup_key) DO UPDATE
SET deadline_utc = EXCLUDED.deadline_utc, deadline_source_tz = EXCLUDED.deadline_source_tz, deadline_info = EXCLUDED.deadline_info,
    deadline_earliest_utc = EXCLUDED.deadline_earliest_utc, deadline_latest_utc = EXCLUDED.deadline_latest_utc,
    signal_id = EXCLUDED.signal_id,
    airline_id = coalesce(opportunities.airline_id, EXCLUDED.airline_id),
    organisation_id = coalesce(opportunities.organisation_id, EXCLUDED.organisation_id),
    territory_id = coalesce(EXCLUDED.territory_id, opportunities.territory_id),
    service_id = coalesce(opportunities.service_id, EXCLUDED.service_id)
RETURNING id, (xmax = 0) AS inserted"""
Q["opportunity_geo_clear"] = """
DELETE FROM opportunity_geography WHERE opportunity_id = CAST(:opp AS uuid) AND support <> 'internal_record'"""
Q["opportunity_geo_copy"] = """
INSERT INTO opportunity_geography (opportunity_id, country_code, role, support)
SELECT CAST(:opp AS uuid), country_code, role, support FROM signal_geography WHERE signal_id = CAST(:signal AS uuid)
ON CONFLICT (opportunity_id, country_code, role) DO NOTHING"""
Q["opportunity_set_tender_status"] = "UPDATE opportunities SET tender_status = CAST(:status AS text) WHERE id = CAST(:id AS uuid)"
Q["checks_prune"] = """
DELETE FROM qualification_checks WHERE opportunity_id = CAST(:id AS uuid) AND NOT (CAST(:keep AS jsonb) ? check_code)"""
Q["opportunity_evidence_basis"] = """
SELECT c.id::text AS claim_id, c.claim_type, c.status, c.review_status
FROM opportunities o JOIN signal_claims sc ON sc.signal_id = o.signal_id JOIN claims c ON c.id = sc.claim_id
WHERE o.id = CAST(:id AS uuid) ORDER BY c.id"""
Q["service_requirements"] = """
SELECT credential_type FROM service_credential_requirements WHERE service_id = CAST(:service AS uuid) ORDER BY credential_type"""
Q["company_name"] = "SELECT name FROM operating_companies WHERE id = CAST(:id AS uuid)"
Q["service_code_by_id"] = "SELECT code FROM services WHERE id = CAST(:id AS uuid)"
Q["service_code"] = "SELECT code FROM services WHERE id = CAST(:id AS uuid)"
Q["opportunities_live"] = """
SELECT id FROM opportunities WHERE commercial_stage NOT IN ('won','lost','expired') AND merged_into_id IS NULL"""
Q["opportunity_set_approval_basis"] = "UPDATE opportunities SET approval_basis = CAST(:basis AS jsonb) WHERE id = CAST(:id AS uuid)"
Q["opportunity_owner"] = """
SELECT p.full_name AS owner FROM opportunities o LEFT JOIN people p ON p.id = o.owner_person_id WHERE o.id = CAST(:id AS uuid)"""
Q["person_exists"] = "SELECT id FROM people WHERE id = CAST(:id AS uuid)"
Q["person_name"] = "SELECT full_name FROM people WHERE id = CAST(:id AS uuid)"
Q["opportunity_set_scope2"] = """
UPDATE opportunities SET operating_company_id = CAST(:company AS uuid), service_id = CAST(:service AS uuid),
       station_airport_id = CAST(:station AS uuid), delivery_start = CAST(:delivery AS date),
       required_credentials = ARRAY(SELECT jsonb_array_elements_text(CAST(:creds AS jsonb)))
WHERE id = CAST(:id AS uuid) RETURNING id"""

# ---------------------------------------------------------------- directive wfc_0002: discovery
Q["regions_list"] = """
SELECT r.code, r.name, r.kind, (SELECT count(*) FROM region_countries rc WHERE rc.region_code = r.code) AS countries
FROM regions r ORDER BY CASE r.kind WHEN 'economic' THEN 0 WHEN 'custom' THEN 1 WHEN 'un_region' THEN 2 ELSE 3 END, r.name"""
Q["region_members"] = "SELECT region_code, country_code::text AS country_code FROM region_countries"
Q["countries_list"] = "SELECT code::text AS code, name, un_region, un_subregion FROM countries ORDER BY name"
Q["region_insert"] = """
INSERT INTO regions (code, name, kind) VALUES (CAST(:code AS text), CAST(:name AS text), 'custom') RETURNING code"""
Q["region_add_country"] = """
INSERT INTO region_countries (region_code, country_code) VALUES (CAST(:region AS text), CAST(:country AS text)) ON CONFLICT DO NOTHING"""
Q["search_insert"] = """
INSERT INTO discovery_searches (name, saved, geo_mode, countries, regions, modules, organisation, airline, keywords, date_from, date_to,
                                date_filter, purpose, brief)
VALUES (CAST(:name AS text), CAST(:saved AS boolean), CAST(:geo_mode AS text),
        ARRAY(SELECT jsonb_array_elements_text(CAST(:countries AS jsonb)))::char(2)[],
        ARRAY(SELECT jsonb_array_elements_text(CAST(:regions AS jsonb))),
        ARRAY(SELECT jsonb_array_elements_text(CAST(:modules AS jsonb))),
        CAST(:organisation AS text), CAST(:airline AS text), CAST(:keywords AS text), CAST(:date_from AS date), CAST(:date_to AS date),
        CAST(:date_filter AS text), CAST(:purpose AS text), CAST(:brief AS text))
RETURNING id"""
Q["search_set_cursor"] = """
UPDATE discovery_searches SET coverage_cursor = coverage_cursor || jsonb_build_object(CAST(:source AS text), CAST(:cursor AS jsonb))
WHERE id = CAST(:id AS uuid)"""
Q["search_get"] = """
SELECT id, name, saved, geo_mode, ARRAY(SELECT unnest(countries)::text) AS countries, regions, modules, organisation, airline,
       keywords, date_from, date_to, date_filter, coverage_cursor, created_at, updated_at, deleted_at, purpose, brief
FROM discovery_searches WHERE id = CAST(:id AS uuid)"""
Q["searches_saved"] = """
SELECT s.id, s.name, s.geo_mode, ARRAY(SELECT unnest(s.countries)::text) AS countries, s.regions, s.modules, s.organisation, s.airline,
       s.keywords, s.date_from, s.date_to, s.date_filter, s.coverage_cursor, s.updated_at, s.purpose, s.brief,
       (SELECT count(*) FROM discovery_link_queue q WHERE q.scope_key = 'search:' || s.id::text AND q.status = 'pending') AS queued_links,
       (SELECT row_to_json(x) FROM (SELECT r.id, r.status, r.outcome, r.created_at, r.finished_at, r.counts FROM discovery_runs r
          WHERE r.search_id = s.id ORDER BY r.created_at DESC LIMIT 1) x) AS last_run,
       (SELECT row_to_json(y) FROM (SELECT sc.id, sc.interval_minutes, sc.enabled, sc.next_run_at, sc.timezone FROM schedules sc
          WHERE sc.scope_search_id = s.id ORDER BY sc.created_at LIMIT 1) y) AS schedule
FROM discovery_searches s WHERE s.saved AND s.deleted_at IS NULL ORDER BY s.name"""
Q["search_delete"] = "UPDATE discovery_searches SET deleted_at = now() WHERE id = CAST(:id AS uuid) AND deleted_at IS NULL RETURNING id"
Q["search_save"] = """
UPDATE discovery_searches SET saved = true, name = CAST(:name AS text) WHERE id = CAST(:id AS uuid) AND deleted_at IS NULL RETURNING id"""
Q["sources_discoverable"] = """
SELECT * FROM sources WHERE enabled AND deleted_at IS NULL AND source_type <> 'file_import' AND base_url IS NOT NULL ORDER BY name"""
Q["run_insert"] = """
INSERT INTO discovery_runs (search_id, source_id, trigger, plan, estimated_cost_usd)
VALUES (CAST(:search AS uuid), CAST(:source AS uuid), CAST(:trigger AS text), CAST(:plan AS jsonb), CAST(:estimated AS numeric))
RETURNING id"""
Q["job_enqueue2"] = """
INSERT INTO jobs (job_type, execution_key, schedule_id, payload, retry_of)
VALUES (CAST(:job_type AS text), CAST(:key AS text), CAST(:schedule AS uuid), CAST(:payload AS jsonb), CAST(:retry_of AS uuid))
ON CONFLICT (execution_key) DO NOTHING RETURNING id"""
Q["run_set_job"] = "UPDATE discovery_runs SET job_id = CAST(:job AS uuid) WHERE id = CAST(:id AS uuid)"
Q["run_get"] = "SELECT * FROM discovery_runs WHERE id = CAST(:id AS uuid)"
Q["run_by_job"] = "SELECT id FROM discovery_runs WHERE job_id = CAST(:job AS uuid)"
Q["run_start"] = """
UPDATE discovery_runs SET status = 'running', started_at = coalesce(started_at, now()) WHERE id = CAST(:id AS uuid)
  AND status IN ('queued','running')"""
Q["run_progress"] = "UPDATE discovery_runs SET progress = CAST(:progress AS jsonb) WHERE id = CAST(:id AS uuid)"
Q["run_status"] = "SELECT status FROM discovery_runs WHERE id = CAST(:id AS uuid)"
Q["run_source_set"] = """
INSERT INTO discovery_run_sources (run_id, source_id, status, detail, documents, new_documents, failures, issues)
VALUES (CAST(:run AS uuid), CAST(:source AS uuid), CAST(:status AS text), CAST(:detail AS text), CAST(:documents AS int),
        CAST(:new_documents AS int), CAST(:failures AS int), CAST(:issues AS jsonb))
ON CONFLICT (run_id, source_id) DO UPDATE SET status = EXCLUDED.status, detail = EXCLUDED.detail, documents = EXCLUDED.documents,
    new_documents = EXCLUDED.new_documents, failures = EXCLUDED.failures, issues = EXCLUDED.issues"""
Q["run_finish"] = """
UPDATE discovery_runs SET status = CAST(:status AS text), outcome = CAST(:outcome AS text), counts = CAST(:counts AS jsonb),
       actual_cost_usd = CAST(:actual AS numeric), finished_at = now()
WHERE id = CAST(:id AS uuid) AND status IN ('queued','running')"""
Q["run_fail"] = """
UPDATE discovery_runs SET status = 'failed', outcome = 'incomplete', error = CAST(:error AS text), finished_at = now()
WHERE id = CAST(:id AS uuid) AND status IN ('queued','running')"""
Q["run_cancel"] = """
UPDATE discovery_runs SET status = 'cancelled', outcome = 'cancelled', finished_at = now()
WHERE id = CAST(:id AS uuid) AND status IN ('queued','running')"""
Q["run_actual_cost"] = """
SELECT coalesce(sum(CASE WHEN status = 'settled' THEN greatest(actual_usd, 0) WHEN status = 'reserved' THEN reserved_usd ELSE 0 END), 0)
FROM budget_reservations WHERE run_id = CAST(:id AS uuid)"""
Q["result_add"] = """
INSERT INTO discovery_results (run_id, signal_id, opportunity_id, is_new, match)
VALUES (CAST(:run AS uuid), CAST(:signal AS uuid), CAST(:opp AS uuid), CAST(:is_new AS boolean), CAST(:match AS jsonb))
ON CONFLICT (run_id, signal_id) DO UPDATE SET opportunity_id = EXCLUDED.opportunity_id, match = EXCLUDED.match"""
Q["ingestion_run_start2"] = """
INSERT INTO ingestion_runs (source_id, job_id, discovery_run_id) VALUES (CAST(:source AS uuid), CAST(:job AS uuid),
       CAST(:discovery_run AS uuid)) RETURNING id"""
Q["ingestion_run_finish2"] = """
UPDATE ingestion_runs SET finished_at = now(), status = CAST(:status AS text), stats = CAST(:stats AS jsonb), error = CAST(:error AS text)
WHERE id = CAST(:id AS uuid)"""
Q["document_by_content"] = """
SELECT d.id, d.extraction_status, d.read_progress, f.family_key FROM source_documents d
LEFT JOIN announcement_families f ON f.id = d.announcement_family_id
WHERE d.canonical_url = CAST(:canonical AS text) AND d.content_hash = CAST(:hash AS text)"""
Q["signals_for_document"] = """
SELECT DISTINCT sc.signal_id::text AS signal_id FROM claim_evidence ce JOIN signal_claims sc ON sc.claim_id = ce.claim_id
WHERE ce.source_document_id = CAST(:doc AS uuid)"""
Q["document_set_summary"] = """
UPDATE source_documents SET summary_en = CAST(:summary AS text), summary_is_translation = CAST(:translated AS boolean),
       language = coalesce(CAST(:language AS text), language)
WHERE id = CAST(:id AS uuid)"""
Q["signal_match_view"] = """
SELECT s.id, s.module, s.related_modules, s.classification, s.title, s.gaps, s.tender_state, s.first_published_at, s.merged_into_id,
       org.canonical_name AS subject_name,
       (SELECT string_agg(DISTINCT c.subject_label, ' ') FROM signal_claims sc JOIN claims c ON c.id = sc.claim_id
         WHERE sc.signal_id = s.id) AS subject_label,
       (SELECT left(string_agg(DISTINCT coalesce(d.title, '') || ' ' || coalesce(ce.excerpt, ''), ' '), 20000)
          FROM signal_claims sc JOIN claim_evidence ce ON ce.claim_id = sc.claim_id JOIN source_documents d ON d.id = ce.source_document_id
         WHERE sc.signal_id = s.id) AS evidence_text,
       (SELECT o.qualification_status FROM opportunities o WHERE o.signal_id = s.id AND o.merged_into_id IS NULL LIMIT 1) AS qualification_status,
       (SELECT count(DISTINCT d.announcement_family_id) FROM signal_claims sc JOIN claim_evidence ce ON ce.claim_id = sc.claim_id
          JOIN source_documents d ON d.id = ce.source_document_id WHERE sc.signal_id = s.id AND ce.stance = 'supports'
          AND ce.excluded_at IS NULL) AS families,
       (SELECT coalesce(d.doc_authority, src.authority) FROM signal_claims sc JOIN claim_evidence ce ON ce.claim_id = sc.claim_id
          JOIN source_documents d ON d.id = ce.source_document_id JOIN sources src ON src.id = d.source_id
         WHERE sc.signal_id = s.id AND ce.stance = 'supports'
         ORDER BY CASE coalesce(d.doc_authority, src.authority) WHEN 'official_portal' THEN 0 WHEN 'internal_record' THEN 0 WHEN 'company_release' THEN 1
                  WHEN 'trade_press' THEN 2 ELSE 3 END LIMIT 1) AS best_authority,
       (SELECT count(*) FROM signal_claims sc JOIN claims c ON c.id = sc.claim_id WHERE sc.signal_id = s.id
          AND c.status = 'supported') AS claims_supported
FROM signals s LEFT JOIN organisations org ON org.id = s.subject_organisation_id WHERE s.id = CAST(:id AS uuid)"""

# ---------------------------------------------------------------- directive wfc_0002: sources and schedules
_SOURCE_COLS = """
    CAST(:name AS text), CAST(:family AS text), CAST(:base_url AS text), CAST(:authority AS text), CAST(:note AS text),
    CAST(:retention AS boolean), CAST(:enabled AS boolean), CAST(:source_type AS text),
    ARRAY(SELECT jsonb_array_elements_text(CAST(:countries AS jsonb)))::char(2)[], CAST(:global_coverage AS boolean),
    CAST(:language AS text), CAST(:local_language AS boolean), ARRAY(SELECT jsonb_array_elements_text(CAST(:modules AS jsonb))),
    CAST(:refresh AS int), CAST(:template AS text), CAST(:max_items AS int), CAST(:notes AS text)"""
Q["source_insert2"] = f"""
INSERT INTO sources (name, family, base_url, authority, authorisation_note, retention_permitted, enabled, source_type, country_coverage,
                     global_coverage, language, local_language_permitted, modules, refresh_minutes, query_template, max_items, notes)
VALUES ({_SOURCE_COLS}) RETURNING id"""
Q["source_update2"] = f"""
UPDATE sources SET (name, family, base_url, authority, authorisation_note, retention_permitted, enabled, source_type, country_coverage,
                    global_coverage, language, local_language_permitted, modules, refresh_minutes, query_template, max_items, notes)
  = ({_SOURCE_COLS})
WHERE id = CAST(:id AS uuid) AND deleted_at IS NULL"""
Q["source_by_name"] = "SELECT id FROM sources WHERE lower(name) = lower(CAST(:name AS text)) AND deleted_at IS NULL"
Q["source_retire"] = "UPDATE sources SET deleted_at = now(), enabled = false WHERE id = CAST(:id AS uuid) AND deleted_at IS NULL"
Q["sources_list"] = """
SELECT s.id, s.name, s.family, s.base_url, s.authority, s.enabled, s.source_type, s.builtin, ARRAY(SELECT unnest(s.country_coverage)::text) AS country_coverage,
       s.global_coverage, s.language, s.local_language_permitted, s.modules, s.refresh_minutes, s.query_template, s.max_items,
       s.retention_permitted, s.authorisation_note, s.notes, s.freshness_sla_hours, s.updated_at,
       (SELECT max(r.finished_at) FROM ingestion_runs r WHERE r.source_id = s.id AND r.status = 'succeeded') AS last_success_at,
       (SELECT max(r.finished_at) FROM ingestion_runs r WHERE r.source_id = s.id AND r.status = 'failed') AS last_failure_at,
       (SELECT r.error FROM ingestion_runs r WHERE r.source_id = s.id AND r.status = 'failed' ORDER BY r.finished_at DESC LIMIT 1) AS last_error,
       (SELECT count(*) FROM source_documents d WHERE d.source_id = s.id) AS documents,
       (SELECT row_to_json(x) FROM (SELECT sc.id, sc.interval_minutes, sc.enabled, sc.next_run_at, sc.timezone FROM schedules sc
          WHERE sc.scope_source_id = s.id ORDER BY sc.created_at LIMIT 1) x) AS schedule
FROM sources s WHERE s.deleted_at IS NULL
  AND (CAST(:kind AS text) IS NULL OR (CAST(:kind AS text) = 'web' AND s.source_type <> 'file_import')
       OR (CAST(:kind AS text) = 'import' AND s.source_type = 'file_import'))
ORDER BY s.source_type = 'file_import', s.name"""
Q["source_runs"] = """
SELECT r.id, r.status, r.started_at, r.finished_at, r.stats, r.error, r.discovery_run_id,
       (SELECT count(*) FROM source_documents d WHERE d.ingestion_run_id = r.id) AS documents
FROM ingestion_runs r WHERE r.source_id = CAST(:source AS uuid) ORDER BY r.started_at DESC LIMIT CAST(:limit AS int)"""
Q["source_documents_list"] = """
SELECT d.id, d.title, d.canonical_url, d.published_at, d.retrieved_at, d.language, d.extraction_status, d.extraction_detail,
       d.summary_en, d.summary_is_translation,
       (SELECT count(DISTINCT ce.claim_id) FROM claim_evidence ce WHERE ce.source_document_id = d.id) AS claims,
       (SELECT count(*) FROM extraction_rejections er WHERE er.source_document_id = d.id AND er.status = 'open') AS open_rejections
FROM source_documents d
WHERE (CAST(:source AS uuid) IS NULL OR d.source_id = CAST(:source AS uuid))
  AND (CAST(:run AS uuid) IS NULL OR d.ingestion_run_id = CAST(:run AS uuid))
  AND (CAST(:status AS text) IS NULL OR d.extraction_status = CAST(:status AS text))
ORDER BY d.retrieved_at DESC LIMIT CAST(:limit AS int)"""
Q["schedule_for_source"] = "SELECT id, timezone FROM schedules WHERE scope_source_id = CAST(:source AS uuid) ORDER BY created_at LIMIT 1"
Q["schedule_insert"] = """
INSERT INTO schedules (job_type, scope_source_id, scope_search_id, interval_minutes, timezone, enabled, name)
VALUES (CAST(:job_type AS text), CAST(:source AS uuid), CAST(:search AS uuid), CAST(:interval AS int), CAST(:tz AS text),
        CAST(:enabled AS boolean), CAST(:name AS text)) RETURNING id"""
Q["schedule_update"] = """
UPDATE schedules SET interval_minutes = CAST(:interval AS int), timezone = CAST(:tz AS text), enabled = CAST(:enabled AS boolean),
       name = CAST(:name AS text), next_run_at = CASE WHEN CAST(:enabled AS boolean) THEN next_run_at ELSE NULL END
WHERE id = CAST(:id AS uuid)"""
Q["schedule_get"] = "SELECT * FROM schedules WHERE id = CAST(:id AS uuid)"
Q["run_results"] = """
SELECT r.signal_id::text AS signal_id, r.opportunity_id::text AS opportunity_id, r.is_new, r.match, s.title, s.classification, s.module,
       o.qualification_status, o.commercial_stage, s.freight_scope, o.tender_status
FROM discovery_results r JOIN signals s ON s.id = r.signal_id LEFT JOIN opportunities o ON o.id = r.opportunity_id
WHERE r.run_id = CAST(:run AS uuid)
ORDER BY (s.classification = 'qualified_opportunity') DESC, (s.classification = 'freight_candidate') DESC, s.title"""

# ---------------------------------------------------------------- directive wfc_0002: review
Q["signals_of_claim"] = "SELECT signal_id::text AS signal_id FROM signal_claims WHERE claim_id = CAST(:claim AS uuid)"
Q["claim_get"] = """
SELECT c.*, (SELECT ce.excerpt FROM claim_evidence ce WHERE ce.claim_id = c.id ORDER BY ce.created_at LIMIT 1) AS evidence_quote,
       (SELECT ce.stance FROM claim_evidence ce WHERE ce.claim_id = c.id ORDER BY ce.created_at LIMIT 1) AS stance
FROM claims c WHERE c.id = CAST(:id AS uuid)"""
Q["claim_set_review"] = """
UPDATE claims SET review_status = CAST(:review AS text), reviewed_at = now(), review_note = CAST(:note AS text)
WHERE id = CAST(:id AS uuid)"""
Q["claim_has_document"] = """
SELECT 1 FROM claim_evidence WHERE claim_id = CAST(:claim AS uuid) AND source_document_id = CAST(:doc AS uuid) LIMIT 1"""
Q["claim_evidence_exclude"] = """
UPDATE claim_evidence SET excluded_at = now() WHERE claim_id = CAST(:claim AS uuid) AND source_document_id = CAST(:doc AS uuid)"""
Q["claim_fields_for"] = """
SELECT field, value, normalised, quote, support, reason, assessed_by, created_at FROM claim_fields
WHERE claim_id = CAST(:claim AS uuid) AND source_document_id = CAST(:doc AS uuid) AND superseded_at IS NULL ORDER BY field"""
Q["document_review_get"] = """
SELECT d.*, f.family_key, s.name AS source_name, s.authority, s.source_type
FROM source_documents d LEFT JOIN announcement_families f ON f.id = d.announcement_family_id
LEFT JOIN sources s ON s.id = d.source_id WHERE d.id = CAST(:id AS uuid)"""
Q["document_checks"] = """
SELECT DISTINCT ON (check_type) check_type, result, detail, checked_at FROM document_checks
WHERE source_document_id = CAST(:id AS uuid) ORDER BY check_type, checked_at DESC"""
Q["document_claims"] = """
SELECT c.id::text AS claim_id, c.claim_type, c.status, c.review_status, c.review_note, c.tender_ref, c.subject_label,
       c.deadline_utc, c.deadline_source_tz, ce.stance, ce.excerpt AS quote, ce.assessed_by, ce.excluded_at, ce.page_ref AS location,
       ce.created_at AS assessed_at,
       (SELECT json_agg(json_build_object('field', cf.field, 'value', cf.value, 'normalised', cf.normalised, 'quote', cf.quote,
                                          'support', cf.support, 'reason', cf.reason, 'assessed_by', cf.assessed_by,
                                          'validation_version', cf.validation_version, 'rechecked', cf.recheck_of IS NOT NULL,
                                          'previous_support', (SELECT p.support FROM claim_fields p WHERE p.id = cf.recheck_of)) ORDER BY cf.field)
          FROM claim_fields cf WHERE cf.claim_id = c.id AND cf.source_document_id = ce.source_document_id AND cf.superseded_at IS NULL) AS fields,
       (SELECT json_agg(json_build_object('signal_id', s.id, 'title', s.title, 'classification', s.classification))
          FROM signal_claims sc JOIN signals s ON s.id = sc.signal_id WHERE sc.claim_id = c.id) AS signals
FROM claim_evidence ce JOIN claims c ON c.id = ce.claim_id
WHERE ce.source_document_id = CAST(:id AS uuid) ORDER BY ce.created_at"""
Q["document_passage_source"] = """
SELECT d.body_text, d.excerpt, d.content_hash, d.canonical_url, d.retrieved_at, d.read_progress FROM source_documents d WHERE d.id = CAST(:id AS uuid)"""
Q["document_rejections"] = """
SELECT id, claim_index, reason, raw, status, resolution_note, created_at FROM extraction_rejections
WHERE source_document_id = CAST(:id AS uuid) ORDER BY created_at"""
Q["review_documents"] = """
SELECT d.id, d.title, d.canonical_url, d.retrieved_at, d.language, d.extraction_status, d.extraction_detail, s.name AS source_name,
       s.authority
FROM source_documents d LEFT JOIN sources s ON s.id = d.source_id
WHERE d.extraction_status IN ('not_connected','budget_refused','failed','partial','pending','incomplete')
ORDER BY d.retrieved_at DESC LIMIT CAST(:limit AS int)"""
Q["review_claims"] = """
SELECT c.id::text AS claim_id, c.claim_type, c.status, c.subject_label, c.tender_ref, c.created_at,
       (SELECT ce.source_document_id::text FROM claim_evidence ce WHERE ce.claim_id = c.id ORDER BY ce.created_at LIMIT 1) AS document_id,
       (SELECT ce.excerpt FROM claim_evidence ce WHERE ce.claim_id = c.id ORDER BY ce.created_at LIMIT 1) AS quote,
       (SELECT count(*) FROM claim_fields cf WHERE cf.claim_id = c.id AND cf.support = 'unsupported' AND cf.superseded_at IS NULL) AS unsupported_fields,
       (SELECT count(*) FROM claim_fields cf WHERE cf.claim_id = c.id AND cf.support = 'review_required' AND cf.superseded_at IS NULL) AS review_fields,
       (SELECT s.title FROM signal_claims sc JOIN signals s ON s.id = sc.signal_id WHERE sc.claim_id = c.id LIMIT 1) AS signal_title
FROM claims c WHERE c.review_status = 'proposed' ORDER BY c.created_at DESC LIMIT CAST(:limit AS int)"""
Q["review_rejections"] = """
SELECT er.id, er.source_document_id::text AS document_id, er.reason, er.raw, er.created_at, d.title, d.canonical_url
FROM extraction_rejections er JOIN source_documents d ON d.id = er.source_document_id
WHERE er.status = 'open' ORDER BY er.created_at DESC LIMIT CAST(:limit AS int)"""
Q["review_merges"] = """
SELECT m.id, m.entity_type, m.left_id::text AS left_id, m.right_id::text AS right_id, m.reason, m.score, m.created_at,
       coalesce(ls.title, lo.canonical_name) AS left_label, coalesce(rs.title, ro.canonical_name) AS right_label
FROM merge_candidates m
LEFT JOIN signals ls ON m.entity_type = 'signal' AND ls.id = m.left_id LEFT JOIN signals rs ON m.entity_type = 'signal' AND rs.id = m.right_id
LEFT JOIN organisations lo ON m.entity_type = 'organisation' AND lo.id = m.left_id
LEFT JOIN organisations ro ON m.entity_type = 'organisation' AND ro.id = m.right_id
WHERE m.status = 'open' ORDER BY m.created_at DESC LIMIT CAST(:limit AS int)"""
Q["review_conflicts"] = """
SELECT c.id::text AS claim_id, cf.field, count(DISTINCT cf.normalised) AS distinct_values,
       json_agg(DISTINCT cf.normalised) AS values, max(s.title) AS signal_title
FROM claim_fields cf JOIN claims c ON c.id = cf.claim_id LEFT JOIN signal_claims sc ON sc.claim_id = c.id LEFT JOIN signals s ON s.id = sc.signal_id
WHERE cf.support = 'supported' AND cf.superseded_at IS NULL AND c.review_status <> 'rejected'
GROUP BY c.id, cf.field HAVING count(DISTINCT cf.normalised) > 1 LIMIT CAST(:limit AS int)"""
Q["rejection_resolve"] = """
UPDATE extraction_rejections SET status = CAST(:status AS text), resolution_note = CAST(:note AS text), resolved_at = now()
WHERE id = CAST(:id AS uuid) AND status = 'open' RETURNING id"""
Q["merge_candidate_lock"] = "SELECT * FROM merge_candidates WHERE id = CAST(:id AS uuid) FOR UPDATE"
Q["merge_candidate_decide"] = """
UPDATE merge_candidates SET status = CAST(:status AS text), decision_note = CAST(:note AS text), decided_at = now()
WHERE id = CAST(:id AS uuid)"""
Q["signal_claims_move"] = """
INSERT INTO signal_claims (signal_id, claim_id) SELECT CAST(:dst AS uuid), claim_id FROM signal_claims WHERE signal_id = CAST(:src AS uuid)
ON CONFLICT DO NOTHING"""
Q["signal_geo_move"] = """
INSERT INTO signal_geography (signal_id, country_code, role, support)
SELECT CAST(:dst AS uuid), country_code, role, support FROM signal_geography WHERE signal_id = CAST(:src AS uuid)
ON CONFLICT (signal_id, country_code, role) DO UPDATE
SET support = CASE WHEN signal_geography.support = 'supported' OR EXCLUDED.support = 'supported' THEN 'supported' ELSE 'unverified' END"""
Q["signal_mark_merged"] = "UPDATE signals SET merged_into_id = CAST(:into AS uuid) WHERE id = CAST(:id AS uuid)"
Q["opportunity_repoint_signal"] = "UPDATE opportunities SET signal_id = CAST(:signal AS uuid) WHERE id = CAST(:id AS uuid)"
Q["opportunity_mark_merged"] = """
UPDATE opportunities SET merged_into_id = CAST(:into AS uuid), commercial_stage = 'deferred' WHERE id = CAST(:id AS uuid)"""
Q["organisation_import_refs"] = """
SELECT (SELECT count(*) FROM bookings WHERE forwarder_id = CAST(:id AS uuid) OR airline_id = CAST(:id AS uuid))
     + (SELECT count(*) FROM quotes WHERE forwarder_id = CAST(:id AS uuid))
     + (SELECT count(*) FROM representation_agreements WHERE airline_id = CAST(:id AS uuid))"""
Q["organisation_merge_refs"] = """
WITH a AS (UPDATE claims SET subject_organisation_id = CAST(:dst AS uuid) WHERE subject_organisation_id = CAST(:src AS uuid) RETURNING 1),
     b AS (UPDATE signals SET subject_organisation_id = CAST(:dst AS uuid) WHERE subject_organisation_id = CAST(:src AS uuid) RETURNING 1),
     c AS (UPDATE opportunities SET organisation_id = CAST(:dst AS uuid) WHERE organisation_id = CAST(:src AS uuid) RETURNING 1),
     d AS (UPDATE people SET organisation_id = CAST(:dst AS uuid) WHERE organisation_id = CAST(:src AS uuid) RETURNING 1)
INSERT INTO organisation_aliases (organisation_id, alias, alias_norm, provenance_id)
SELECT CAST(:dst AS uuid), alias, alias_norm, provenance_id FROM organisation_aliases WHERE organisation_id = CAST(:src AS uuid)
ON CONFLICT DO NOTHING"""
Q["organisation_mark_merged"] = """
WITH m AS (UPDATE organisations SET merged_into_id = CAST(:into AS uuid) WHERE id = CAST(:id AS uuid) RETURNING id)
INSERT INTO organisation_merges (survivor_id, merged_id, reason, proposed_by)
SELECT CAST(:into AS uuid), id, 'reviewer decision on a merge candidate', 'fuzzy_match' FROM m"""
Q["organisation_merge_airline_refs"] = """
WITH a AS (UPDATE claims SET airline_id = CAST(:dst AS uuid) WHERE airline_id = CAST(:src AS uuid) RETURNING 1)
UPDATE opportunities SET airline_id = CAST(:dst AS uuid) WHERE airline_id = CAST(:src AS uuid)"""

# ---------------------------------------------------------------- directive wfc_0002: imports
Q["source_mark_import"] = "UPDATE sources SET source_type = 'file_import' WHERE id = CAST(:id AS uuid)"
Q["import_file_store"] = """
INSERT INTO import_files (import_job_id, content, naive_timezone, plan_fingerprint)
VALUES (CAST(:job AS uuid), CAST(:content AS bytea), CAST(:tz AS text), CAST(:fingerprint AS text))"""
Q["import_file_get"] = "SELECT content, naive_timezone, plan_fingerprint FROM import_files WHERE import_job_id = CAST(:id AS uuid)"
Q["import_commit_for_preview"] = "SELECT id FROM import_jobs WHERE preview_job_id = CAST(:id AS uuid) AND mode = 'commit'"
Q["import_job_insert2"] = """
INSERT INTO import_jobs (dataset, source_id, file_name, file_sha256, schema_version, mapping, mode, status, totals, session_ref,
                         preview_job_id, partial)
VALUES (CAST(:dataset AS text), CAST(:source_id AS uuid), CAST(:file_name AS text), CAST(:sha AS text), CAST(:schema_version AS text),
        CAST(:mapping AS jsonb), CAST(:mode AS text), CAST(:status AS text), CAST(:totals AS jsonb), CAST(:session_ref AS text),
        CAST(:preview AS uuid), CAST(:partial AS boolean))
RETURNING id"""
Q["station_id"] = "SELECT id FROM stations WHERE code = CAST(:code AS text)"
Q["existing_trucking"] = """
SELECT r.external_id, org.canonical_name AS provider, st.code AS origin_station, ap.iata_code AS gateway,
       array_to_string(r.departure_days, ';') AS departure_days, to_char(r.departure_time_local, 'HH24:MI') AS departure_time,
       r.transit_minutes, r.restrictions
FROM road_feeder_services r LEFT JOIN organisations org ON org.id = r.provider_organisation_id
JOIN stations st ON st.id = r.origin_station_id JOIN airports ap ON ap.id = r.gateway_airport_id
WHERE r.source_id = CAST(:source AS uuid)"""
Q["existing_finance"] = """
SELECT oc.name AS operating_company, f.period_start, f.period_end, f.metric, f.amount, f.currency, f.basis
FROM financial_aggregates f JOIN operating_companies oc ON oc.id = f.operating_company_id WHERE f.source_id = CAST(:source AS uuid)"""
Q["existing_channel_events"] = """
SELECT e.external_id, e.event_type, e.session_key, e.booking_external_id AS booking_ref, e.channel, e.occurred_at,
       org.canonical_name AS forwarder
FROM channel_events e LEFT JOIN organisations org ON org.id = e.forwarder_id WHERE e.source_id = CAST(:source AS uuid)"""
Q["existing_credentials"] = """
SELECT tc.external_id, oc.name AS operating_company, tc.credential_type, s.code AS service_code, ap.iata_code AS station,
       tc.holder_description, tc.issued_on, tc.expires_on
FROM training_credentials tc JOIN operating_companies oc ON oc.id = tc.operating_company_id
LEFT JOIN services s ON s.id = tc.service_id LEFT JOIN airports ap ON ap.id = tc.station_airport_id
WHERE tc.source_id = CAST(:source AS uuid) AND tc.external_id IS NOT NULL"""
Q["existing_gateway_connections"] = """
SELECT gc.external_id, ga.iata_code AS gateway, da.iata_code AS destination, a.iata_code AS airline_iata, gc.flight_number,
       array_to_string(gc.departure_days, ';') AS departure_days, to_char(gc.departure_time_local, 'HH24:MI') AS departure_time,
       gc.connection_cutoff_minutes
FROM gateway_connections gc JOIN airports ga ON ga.id = gc.gateway_airport_id
LEFT JOIN trade_lanes l ON l.id = gc.trade_lane_id LEFT JOIN airports da ON da.id = l.destination_airport_id
LEFT JOIN airlines a ON a.organisation_id = gc.airline_id
WHERE gc.source_id = CAST(:source AS uuid) AND gc.external_id IS NOT NULL"""
Q["existing_contacts"] = """
SELECT p.external_id, p.full_name, p.role_title, org.canonical_name AS organisation, oc.name AS operating_company, p.email, p.is_internal
FROM people p LEFT JOIN organisations org ON org.id = p.organisation_id LEFT JOIN operating_companies oc ON oc.id = p.operating_company_id
WHERE p.external_id IS NOT NULL"""
Q["existing_airports"] = "SELECT iata_code, icao_code, name, country::text AS country, timezone FROM airports"
Q["existing_airlines"] = """
SELECT a.iata_code, o.canonical_name AS name, a.icao_code, a.awb_prefix, o.country::text AS country
FROM airlines a JOIN organisations o ON o.id = a.organisation_id WHERE a.iata_code IS NOT NULL"""
Q["existing_territories"] = "SELECT code, name, kind, country_code::text AS country FROM territories"
Q["existing_services"] = "SELECT code, name, category FROM services"
Q["existing_stations"] = "SELECT code, name, is_offline, country::text AS country, timezone FROM stations"
Q["existing_operating_companies"] = """
SELECT name, legal_entity_name, country::text AS country, is_group_member FROM operating_companies"""
Q["existing_service_requirements"] = """
SELECT s.code AS service_code, r.credential_type FROM service_credential_requirements r JOIN services s ON s.id = r.service_id"""
_DAYS = "ARRAY(SELECT jsonb_array_elements_text(CAST(:days AS jsonb)))::smallint[]"
Q["trucking_upsert"] = f"""
INSERT INTO road_feeder_services (source_id, external_id, provider_organisation_id, origin_station_id, gateway_airport_id, departure_days,
                                  departure_time_local, transit_minutes, restrictions, provenance_id)
VALUES (CAST(:source AS uuid), CAST(:external_id AS text), CAST(:provider AS uuid), CAST(:station AS uuid), CAST(:gateway AS uuid),
        {_DAYS}, CAST(:time AS time), CAST(:transit AS int), CAST(:restrictions AS text), CAST(:prov AS uuid))
ON CONFLICT (source_id, external_id) DO UPDATE SET provider_organisation_id = EXCLUDED.provider_organisation_id,
    origin_station_id = EXCLUDED.origin_station_id, gateway_airport_id = EXCLUDED.gateway_airport_id,
    departure_days = EXCLUDED.departure_days, departure_time_local = EXCLUDED.departure_time_local,
    transit_minutes = EXCLUDED.transit_minutes, restrictions = EXCLUDED.restrictions, provenance_id = EXCLUDED.provenance_id
RETURNING id"""
Q["finance_upsert"] = """
INSERT INTO financial_aggregates (source_id, operating_company_id, period_start, period_end, metric, amount, currency, basis, provenance_id)
VALUES (CAST(:source AS uuid), CAST(:company AS uuid), CAST(:period_start AS date), CAST(:period_end AS date), CAST(:metric AS text),
        CAST(:amount AS numeric), CAST(:currency AS text), CAST(:basis AS text), CAST(:prov AS uuid))
ON CONFLICT (source_id, operating_company_id, period_start, period_end, metric, currency) DO UPDATE
SET amount = EXCLUDED.amount, basis = EXCLUDED.basis, provenance_id = EXCLUDED.provenance_id
RETURNING id"""
Q["channel_event_upsert"] = """
INSERT INTO channel_events (source_id, external_id, event_type, session_key, booking_external_id, channel, occurred_at, forwarder_id,
                            provenance_id)
VALUES (CAST(:source AS uuid), CAST(:external_id AS text), CAST(:event_type AS text), CAST(:session_key AS text),
        CAST(:booking_ref AS text), CAST(:channel AS text), CAST(:occurred_at AS timestamptz), CAST(:forwarder AS uuid), CAST(:prov AS uuid))
ON CONFLICT (source_id, external_id) DO UPDATE SET event_type = EXCLUDED.event_type, session_key = EXCLUDED.session_key,
    booking_external_id = EXCLUDED.booking_external_id, channel = EXCLUDED.channel, occurred_at = EXCLUDED.occurred_at,
    forwarder_id = EXCLUDED.forwarder_id, provenance_id = EXCLUDED.provenance_id
RETURNING id"""
Q["credential_upsert"] = """
INSERT INTO training_credentials (source_id, external_id, operating_company_id, service_id, credential_type, holder_description,
                                  station_airport_id, issued_on, expires_on, provenance_id)
VALUES (CAST(:source AS uuid), CAST(:external_id AS text), CAST(:company AS uuid), CAST(:service AS uuid), CAST(:credential_type AS text),
        CAST(:holder AS text), CAST(:station AS uuid), CAST(:issued_on AS date), CAST(:expires_on AS date), CAST(:prov AS uuid))
ON CONFLICT (source_id, external_id) WHERE external_id IS NOT NULL DO UPDATE SET operating_company_id = EXCLUDED.operating_company_id,
    service_id = EXCLUDED.service_id, credential_type = EXCLUDED.credential_type, holder_description = EXCLUDED.holder_description,
    station_airport_id = EXCLUDED.station_airport_id, issued_on = EXCLUDED.issued_on, expires_on = EXCLUDED.expires_on,
    provenance_id = EXCLUDED.provenance_id
RETURNING id"""
Q["airport_upsert"] = """
INSERT INTO airports (iata_code, icao_code, name, country, timezone)
VALUES (CAST(:iata AS text), CAST(:icao AS text), CAST(:name AS text), CAST(:country AS text), CAST(:tz AS text))
ON CONFLICT (iata_code) DO UPDATE SET icao_code = EXCLUDED.icao_code, name = EXCLUDED.name, country = EXCLUDED.country,
    timezone = EXCLUDED.timezone
RETURNING id"""
Q["org_set_country"] = "UPDATE organisations SET country = coalesce(CAST(:country AS text), country) WHERE id = CAST(:id AS uuid)"
Q["org_set_name"] = """
UPDATE organisations SET canonical_name = CAST(:name AS text), updated_at = now()
WHERE id = CAST(:id AS uuid) AND canonical_name IS DISTINCT FROM CAST(:name AS text)"""
Q["airline_upsert"] = """
INSERT INTO airlines (organisation_id, iata_code, icao_code, awb_prefix)
VALUES (CAST(:org AS uuid), CAST(:iata AS text), CAST(:icao AS text), CAST(:awb AS text))
ON CONFLICT (organisation_id) DO UPDATE SET iata_code = EXCLUDED.iata_code, icao_code = EXCLUDED.icao_code, awb_prefix = EXCLUDED.awb_prefix"""
Q["company_upsert"] = """
INSERT INTO operating_companies (name, legal_entity_name, country, is_group_member, provenance_id)
VALUES (CAST(:name AS text), CAST(:legal AS text), CAST(:country AS text), CAST(:member AS boolean), CAST(:prov AS uuid))
ON CONFLICT (name) DO UPDATE SET legal_entity_name = EXCLUDED.legal_entity_name, country = EXCLUDED.country,
    is_group_member = EXCLUDED.is_group_member
RETURNING id"""
Q["territory_upsert"] = """
INSERT INTO territories (code, name, kind, country_code)
VALUES (CAST(:code AS text), CAST(:name AS text), CAST(:kind AS text), CAST(:country AS text))
ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name, kind = EXCLUDED.kind, country_code = EXCLUDED.country_code
RETURNING id"""
Q["territory_set_country"] = """
UPDATE territories SET country_code = CAST(:country AS text)
WHERE id = CAST(:id AS uuid) AND CAST(:country AS text) IN (SELECT code FROM countries)"""
Q["service_upsert"] = """
INSERT INTO services (code, name, category) VALUES (CAST(:code AS text), CAST(:name AS text), CAST(:category AS text))
ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name, category = EXCLUDED.category RETURNING id"""
Q["service_requirement_add"] = """
INSERT INTO service_credential_requirements (service_id, credential_type) VALUES (CAST(:service AS uuid), CAST(:credential AS text))
ON CONFLICT DO NOTHING"""
Q["service_requirement_delete"] = """
DELETE FROM service_credential_requirements WHERE service_id = CAST(:service AS uuid) AND credential_type = CAST(:credential AS text)"""
Q["contact_upsert"] = """
INSERT INTO people (external_id, full_name, role_title, organisation_id, operating_company_id, email, is_internal, provenance_id)
VALUES (CAST(:external_id AS text), CAST(:full_name AS text), CAST(:role_title AS text), CAST(:org AS uuid), CAST(:company AS uuid),
        CAST(:email AS text), CAST(:internal AS boolean), CAST(:prov AS uuid))
ON CONFLICT (external_id) WHERE external_id IS NOT NULL DO UPDATE SET full_name = EXCLUDED.full_name, role_title = EXCLUDED.role_title,
    organisation_id = EXCLUDED.organisation_id, operating_company_id = EXCLUDED.operating_company_id, email = EXCLUDED.email,
    is_internal = EXCLUDED.is_internal
RETURNING id"""
Q["station_upsert"] = """
INSERT INTO stations (code, name, is_offline, country, timezone)
VALUES (CAST(:code AS text), CAST(:name AS text), CAST(:offline AS boolean), CAST(:country AS text), CAST(:tz AS text))
ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name, is_offline = EXCLUDED.is_offline, country = EXCLUDED.country,
    timezone = EXCLUDED.timezone
RETURNING id"""
Q["gateway_upsert"] = f"""
INSERT INTO gateway_connections (source_id, external_id, gateway_airport_id, airline_id, trade_lane_id, flight_number, departure_days,
                                 departure_time_local, connection_cutoff_minutes, provenance_id)
VALUES (CAST(:source AS uuid), CAST(:external_id AS text), CAST(:gateway AS uuid), CAST(:airline AS uuid), CAST(:lane AS uuid),
        CAST(:flight AS text), {_DAYS}, CAST(:time AS time), CAST(:cutoff AS int), CAST(:prov AS uuid))
ON CONFLICT (source_id, external_id) WHERE external_id IS NOT NULL DO UPDATE SET gateway_airport_id = EXCLUDED.gateway_airport_id,
    airline_id = EXCLUDED.airline_id, trade_lane_id = EXCLUDED.trade_lane_id, flight_number = EXCLUDED.flight_number,
    departure_days = EXCLUDED.departure_days, departure_time_local = EXCLUDED.departure_time_local,
    connection_cutoff_minutes = EXCLUDED.connection_cutoff_minutes, provenance_id = EXCLUDED.provenance_id
RETURNING id"""
Q["quote_delete"] = "DELETE FROM quotes WHERE id = CAST(:id AS uuid)"
Q["capacity_delete"] = "DELETE FROM capacity_snapshots WHERE id = CAST(:id AS uuid)"
Q["trucking_delete"] = "DELETE FROM road_feeder_services WHERE id = CAST(:id AS uuid)"
Q["finance_delete"] = "DELETE FROM financial_aggregates WHERE id = CAST(:id AS uuid)"
Q["channel_event_delete"] = "DELETE FROM channel_events WHERE id = CAST(:id AS uuid)"
Q["credential_delete"] = "DELETE FROM training_credentials WHERE id = CAST(:id AS uuid)"
Q["gateway_delete"] = "DELETE FROM gateway_connections WHERE id = CAST(:id AS uuid)"
Q["airport_delete"] = "DELETE FROM airports WHERE id = CAST(:id AS uuid)"
Q["station_delete"] = "DELETE FROM stations WHERE id = CAST(:id AS uuid)"
Q["contact_delete"] = "DELETE FROM people WHERE id = CAST(:id AS uuid)"

# ---------------------------------------------------------------- directive wfc_0002: prioritisation
Q["opportunity_priority_facts"] = """
SELECT o.id, o.module, o.deadline_utc, o.deadline_earliest_utc, o.deadline_info, o.owner_person_id, o.module_facts, o.airline_id,
       s.first_published_at,
       (SELECT count(DISTINCT d.announcement_family_id) FROM signal_claims sc JOIN claim_evidence ce ON ce.claim_id = sc.claim_id
          JOIN source_documents d ON d.id = ce.source_document_id WHERE sc.signal_id = o.signal_id AND ce.stance = 'supports'
          AND ce.excluded_at IS NULL) AS families,
       (SELECT src.authority FROM signal_claims sc JOIN claim_evidence ce ON ce.claim_id = sc.claim_id
          JOIN source_documents d ON d.id = ce.source_document_id JOIN sources src ON src.id = d.source_id
         WHERE sc.signal_id = o.signal_id AND ce.stance = 'supports' AND ce.excluded_at IS NULL
         ORDER BY CASE src.authority WHEN 'official_portal' THEN 0 WHEN 'internal_record' THEN 0 WHEN 'company_release' THEN 1
                  WHEN 'trade_press' THEN 2 ELSE 3 END LIMIT 1) AS best_authority,
       (SELECT count(*) FROM signal_claims sc JOIN claims c ON c.id = sc.claim_id WHERE sc.signal_id = o.signal_id
          AND c.status = 'contradicted') AS contradicted,
       (cardinality(o.required_credentials) > 0 OR EXISTS (SELECT 1 FROM service_credential_requirements r WHERE r.service_id = o.service_id))
          AS credentials_required,
       cv.basis, cv.currency, cv.wfc_remuneration, cv.incremental_costs, cv.guarantee_exposure, cv.duration_months,
       (SELECT count(*) FROM representation_agreements ra WHERE ra.airline_id = o.airline_id AND ra.status = 'active') AS agreements_elsewhere,
       EXISTS (SELECT 1 FROM people p WHERE p.organisation_id = coalesce(o.airline_id, o.organisation_id)) AS has_contact,
       EXISTS (SELECT 1 FROM engagements e WHERE e.organisation_id = coalesce(o.airline_id, o.organisation_id)) AS has_engagement
FROM opportunities o LEFT JOIN signals s ON s.id = o.signal_id LEFT JOIN commercial_values cv ON cv.opportunity_id = o.id
WHERE o.id = CAST(:id AS uuid)"""
Q["assessments_clear"] = "DELETE FROM assessments WHERE opportunity_id = CAST(:opp AS uuid)"

# ---------------------------------------------------------------- directive wfc_0002: capability areas
Q["dataset_freshness"] = """
SELECT s.freshness_sla_hours,
       (SELECT max(r.finished_at) FROM ingestion_runs r WHERE r.source_id = s.id AND r.status = 'succeeded') AS last_success_at
FROM sources s WHERE s.name = CAST(:name AS text)"""
Q["agreements_all"] = """
SELECT ra.airline_id::text AS airline_id, org.canonical_name AS airline_name, oc.name AS operating_company, ra.effective_from,
       ra.effective_to, ra.exclusivity, ra.appointment_rights, ra.status,
       (SELECT coalesce(json_agg(t.code ORDER BY t.code), '[]'::json) FROM agreement_territories at JOIN territories t ON t.id = at.territory_id
         WHERE at.agreement_id = ra.id) AS territories,
       (SELECT coalesce(json_agg(s.code ORDER BY s.code), '[]'::json) FROM agreement_services asv JOIN services s ON s.id = asv.service_id
         WHERE asv.agreement_id = ra.id) AS services
FROM representation_agreements ra JOIN operating_companies oc ON oc.id = ra.operating_company_id
JOIN organisations org ON org.id = ra.airline_id"""
Q["third_party_all"] = """
SELECT tp.airline_id::text AS airline_id, t.code AS territory, s.code AS service, org.canonical_name AS holder, tp.exclusivity, tp.valid_to
FROM third_party_appointments tp JOIN territories t ON t.id = tp.territory_id
LEFT JOIN services s ON s.id = tp.service_id LEFT JOIN organisations org ON org.id = tp.holder_organisation_id"""
Q["credentials_all2"] = """
SELECT oc.name AS operating_company, tc.credential_type, tc.expires_on, tc.issued_on, ap.iata_code AS station
FROM training_credentials tc JOIN operating_companies oc ON oc.id = tc.operating_company_id
LEFT JOIN airports ap ON ap.id = tc.station_airport_id"""
Q["service_requirements_all"] = """
SELECT s.code AS service_code, r.credential_type FROM service_credential_requirements r JOIN services s ON s.id = r.service_id"""
Q["airports_brief"] = "SELECT iata_code, country::text AS country, name, timezone FROM airports ORDER BY iata_code"
Q["bookings_by_airline"] = """
SELECT airline_id::text AS airline_id, count(*) AS n FROM bookings WHERE airline_id IS NOT NULL AND status <> 'cancelled' GROUP BY airline_id"""
Q["opportunity_by_origin"] = "SELECT id FROM opportunities WHERE origin_ref = CAST(:ref AS text) AND merged_into_id IS NULL"
Q["forwarder_quote_stats"] = """
SELECT count(*) FILTER (WHERE status = 'won') AS won, count(*) FILTER (WHERE status = 'lost') AS lost,
       count(*) FILTER (WHERE status = 'lost' AND lost_reason ILIKE '%price%') AS lost_price
FROM quotes WHERE forwarder_id = CAST(:forwarder AS uuid) AND quoted_at >= CAST(:since AS timestamptz)"""
Q["forwarder_bookings_12m"] = """
SELECT count(*) FROM bookings WHERE forwarder_id = CAST(:forwarder AS uuid) AND status <> 'cancelled' AND flight_date >= CAST(:since AS date)"""
Q["lane_period_weight"] = """
SELECT sum(chargeable_weight_kg) FILTER (WHERE status <> 'cancelled') AS chargeable_kg,
       count(*) FILTER (WHERE status <> 'cancelled' AND chargeable_weight_kg IS NULL) AS missing
FROM bookings WHERE trade_lane_id = CAST(:lane AS uuid) AND flight_date BETWEEN CAST(:start AS date) AND CAST(:end AS date)"""
Q["lane_capacity_series"] = """
SELECT period_start, period_end, basis, capacity_type, amount, snapshot_at FROM capacity_snapshots
WHERE trade_lane_id = CAST(:lane AS uuid) ORDER BY basis, capacity_type, period_start, snapshot_at"""
Q["stations_offline"] = "SELECT code, name, country::text AS country, timezone FROM stations WHERE is_offline ORDER BY code"
Q["gateway_connections_for2"] = """
SELECT ga.iata_code AS gateway, gc.departure_days, gc.departure_time_local, gc.connection_cutoff_minutes, a.iata_code AS airline,
       gc.flight_number, da.iata_code AS destination
FROM gateway_connections gc JOIN airports ga ON ga.id = gc.gateway_airport_id
LEFT JOIN airlines a ON a.organisation_id = gc.airline_id
LEFT JOIN trade_lanes l ON l.id = gc.trade_lane_id LEFT JOIN airports da ON da.id = l.destination_airport_id
WHERE ga.iata_code = CAST(:gateway AS text) ORDER BY gc.departure_time_local"""
Q["module_demand"] = """
SELECT o.id::text AS id, o.title, sv.code AS service, o.deadline_utc, o.deadline_info, o.qualification_status, o.delivery_start, o.required_credentials,
       s.classification, o.tender_status, o.freight_scope, o.origin_ref,
       ARRAY(SELECT g.country_code::text FROM opportunity_geography g WHERE g.opportunity_id = o.id
             AND g.role IN ('delivery','contract_territory') AND g.support IN ('supported','internal_record')) AS countries
FROM opportunities o LEFT JOIN services sv ON sv.id = o.service_id LEFT JOIN signals s ON s.id = o.signal_id
WHERE o.module = CAST(:module AS text) AND o.merged_into_id IS NULL AND o.commercial_stage NOT IN ('won','lost','expired')
ORDER BY o.deadline_latest_utc NULLS LAST"""
Q["digital_adoption"] = """
WITH b AS (
  SELECT forwarder_id, count(*) AS bookings FROM bookings
  WHERE forwarder_id IS NOT NULL AND status <> 'cancelled' AND flight_date BETWEEN CAST(:start AS date) AND CAST(:end AS date)
  GROUP BY forwarder_id),
e AS (
  SELECT forwarder_id, count(*) AS events, count(*) FILTER (WHERE event_type = 'booking') AS digital_bookings,
         count(*) FILTER (WHERE event_type = 'integration_failure') AS failures
  FROM channel_events WHERE forwarder_id IS NOT NULL AND occurred_at >= CAST(:lo AS timestamptz) AND occurred_at < CAST(:hi AS timestamptz)
  GROUP BY forwarder_id)
SELECT o.id::text AS forwarder_id, o.canonical_name AS forwarder, coalesce(b.bookings, 0) AS bookings, coalesce(e.events, 0) AS digital_events,
       coalesce(e.digital_bookings, 0) AS digital_bookings, coalesce(e.failures, 0) AS integration_failures,
       (coalesce(b.bookings, 0) > 0 AND coalesce(e.events, 0) = 0) AS adoption_gap
FROM organisations o LEFT JOIN b ON b.forwarder_id = o.id LEFT JOIN e ON e.forwarder_id = o.id
WHERE o.kind = 'forwarder' AND o.merged_into_id IS NULL AND (b.bookings IS NOT NULL OR e.events IS NOT NULL)
ORDER BY (coalesce(b.bookings, 0) > 0 AND coalesce(e.events, 0) = 0) DESC, coalesce(b.bookings, 0) DESC"""
Q["combined_service_candidates"] = """
SELECT o.id::text AS forwarder_id, o.canonical_name AS forwarder,
       array_agg(DISTINCT ap.iata_code) AS gateways, count(DISTINCT bk.id) AS bookings_via_gateways
FROM organisations o
JOIN bookings bk ON bk.forwarder_id = o.id AND bk.status <> 'cancelled' AND bk.flight_date BETWEEN CAST(:start AS date) AND CAST(:end AS date)
JOIN trade_lanes l ON l.id = bk.trade_lane_id
JOIN airports ap ON ap.id IN (l.origin_airport_id, l.destination_airport_id)
WHERE EXISTS (SELECT 1 FROM road_feeder_services r WHERE r.gateway_airport_id = ap.id)
  AND EXISTS (SELECT 1 FROM channel_events ce WHERE ce.forwarder_id = o.id AND ce.occurred_at >= CAST(:lo AS timestamptz)
              AND ce.occurred_at < CAST(:hi AS timestamptz))
GROUP BY o.id, o.canonical_name ORDER BY count(DISTINCT bk.id) DESC"""
Q["opportunity_insert_module"] = """
INSERT INTO opportunities (module, dedup_key, title, airline_id, organisation_id, territory_id, service_id, operating_company_id,
                           station_airport_id, origin_ref, module_facts, notes)
VALUES (CAST(:module AS text), CAST(:key AS text), CAST(:title AS text), CAST(:airline AS uuid), CAST(:org AS uuid), CAST(:territory AS uuid),
        CAST(:service AS uuid), CAST(:company AS uuid), CAST(:station AS uuid), CAST(:origin AS text), CAST(:facts AS jsonb), CAST(:notes AS text))
RETURNING id"""
Q["opportunity_geo_internal"] = """
INSERT INTO opportunity_geography (opportunity_id, country_code, role, support) VALUES (CAST(:opp AS uuid), CAST(:country AS text),
       'delivery', 'internal_record') ON CONFLICT DO NOTHING"""
Q["exception_set_owner"] = """
UPDATE operational_exceptions SET owner_person_id = CAST(:person AS uuid) WHERE id = CAST(:id AS uuid) RETURNING id"""
Q["task_set_owner_for_source"] = """
UPDATE tasks SET owner_person_id = CAST(:owner AS uuid) WHERE source_type = CAST(:source_type AS text) AND source_id = CAST(:source_id AS uuid)"""
Q["exception_acknowledge"] = """
UPDATE operational_exceptions SET status = 'acknowledged' WHERE id = CAST(:id AS uuid) AND status = 'open' RETURNING id"""

# ---------------------------------------------------------------- directive wfc_0002: API views
Q["schedules_for_search"] = "SELECT id FROM schedules WHERE scope_search_id = CAST(:search AS uuid)"
Q["runs_list"] = """
SELECT r.id, r.search_id, r.source_id, r.trigger, r.status, r.outcome, r.counts, r.progress, r.estimated_cost_usd, r.actual_cost_usd,
       r.created_at, r.started_at, r.finished_at, r.error, ds.name AS search_name, src.name AS source_name,
       r.plan->'countries' AS countries, r.plan->'modules' AS modules, r.plan->>'coverage_note' AS coverage_note
FROM discovery_runs r LEFT JOIN discovery_searches ds ON ds.id = r.search_id LEFT JOIN sources src ON src.id = r.source_id
WHERE (CAST(:search AS uuid) IS NULL OR r.search_id = CAST(:search AS uuid))
  AND (CAST(:source AS uuid) IS NULL OR r.source_id = CAST(:source AS uuid))
ORDER BY r.created_at DESC LIMIT CAST(:limit AS int)"""
Q["run_retry_of"] = """
SELECT r.id, r.job_id, r.plan FROM discovery_runs r JOIN jobs j ON j.id = r.job_id
WHERE j.retry_of = CAST(:job AS uuid) ORDER BY r.created_at LIMIT 1"""
Q["run_sources"] = """
SELECT rs.source_id, s.name, s.authority, s.source_type, rs.status, rs.detail, rs.documents, rs.new_documents, rs.failures, rs.issues
FROM discovery_run_sources rs JOIN sources s ON s.id = rs.source_id WHERE rs.run_id = CAST(:run AS uuid) ORDER BY s.name"""
Q["job_get"] = "SELECT * FROM jobs WHERE id = CAST(:id AS uuid)"
Q["job_retry_count"] = "SELECT count(*) FROM jobs WHERE retry_of = CAST(:id AS uuid)"
Q["jobs_list2"] = """
SELECT j.id, j.job_type, j.execution_key, j.status, j.attempts, j.max_attempts, j.run_after, j.lease_owner, j.last_error, j.created_at,
       j.finished_at, j.retry_of, j.progress, (SELECT r.id FROM discovery_runs r WHERE r.job_id = j.id LIMIT 1) AS discovery_run_id
FROM jobs j WHERE (CAST(:status AS text) IS NULL OR j.status = CAST(:status AS text))
ORDER BY j.created_at DESC LIMIT CAST(:limit AS int)"""
Q["document_has_body"] = "SELECT body_text IS NOT NULL FROM source_documents WHERE id = CAST(:id AS uuid)"
Q["signal_evidence_view"] = """
SELECT c.id::text AS claim_id, c.claim_type, c.status, c.review_status, c.review_note, c.tender_ref, ce.stance, ce.excerpt AS quote, ce.assessed_by,
       ce.excluded_at, ce.page_ref AS location, ce.created_at AS assessed_at, d.id::text AS document_id, d.title, d.canonical_url,
       d.original_url, d.published_at, d.retrieved_at, d.content_hash AS document_version, d.language,
       (d.body_text IS NOT NULL) AS text_retained,
       d.summary_en, d.summary_is_translation, f.family_key, s.name AS source_name, s.authority,
       (SELECT dc.result FROM document_checks dc WHERE dc.source_document_id = d.id AND dc.check_type = 'authenticity'
         ORDER BY dc.checked_at DESC LIMIT 1) AS authenticity,
       (SELECT json_agg(json_build_object('field', cf.field, 'value', cf.value, 'normalised', cf.normalised, 'quote', cf.quote,
                                          'support', cf.support, 'reason', cf.reason, 'assessed_by', cf.assessed_by,
                                          'validation_version', cf.validation_version, 'rechecked', cf.recheck_of IS NOT NULL,
                                          'previous_support', (SELECT p.support FROM claim_fields p WHERE p.id = cf.recheck_of)) ORDER BY cf.field)
          FROM claim_fields cf WHERE cf.claim_id = c.id AND cf.source_document_id = d.id AND cf.superseded_at IS NULL) AS fields
FROM signal_claims sc JOIN claims c ON c.id = sc.claim_id JOIN claim_evidence ce ON ce.claim_id = c.id
JOIN source_documents d ON d.id = ce.source_document_id LEFT JOIN announcement_families f ON f.id = d.announcement_family_id
LEFT JOIN sources s ON s.id = d.source_id
WHERE sc.signal_id = CAST(:signal AS uuid) ORDER BY coalesce(d.published_at, d.retrieved_at), c.claim_type"""

# ---------------------------------------------------------------- directive wfc_0002: economics, network, referrals
Q["module_opportunity_count"] = """
SELECT count(*) FROM opportunities WHERE module = CAST(:module AS text) AND merged_into_id IS NULL"""
Q["network_count"] = "SELECT count(*) FROM network_candidates"
Q["value_upsert"] = """
INSERT INTO commercial_values (opportunity_id, currency, airline_revenue, wfc_remuneration, incremental_costs, guarantee_exposure,
                               duration_months, basis, assumptions, value_kind)
VALUES (CAST(:opp AS uuid), CAST(:currency AS text), CAST(:revenue AS numeric), CAST(:remuneration AS numeric), CAST(:costs AS numeric),
        CAST(:exposure AS numeric), CAST(:months AS int), CAST(:basis AS text), CAST(:assumptions AS jsonb), CAST(:kind AS text))
ON CONFLICT (opportunity_id) DO UPDATE SET currency = EXCLUDED.currency, airline_revenue = EXCLUDED.airline_revenue,
    wfc_remuneration = EXCLUDED.wfc_remuneration, incremental_costs = EXCLUDED.incremental_costs,
    guarantee_exposure = EXCLUDED.guarantee_exposure, duration_months = EXCLUDED.duration_months, basis = EXCLUDED.basis,
    assumptions = EXCLUDED.assumptions, value_kind = EXCLUDED.value_kind, updated_at = now()"""
Q["value_set_retained"] = """
UPDATE commercial_values SET retained_contribution = CAST(:retained AS numeric) WHERE opportunity_id = CAST(:opp AS uuid)"""
Q["opportunity_group"] = "SELECT id, competition_group_id FROM opportunities WHERE id = CAST(:id AS uuid)"
Q["opportunity_set_group"] = "UPDATE opportunities SET competition_group_id = CAST(:grp AS uuid) WHERE id = CAST(:id AS uuid)"
Q["referral_insert"] = """
INSERT INTO referrals (opportunity_id, from_company_id, to_company_id) VALUES (CAST(:opp AS uuid), CAST(:src AS uuid), CAST(:dst AS uuid))
ON CONFLICT (opportunity_id, to_company_id) DO NOTHING RETURNING id"""
# Allowed transitions only: proposed -> accepted | declined; accepted -> closed. A proposed referral cannot be
# "closed" into the receiver's figures without having been accepted.
Q["referral_set_status"] = """
UPDATE referrals SET status = CAST(:status AS text) WHERE id = CAST(:id AS uuid)
  AND ((status = 'proposed' AND CAST(:status AS text) IN ('accepted','declined')) OR (status = 'accepted' AND CAST(:status AS text) = 'closed'))
RETURNING id"""
Q["referral_get"] = "SELECT id, status FROM referrals WHERE id = CAST(:id AS uuid)"
Q["referrals_list"] = """
SELECT r.id, r.status, r.created_at, o.id AS opportunity_id, o.title, f.name AS from_company, t.name AS to_company
FROM referrals r JOIN opportunities o ON o.id = r.opportunity_id JOIN operating_companies f ON f.id = r.from_company_id
JOIN operating_companies t ON t.id = r.to_company_id ORDER BY r.created_at DESC"""
Q["network_link_signal"] = """
INSERT INTO network_candidate_signals (candidate_id, signal_id)
SELECT n.id, s.id FROM network_candidates n, signals s WHERE n.id = CAST(:id AS uuid) AND s.id = CAST(:signal AS uuid)
ON CONFLICT DO NOTHING RETURNING candidate_id"""

# ---------------------------------------------------------------- directive wfc_0002: geography-filtered views
_GEO_OPP = """(CAST(:geo AS jsonb) IS NULL OR EXISTS (SELECT 1 FROM opportunity_geography g WHERE g.opportunity_id = o.id
     AND g.support IN ('supported','internal_record') AND g.role IN ('delivery','contract_territory','origin','destination')
     AND CAST(:geo AS jsonb) ? g.country_code::text))"""
_GEO_SIG = """(CAST(:geo AS jsonb) IS NULL OR EXISTS (SELECT 1 FROM signal_geography g WHERE g.signal_id = s.id AND g.support = 'supported'
     AND g.role IN ('delivery','contract_territory','origin','destination') AND CAST(:geo AS jsonb) ? g.country_code::text))"""
Q["briefing_pipeline_geo"] = f"""
SELECT o.module, o.commercial_stage, o.qualification_status, coalesce(o.tender_status, 'unknown') AS tender_status,
       coalesce(o.freight_scope, 'unclear') AS freight_scope, count(*) AS n
FROM opportunities o WHERE o.merged_into_id IS NULL AND {_GEO_OPP} GROUP BY 1, 2, 3, 4, 5 ORDER BY 1, 2, 3, 4, 5"""
Q["briefing_deadlines_geo"] = f"""
SELECT o.id, o.title, o.module, o.deadline_utc, o.deadline_source_tz, o.deadline_info, o.qualification_status, o.commercial_stage, o.tender_status, o.freight_scope
FROM opportunities o
WHERE o.deadline_latest_utc >= now() AND o.deadline_earliest_utc <= now() + make_interval(days => CAST(:days AS int)) AND o.merged_into_id IS NULL
  AND o.commercial_stage NOT IN ('won','lost','expired','deferred') AND coalesce(o.freight_scope, '') NOT IN ('passenger','not_freight') AND {_GEO_OPP}
ORDER BY o.deadline_latest_utc LIMIT 50"""
Q["briefing_signals_geo"] = f"""
SELECT s.id, s.module, s.classification, s.title, s.summary, s.gaps, s.created_at, s.freight_scope, (s.tender_state->>'status') AS tender_status,
       ARRAY(SELECT DISTINCT g.country_code::text FROM signal_geography g WHERE g.signal_id = s.id AND g.support = 'supported') AS countries
FROM signals s WHERE s.merged_into_id IS NULL AND {_GEO_SIG} ORDER BY s.created_at DESC LIMIT CAST(:limit AS int)"""
Q["review_counts"] = """
SELECT (SELECT count(*) FROM source_documents WHERE extraction_status IN ('not_connected','budget_refused','failed','partial')) AS documents,
       (SELECT count(*) FROM claims WHERE review_status = 'proposed') AS claims,
       (SELECT count(*) FROM extraction_rejections WHERE status = 'open') AS rejections,
       (SELECT count(*) FROM merge_candidates WHERE status = 'open') AS merges"""
Q["opportunity_list2"] = f"""
SELECT o.id, o.module, o.title, o.commercial_stage, o.qualification_status, o.deadline_utc, o.deadline_source_tz, o.deadline_info, o.tender_status,
       o.tender_status_basis, o.freight_scope, s.freight_scope_reason, (s.tender_state->>'published_at') AS evidence_published_at,
       (s.tender_state->>'status_verified_at') AS status_stated_at, (s.tender_state->>'status_asserted_at') AS status_first_stated_at,
       (s.tender_state->>'retrieved_at') AS last_retrieved_at,
       s.classification, oc.name AS operating_company, org.canonical_name AS organisation, t.code AS territory,
       sv.code AS service, p.full_name AS owner, o.updated_at,
       ARRAY(SELECT DISTINCT g.country_code::text FROM opportunity_geography g WHERE g.opportunity_id = o.id
             AND g.support IN ('supported','internal_record') AND g.role IN ('delivery','contract_territory','origin','destination')
             ORDER BY 1) AS countries,
       (SELECT json_object_agg(a.dimension, json_build_object('status', a.status, 'score', a.score)) FROM assessments a
         WHERE a.opportunity_id = o.id) AS priority,
       count(*) OVER () AS total
FROM opportunities o
LEFT JOIN signals s ON s.id = o.signal_id
LEFT JOIN operating_companies oc ON oc.id = o.operating_company_id
LEFT JOIN organisations org ON org.id = coalesce(o.airline_id, o.organisation_id)
LEFT JOIN territories t ON t.id = o.territory_id
LEFT JOIN services sv ON sv.id = o.service_id
LEFT JOIN people p ON p.id = o.owner_person_id
WHERE o.merged_into_id IS NULL
  AND (CAST(:module AS text) IS NULL OR o.module = CAST(:module AS text))
  AND (CAST(:stage AS text) IS NULL OR o.commercial_stage = CAST(:stage AS text))
  AND (CAST(:qual AS text) IS NULL OR o.qualification_status = CAST(:qual AS text))
  AND (CAST(:company AS uuid) IS NULL OR o.operating_company_id = CAST(:company AS uuid))
  AND (CAST(:q AS text) IS NULL OR o.title ILIKE '%' || CAST(:q AS text) || '%' OR org.canonical_name ILIKE '%' || CAST(:q AS text) || '%'
       OR s.tender_ref ILIKE '%' || CAST(:q AS text) || '%' OR o.id::text = CAST(:q AS text))
  AND {_GEO_OPP}
ORDER BY o.deadline_latest_utc NULLS LAST, o.updated_at DESC
LIMIT CAST(:limit AS int) OFFSET CAST(:offset AS int)"""
Q["opportunity_get2"] = """
SELECT o.*, ap.iata_code AS station_code, s.classification, s.gaps, s.title AS signal_title, s.tender_state, s.identity_basis,
       s.tender_ref, oc.name AS operating_company, org.canonical_name AS organisation, t.code AS territory, sv.code AS service,
       p.full_name AS owner
FROM opportunities o
LEFT JOIN airports ap ON ap.id = o.station_airport_id
LEFT JOIN signals s ON s.id = o.signal_id
LEFT JOIN operating_companies oc ON oc.id = o.operating_company_id
LEFT JOIN organisations org ON org.id = coalesce(o.airline_id, o.organisation_id)
LEFT JOIN territories t ON t.id = o.territory_id
LEFT JOIN services sv ON sv.id = o.service_id
LEFT JOIN people p ON p.id = o.owner_person_id
WHERE o.id = CAST(:id AS uuid)"""
Q["opportunity_geo"] = """
SELECT g.country_code::text AS country_code, c.name, g.role, g.support FROM opportunity_geography g JOIN countries c ON c.code = g.country_code
WHERE g.opportunity_id = CAST(:id AS uuid) ORDER BY g.role, c.name"""
Q["referrals_for"] = """
SELECT r.id, r.status, f.name AS from_company, t.name AS to_company, r.created_at FROM referrals r
JOIN operating_companies f ON f.id = r.from_company_id JOIN operating_companies t ON t.id = r.to_company_id
WHERE r.opportunity_id = CAST(:id AS uuid) ORDER BY r.created_at"""
Q["opportunity_competitors"] = """
SELECT o2.id, o2.title, o2.module FROM opportunities o JOIN opportunities o2 ON o2.competition_group_id = o.competition_group_id
WHERE o.id = CAST(:id AS uuid) AND o2.id <> o.id"""
Q["values_for_pipeline2"] = f"""
SELECT o.id::text AS opportunity_id, cv.currency, cv.airline_revenue, cv.wfc_remuneration, cv.incremental_costs,
       cv.guarantee_exposure, cv.basis, cv.assumptions, cv.value_kind, o.competition_group_id::text AS competition_group,
       o.module, oc.name AS operating_company, rf_from.name AS referred_from, (rf.to_company_id IS NOT NULL) AS referred
FROM opportunities o JOIN commercial_values cv ON cv.opportunity_id = o.id
-- Attribution: an accepted (or closed) referral moves the value to the RECEIVING company; the referring company no
-- longer counts it. Several accepted referrals: the latest receiver. One row per opportunity either way.
LEFT JOIN LATERAL (SELECT r.to_company_id, r.from_company_id FROM referrals r
                    WHERE r.opportunity_id = o.id AND r.status IN ('accepted','closed') ORDER BY r.created_at DESC, r.id LIMIT 1) rf ON true
LEFT JOIN operating_companies oc ON oc.id = coalesce(rf.to_company_id, o.operating_company_id)
LEFT JOIN operating_companies rf_from ON rf_from.id = rf.from_company_id
WHERE o.merged_into_id IS NULL
  -- potential pipeline = open opportunities only; won and realised values only for won opportunities
  AND CASE WHEN CAST(:kind AS text) = 'potential' THEN o.commercial_stage NOT IN ('won','lost','expired','deferred')
           ELSE o.commercial_stage = 'won' END
  AND (CAST(:company AS uuid) IS NULL OR coalesce(rf.to_company_id, o.operating_company_id) = CAST(:company AS uuid))
  AND (CAST(:module AS text) IS NULL OR o.module = CAST(:module AS text))
  AND {_GEO_OPP}"""
Q["opportunity_update_from_signal"] = """
UPDATE opportunities SET deadline_utc = CAST(:deadline AS timestamptz), deadline_source_tz = CAST(:tz AS text),
       deadline_info = CAST(:info AS jsonb), deadline_earliest_utc = CAST(:earliest AS timestamptz),
       deadline_latest_utc = CAST(:latest AS timestamptz),
       airline_id = coalesce(airline_id, CAST(:airline_id AS uuid)), organisation_id = coalesce(organisation_id, CAST(:organisation_id AS uuid)),
       territory_id = CAST(:territory_id AS uuid), service_id = coalesce(service_id, CAST(:service_id AS uuid))
WHERE id = CAST(:id AS uuid)"""
Q["signal_merge_info"] = """
SELECT s.id::text AS id, s.created_at, (SELECT o.id FROM opportunities o WHERE o.signal_id = s.id AND o.merged_into_id IS NULL LIMIT 1) AS opp
FROM signals s WHERE s.id = CAST(:id AS uuid)"""


# ---------------------------------------------------------------- 27 Oct 2026 (second instruction): freight relevance, geography conflicts, status basis (wfc_0007)
Q["document_title"] = "SELECT title FROM source_documents WHERE id = CAST(:id AS uuid)"
Q["document_set_geography_conflict"] = "UPDATE source_documents SET geography_conflict = CAST(:text AS text) WHERE id = CAST(:id AS uuid)"
# The live freight-scope readings of a signal's anchor claims (one per claim document).
Q["signal_scope_fields"] = """
SELECT cf.normalised, cf.reason, cf.support, c.claim_type FROM signal_claims sc JOIN claims c ON c.id = sc.claim_id
JOIN claim_fields cf ON cf.claim_id = c.id AND cf.superseded_at IS NULL AND cf.field = 'freight_scope'
JOIN claim_evidence ce ON ce.claim_id = c.id AND ce.source_document_id = cf.source_document_id AND ce.excluded_at IS NULL
WHERE sc.signal_id = CAST(:signal AS uuid) AND c.review_status NOT IN ('rejected', 'corrected')
  AND c.claim_type IN ('gssa_tender', 'service_tender', 'tcm_signal')"""
Q["signal_geo_conflicts"] = """
SELECT DISTINCT d.geography_conflict FROM signal_claims sc JOIN claims c ON c.id = sc.claim_id
JOIN claim_evidence ce ON ce.claim_id = c.id AND ce.excluded_at IS NULL JOIN source_documents d ON d.id = ce.source_document_id
WHERE sc.signal_id = CAST(:signal AS uuid) AND c.review_status NOT IN ('rejected', 'corrected') AND d.geography_conflict IS NOT NULL"""
# A supported scope country of a signal stays supported only while a LIVE, non-superseded field assessment supports it.
Q["signal_geo_recompute"] = """
UPDATE signal_geography g SET support = 'unverified'
WHERE g.signal_id = CAST(:signal AS uuid) AND g.support = 'supported' AND g.role IN ('delivery','contract_territory','origin','destination')
  AND NOT EXISTS (
    SELECT 1 FROM signal_claims sc JOIN claims c ON c.id = sc.claim_id
    JOIN claim_evidence ce ON ce.claim_id = c.id AND ce.excluded_at IS NULL
    JOIN claim_fields cf ON cf.claim_id = c.id AND cf.source_document_id = ce.source_document_id AND cf.superseded_at IS NULL AND cf.support = 'supported'
    LEFT JOIN airports ap ON ap.iata_code = cf.normalised
    WHERE sc.signal_id = g.signal_id AND c.review_status NOT IN ('rejected', 'corrected')
      AND cf.field = CASE g.role WHEN 'delivery' THEN 'country' ELSE g.role END
      AND (cf.normalised = g.country_code::text OR ap.country = g.country_code))"""
Q["signal_set_scope"] = "UPDATE signals SET freight_scope = CAST(:scope AS text), freight_scope_reason = CAST(:reason AS text) WHERE id = CAST(:id AS uuid)"
Q["opportunity_set_scope_basis"] = """
UPDATE opportunities SET freight_scope = CAST(:scope AS text), tender_status_basis = CAST(:basis AS text) WHERE id = CAST(:id AS uuid)"""
# Anchor claims whose freight relevance was never assessed (made under validation rules before v4).
Q["claims_without_scope"] = """
SELECT c.id::text AS claim_id, c.claim_type, ce.source_document_id::text AS document_id, ce.excerpt AS claim_quote, d.body_text AS document_text, d.title,
       (SELECT cf.normalised FROM claim_fields cf WHERE cf.claim_id = c.id AND cf.source_document_id = ce.source_document_id AND cf.field = 'service'
          AND cf.support = 'supported' AND cf.superseded_at IS NULL LIMIT 1) AS service,
       ARRAY(SELECT sc.signal_id::text FROM signal_claims sc WHERE sc.claim_id = c.id) AS signal_ids
FROM claims c JOIN claim_evidence ce ON ce.claim_id = c.id AND ce.excluded_at IS NULL JOIN source_documents d ON d.id = ce.source_document_id
WHERE c.claim_type IN ('gssa_tender', 'service_tender', 'tcm_signal', 'representation_change') AND c.review_status NOT IN ('rejected', 'corrected')
  AND NOT EXISTS (SELECT 1 FROM claim_fields cf WHERE cf.claim_id = c.id AND cf.source_document_id = ce.source_document_id
                  AND cf.field = 'freight_scope' AND cf.superseded_at IS NULL)
ORDER BY c.created_at"""
Q["tender_signals_live"] = """
SELECT s.id::text AS id FROM signals s WHERE s.merged_into_id IS NULL AND s.signal_key LIKE 'tender|%' ORDER BY s.created_at"""
# Stored country matches of past discovery runs, for re-check after a geography verdict changes.
Q["discovery_results_of_signal"] = """
SELECT r.run_id::text AS run_id, r.match, dr.search_id::text AS search_id, dr.source_id::text AS source_id
FROM discovery_results r JOIN discovery_runs dr ON dr.id = r.run_id WHERE r.signal_id = CAST(:signal AS uuid)"""
Q["result_set_match"] = "UPDATE discovery_results SET match = CAST(:match AS jsonb) WHERE run_id = CAST(:run AS uuid) AND signal_id = CAST(:signal AS uuid)"
Q["opportunities_of_signal"] = """
SELECT o.id::text AS id, o.freight_scope, o.tender_status, o.tender_status_basis FROM opportunities o WHERE o.signal_id = CAST(:signal AS uuid) AND o.merged_into_id IS NULL"""
# ---------------------------------------------------------------- wfc_0008 (third instruction of 27 Oct 2026): v5 re-check
Q["scope_fields_to_recheck"] = """
SELECT cf.id::text AS field_id, cf.claim_id::text AS claim_id, cf.source_document_id::text AS document_id, cf.normalised, cf.support, cf.reason,
       cf.quote, cf.validation_version, cf.assessed_by, c.claim_type, c.review_status, d.body_text AS document_text, d.title,
       (SELECT ce.excerpt FROM claim_evidence ce WHERE ce.claim_id = c.id AND ce.source_document_id = cf.source_document_id LIMIT 1) AS claim_quote,
       (SELECT s.normalised FROM claim_fields s WHERE s.claim_id = c.id AND s.source_document_id = cf.source_document_id AND s.field = 'service'
          AND s.support = 'supported' AND s.superseded_at IS NULL LIMIT 1) AS service,
       (SELECT s.quote FROM claim_fields s WHERE s.claim_id = c.id AND s.source_document_id = cf.source_document_id AND s.field = 'service'
          AND s.support = 'supported' AND s.superseded_at IS NULL LIMIT 1) AS service_quote,
       ARRAY(SELECT sc.signal_id::text FROM signal_claims sc WHERE sc.claim_id = c.id) AS signal_ids
FROM claim_fields cf JOIN claims c ON c.id = cf.claim_id JOIN source_documents d ON d.id = cf.source_document_id
WHERE cf.field = 'freight_scope' AND cf.superseded_at IS NULL AND cf.validation_version < CAST(:version AS int)
  AND c.review_status NOT IN ('rejected', 'corrected') AND cf.assessed_by <> 'human'
ORDER BY cf.created_at"""
Q["route_signals_live"] = """
SELECT s.id::text AS id, s.module, s.signal_key, s.related_modules,
       ARRAY(SELECT c.claim_type || chr(31) || coalesce(ce.excerpt, '') || chr(31) || coalesce(d.body_text, '')
             FROM signal_claims sc JOIN claims c ON c.id = sc.claim_id JOIN claim_evidence ce ON ce.claim_id = c.id AND ce.excluded_at IS NULL
             JOIN source_documents d ON d.id = ce.source_document_id
             WHERE sc.signal_id = s.id AND c.review_status NOT IN ('rejected','corrected')
               AND c.claim_type IN ('route_launch','route_suspension','representation_change')) AS evidence
FROM signals s WHERE s.merged_into_id IS NULL AND s.signal_key NOT LIKE 'tender|%'
  AND EXISTS (SELECT 1 FROM signal_claims sc JOIN claims c ON c.id = sc.claim_id WHERE sc.signal_id = s.id
              AND c.claim_type IN ('route_launch','route_suspension','representation_change'))"""
Q["signal_set_module"] = """
UPDATE signals SET module = CAST(:module AS text), related_modules = ARRAY(SELECT jsonb_array_elements_text(CAST(:related AS jsonb)))
WHERE id = CAST(:id AS uuid) AND NOT EXISTS (SELECT 1 FROM signals o WHERE o.module = CAST(:module AS text) AND o.signal_key = signals.signal_key
                                             AND o.id <> signals.id)
RETURNING id"""

# ---------------------------------------------------------------- wfc_0009 (fourth instruction of 27 Oct 2026): v6 re-check
Q["documents_publication_to_recheck"] = """
SELECT id::text AS id, published_at, published_at_source, publication_flag, publication_note, retrieved_at, body_text, excerpt
FROM source_documents WHERE publication_version < CAST(:version AS int) ORDER BY id"""
Q["document_set_publication"] = """
UPDATE source_documents SET published_at = CAST(:published AS timestamptz), published_at_source = CAST(:source AS text),
    publication_flag = CAST(:flag AS text), publication_note = CAST(:note AS text), publication_version = CAST(:version AS int)
WHERE id = CAST(:id AS uuid)"""
Q["document_set_publication_version"] = """
UPDATE source_documents SET publication_version = CAST(:version AS int) WHERE id = CAST(:id AS uuid)"""

# ---------------------------------------------------------------- wfc_0010 (fifth instruction of 27 Oct 2026)
Q["signal_set_classification"] = """
UPDATE signals SET classification = CAST(:classification AS text) WHERE id = CAST(:id AS uuid)"""
Q["opportunity_review_flags"] = "SELECT review_flags FROM opportunities WHERE id = CAST(:id AS uuid)"
Q["signal_classification"] = "SELECT classification FROM signals WHERE id = CAST(:id AS uuid)"
Q["signal_has_document"] = """
SELECT EXISTS (SELECT 1 FROM signals s JOIN signal_claims sc ON sc.signal_id = s.id JOIN claim_evidence ce ON ce.claim_id = sc.claim_id
               WHERE s.signal_key = CAST(:key AS text) AND s.merged_into_id IS NULL AND ce.source_document_id = CAST(:doc AS uuid))"""
Q["station_country"] = "SELECT country::text FROM stations WHERE code = CAST(:code AS text)"
Q["forwarder_by_name"] = """
SELECT id::text FROM organisations WHERE kind = 'forwarder' AND merged_into_id IS NULL AND canonical_name = CAST(:name AS text) LIMIT 1"""


# ---------------------------------------------------------------- wfc_0011 (28 Oct 2026: discovery + relationship intelligence)
# Every record the Overview and Opportunities screens list: opportunities (tender or commercial) and the signals that are not
# tracked as an opportunity (market signals, historical intelligence; excluded records only on request). List parameters are
# JSON arrays (NULL = no filter).
_RECORDS = """
WITH rec AS (
  SELECT 'opportunity'::text AS kind, o.id, o.record_type, o.module, o.title,
         org.canonical_name AS organisation, org.id AS organisation_id,
         ARRAY(SELECT DISTINCT g.country_code::text FROM opportunity_geography g WHERE g.opportunity_id = o.id
               AND g.support IN ('supported','internal_record') ORDER BY 1) AS countries,
         coalesce(CAST(s.tender_state->>'published_at' AS timestamptz), s.first_published_at) AS source_date,
         o.deadline_utc, coalesce(o.deadline_utc, o.deadline_latest_utc) AS deadline_at, o.deadline_source_tz, o.deadline_info,
         o.tender_status, o.progress, o.closed_reason, o.saved_at, o.owner_label,
         o.next_action, o.next_action_due, s.classification, coalesce(o.freight_scope, s.freight_scope) AS freight_scope,
         o.qualification_status, o.created_at, o.updated_at,
         coalesce(cov.level, 'none') AS coverage, coalesce(cov.people, 0) AS people, coalesce(cov.candidates, 0) AS candidates,
         coalesce(cov.confirmed, 0) AS confirmed, coalesce(cov.with_relationship, 0) AS with_relationship,
         coalesce(cov.with_introduction, 0) AS with_introduction, cov.last_researched_at,
         (SELECT count(*) FROM claims c JOIN signal_claims sc ON sc.claim_id = c.id
           WHERE sc.signal_id = s.id AND c.review_status = 'confirmed') AS reviewed_claims,
         s.tender_ref, (s.tender_state->>'status_conflict') AS status_conflict
    FROM opportunities o
    LEFT JOIN signals s ON s.id = coalesce(o.signal_id, o.tracked_from_signal_id)
    LEFT JOIN organisations org ON org.id = coalesce(o.airline_id, o.organisation_id)
    LEFT JOIN opportunity_relationship_coverage cov ON cov.opportunity_id = o.id
   WHERE o.merged_into_id IS NULL
  UNION ALL
  SELECT 'signal', s.id,
         CASE s.classification WHEN 'historical_record' THEN 'historical' WHEN 'excluded' THEN 'excluded' ELSE 'market_signal' END,
         s.module, s.title, so.canonical_name, so.id,
         ARRAY(SELECT DISTINCT g.country_code::text FROM signal_geography g WHERE g.signal_id = s.id AND g.support = 'supported' ORDER BY 1),
         s.first_published_at, CAST(s.tender_state->>'deadline_utc' AS timestamptz), CAST(s.tender_state->>'deadline_utc' AS timestamptz),
         s.tender_state->>'deadline_source_tz',
         s.tender_state->'deadline', s.tender_state->>'status', NULL, NULL, NULL, NULL, NULL, NULL, s.classification, s.freight_scope, NULL,
         s.created_at, s.updated_at, 'none', 0, 0, 0, 0, 0, NULL,
         (SELECT count(*) FROM claims c JOIN signal_claims sc ON sc.claim_id = c.id
           WHERE sc.signal_id = s.id AND c.review_status = 'confirmed'),
         s.tender_ref, (s.tender_state->>'status_conflict')
    FROM signals s
    LEFT JOIN LATERAL (SELECT o2.id, o2.canonical_name FROM signal_claims sc JOIN claims c ON c.id = sc.claim_id
                         JOIN organisations o2 ON o2.id = c.subject_organisation_id WHERE sc.signal_id = s.id
                        ORDER BY c.created_at LIMIT 1) so ON true
   WHERE s.merged_into_id IS NULL
     AND NOT EXISTS (SELECT 1 FROM opportunities o WHERE o.merged_into_id IS NULL AND (o.signal_id = s.id OR o.tracked_from_signal_id = s.id))
)
SELECT r.*, count(*) OVER () AS total FROM rec r
 WHERE (CAST(:types AS jsonb) IS NULL OR CAST(:types AS jsonb) ? r.record_type)
   AND (CAST(:types AS jsonb) IS NOT NULL OR r.record_type <> 'excluded')
   AND (CAST(:modules AS jsonb) IS NULL OR CAST(:modules AS jsonb) ? r.module)
   AND (CAST(:geo AS jsonb) IS NULL OR CAST(:geo AS jsonb) ?| r.countries)
   AND (CAST(:tender AS jsonb) IS NULL OR CAST(:tender AS jsonb) ? coalesce(r.tender_status, 'none'))
   AND (CAST(:progress AS jsonb) IS NULL OR CAST(:progress AS jsonb) ? coalesce(r.progress, 'untracked'))
   AND (CAST(:coverage AS jsonb) IS NULL OR CAST(:coverage AS jsonb) ? r.coverage)
   AND (CAST(:org AS text) IS NULL OR r.organisation ILIKE '%' || CAST(:org AS text) || '%' OR r.organisation_id::text = CAST(:org AS text))
   AND (CAST(:q AS text) IS NULL OR r.title ILIKE '%' || CAST(:q AS text) || '%' OR r.organisation ILIKE '%' || CAST(:q AS text) || '%'
        OR r.tender_ref ILIKE '%' || CAST(:q AS text) || '%')
   AND (CAST(:deadline_days AS int) IS NULL OR (r.deadline_at >= now() AND r.deadline_at <= now() + make_interval(days => CAST(:deadline_days AS int))))
   AND (CAST(:saved AS boolean) IS NULL OR (r.saved_at IS NOT NULL) = CAST(:saved AS boolean))
   AND (CAST(:since AS timestamptz) IS NULL OR r.created_at >= CAST(:since AS timestamptz))
   AND (CAST(:id AS uuid) IS NULL OR r.id = CAST(:id AS uuid))
"""
Q["records_list"] = _RECORDS + """
 ORDER BY CASE WHEN CAST(:sort AS text) = 'deadline' THEN r.deadline_at END ASC NULLS LAST,
          CASE WHEN CAST(:sort AS text) = 'source_date' THEN coalesce(r.source_date, r.created_at) END DESC NULLS LAST,
          r.created_at DESC, r.id
 LIMIT CAST(:limit AS int) OFFSET CAST(:offset AS int)"""

Q["org_set_website"] = "UPDATE organisations SET website = CAST(:website AS text), updated_at = now() WHERE id = CAST(:id AS uuid)"
Q["record_signal_get"] = """
SELECT s.id, s.module, s.classification, s.title, s.summary, s.gaps, s.tender_state, s.tender_ref, s.freight_scope, s.freight_scope_reason,
       s.first_published_at AS first_published, s.created_at, s.updated_at, s.identity_basis,
       CASE s.classification WHEN 'historical_record' THEN 'historical' WHEN 'excluded' THEN 'excluded' ELSE 'market_signal' END AS record_type,
       (SELECT o.id FROM opportunities o WHERE o.merged_into_id IS NULL AND (o.signal_id = s.id OR o.tracked_from_signal_id = s.id) LIMIT 1)
           AS opportunity_id
  FROM signals s WHERE s.id = CAST(:id AS uuid)"""
Q["record_signal_geo"] = """
SELECT g.country_code::text AS country_code, c.name, g.role, g.support FROM signal_geography g JOIN countries c ON c.code = g.country_code
 WHERE g.signal_id = CAST(:id AS uuid) ORDER BY g.role, c.name"""

# ---- involved organisations of an opportunity (issuer, plus organisations its evidence is about, plus people's organisations)
Q["opportunity_organisations"] = """
SELECT * FROM (
SELECT DISTINCT ON (x.id) x.id, x.name, x.kind, x.country, x.website, x.newsroom_url, x.leadership_url, x.involvement, x.ord FROM (
  SELECT org.id, org.canonical_name AS name, org.kind, org.country::text AS country, org.website, org.newsroom_url, org.leadership_url,
         'issuer' AS involvement, 0 AS ord
    FROM opportunities o JOIN organisations org ON org.id = coalesce(o.airline_id, o.organisation_id) WHERE o.id = CAST(:id AS uuid)
  UNION ALL
  SELECT org.id, org.canonical_name, org.kind, org.country::text, org.website, org.newsroom_url, org.leadership_url, 'named in the evidence', 1
    FROM opportunities o JOIN signal_claims sc ON sc.signal_id = coalesce(o.signal_id, o.tracked_from_signal_id)
    JOIN claims c ON c.id = sc.claim_id JOIN organisations org ON org.id = c.subject_organisation_id WHERE o.id = CAST(:id AS uuid)
  UNION ALL
  SELECT org.id, org.canonical_name, org.kind, org.country::text, org.website, org.newsroom_url, org.leadership_url,
         CASE pr.affiliation WHEN 'partner' THEN 'partner organisation of a linked person'
                             WHEN 'customer' THEN 'customer organisation of a linked person'
                             ELSE 'organisation of a linked person' END, 2
    FROM opportunity_people op JOIN people p ON p.id = op.person_id AND p.merged_into_id IS NULL
    JOIN person_roles pr ON pr.person_id = p.id AND pr.role_status = 'current' AND pr.organisation_id IS NOT NULL
    JOIN organisations org ON org.id = pr.organisation_id
   WHERE op.opportunity_id = CAST(:id AS uuid) AND op.status <> 'not_relevant'
  UNION ALL
  SELECT org.id, org.canonical_name, org.kind, org.country::text, org.website, org.newsroom_url, org.leadership_url,
         'organisation of a linked person', 3
    FROM opportunity_people op JOIN people p ON p.id = op.person_id AND p.merged_into_id IS NULL JOIN organisations org ON org.id = p.organisation_id
   WHERE op.opportunity_id = CAST(:id AS uuid) AND op.status <> 'not_relevant'
) x ORDER BY x.id, x.ord) y ORDER BY y.ord, y.name"""
# Source documents behind an opportunity, with retained text (only stored when the source permits retention).
Q["opportunity_documents"] = """
SELECT DISTINCT d.id, d.title, d.canonical_url, d.published_at, d.retrieved_at, d.body_text
  FROM opportunities o JOIN signal_claims sc ON sc.signal_id = coalesce(o.signal_id, o.tracked_from_signal_id)
  JOIN claim_evidence ce ON ce.claim_id = sc.claim_id JOIN source_documents d ON d.id = ce.source_document_id
 WHERE o.id = CAST(:id AS uuid) AND ce.excluded_at IS NULL"""

# ---- people
_PERSON_COLS = """p.id, p.full_name, p.role_title, p.organisation_id, coalesce(org.canonical_name, p.organisation_label) AS organisation,
       org.country::text AS organisation_country, p.remit_text, p.remit_countries, p.remit_basis, p.identity_confirmed_at, p.identity_basis,
       p.last_verified_at, p.linkedin_profile_url, p.linkedin_confirmed_at, p.relationship_owner, p.notes, p.next_action, p.next_action_due,
       p.origin, p.email, p.created_at, p.updated_at, ps.state, ps.current_relationships, ps.available_routes, ps.possible_routes,
       p.stakeholder_type, p.decision_authority, p.posture, p.judgement_basis, p.judgement_by_label, p.judgement_at, p.key_interests,
       p.strategic_account, p.capability_area, org.kind AS organisation_kind,
       (SELECT max(e.occurred_at) FROM engagements e WHERE e.person_id = p.id) AS last_engagement"""
Q["rel_person_get"] = f"""
SELECT {_PERSON_COLS.replace("ps.state", "coalesce(ps.state, CASE WHEN p.merged_into_id IS NOT NULL THEN 'merged' END) AS state")},
       p.merged_into_id, (SELECT m.full_name FROM people m WHERE m.id = p.merged_into_id) AS merged_into_name
  FROM people p LEFT JOIN person_state ps ON ps.person_id = p.id LEFT JOIN organisations org ON org.id = p.organisation_id
 WHERE p.id = CAST(:id AS uuid) AND NOT p.is_internal"""
Q["rel_people_list"] = f"""
SELECT {_PERSON_COLS},
       (SELECT count(*) FROM opportunity_people op WHERE op.person_id = p.id AND op.status <> 'not_relevant') AS opportunities,
       count(*) OVER () AS total
  FROM people p JOIN person_state ps ON ps.person_id = p.id LEFT JOIN organisations org ON org.id = p.organisation_id
 WHERE (CAST(:states AS jsonb) IS NULL OR CAST(:states AS jsonb) ? ps.state)
   AND (CAST(:q AS text) IS NULL OR p.full_name ILIKE '%' || CAST(:q AS text) || '%' OR p.role_title ILIKE '%' || CAST(:q AS text) || '%'
        OR coalesce(org.canonical_name, p.organisation_label) ILIKE '%' || CAST(:q AS text) || '%')
   AND (CAST(:org AS uuid) IS NULL OR p.organisation_id = CAST(:org AS uuid))
   AND (CAST(:since AS timestamptz) IS NULL OR p.created_at >= CAST(:since AS timestamptz))
   AND (CAST(:has_action AS boolean) IS NULL OR (p.next_action IS NOT NULL) = CAST(:has_action AS boolean))
   AND (CAST(:country AS text) IS NULL OR org.country::text = CAST(:country AS text) OR CAST(:country AS text) = ANY(coalesce(p.remit_countries::text[], ARRAY[]::text[])))
   AND (CAST(:module AS text) IS NULL OR p.capability_area = CAST(:module AS text)
        OR EXISTS (SELECT 1 FROM opportunity_people op JOIN opportunities oo ON oo.id = op.opportunity_id
                    WHERE op.person_id = p.id AND op.status <> 'not_relevant' AND oo.module = CAST(:module AS text)))
   AND (CAST(:stakeholder_type AS text) IS NULL OR p.stakeholder_type = CAST(:stakeholder_type AS text))
 ORDER BY CASE ps.state WHEN 'existing_relationship' THEN 0 WHEN 'introduction_available' THEN 1 WHEN 'identity_confirmed' THEN 2 ELSE 3 END,
          p.next_action_due NULLS LAST, p.updated_at DESC, p.id
 LIMIT CAST(:limit AS int) OFFSET CAST(:offset AS int)"""
Q["rel_person_find"] = """
SELECT p.id FROM people p
 WHERE NOT p.is_internal AND lower(regexp_replace(p.full_name, '\\s+', ' ', 'g')) = lower(CAST(:name AS text))
   AND ((CAST(:org AS uuid) IS NOT NULL AND p.organisation_id = CAST(:org AS uuid))
        OR (CAST(:org AS uuid) IS NULL AND p.organisation_id IS NULL
            AND coalesce(lower(p.organisation_label), '') = coalesce(lower(CAST(:org_label AS text)), '')))
 ORDER BY p.created_at LIMIT 1"""
Q["rel_person_find_on_opp"] = """
SELECT p.id FROM opportunity_people op JOIN people p ON p.id = op.person_id
 WHERE op.opportunity_id = CAST(:opp AS uuid) AND lower(regexp_replace(p.full_name, '\\s+', ' ', 'g')) = lower(CAST(:name AS text))
   AND (p.organisation_id IS NULL OR CAST(:org AS uuid) IS NULL OR p.organisation_id = CAST(:org AS uuid))
 ORDER BY p.created_at LIMIT 1"""
Q["rel_person_insert"] = """
INSERT INTO people (full_name, role_title, organisation_id, organisation_label, origin, remit_text, remit_countries, notes)
VALUES (CAST(:name AS text), CAST(:role AS text), CAST(:org AS uuid), CAST(:org_label AS text), CAST(:origin AS text),
        CAST(:remit AS text),
        CASE WHEN CAST(:remit_countries AS jsonb) IS NULL THEN NULL
             ELSE ARRAY(SELECT jsonb_array_elements_text(CAST(:remit_countries AS jsonb)))::char(2)[] END, CAST(:notes AS text))
RETURNING id"""
Q["rel_person_update"] = """
UPDATE people SET role_title = CAST(:role AS text), organisation_id = CAST(:org AS uuid), organisation_label = CAST(:org_label AS text),
       remit_text = CAST(:remit AS text), remit_basis = CAST(:remit_basis AS text), relationship_owner = CAST(:owner AS text),
       notes = CAST(:notes AS text), next_action = CAST(:next_action AS text), next_action_due = CAST(:next_action_due AS date),
       updated_at = now()
 WHERE id = CAST(:id AS uuid) AND NOT is_internal"""
Q["rel_person_role_if_empty"] = """
UPDATE people SET role_title = CAST(:role AS text), updated_at = now()
 WHERE id = CAST(:id AS uuid) AND role_title IS NULL AND CAST(:role AS text) IS NOT NULL"""
Q["rel_person_confirm"] = """
UPDATE people SET identity_confirmed_at = now(), identity_basis = CAST(:basis AS text), last_verified_at = now(), updated_at = now()
 WHERE id = CAST(:id AS uuid) AND NOT is_internal"""
Q["rel_person_verified"] = "UPDATE people SET last_verified_at = now(), updated_at = now() WHERE id = CAST(:id AS uuid)"
Q["rel_person_linkedin"] = """
UPDATE people SET linkedin_profile_url = CAST(:url AS text), linkedin_confirmed_at = CASE WHEN CAST(:url AS text) IS NULL THEN NULL ELSE now() END,
       updated_at = now()
 WHERE id = CAST(:id AS uuid) AND NOT is_internal"""
Q["rel_evidence_add"] = """
INSERT INTO person_evidence (person_id, supports, source_kind, document_id, url, quote, note, session_ref)
SELECT CAST(:person AS uuid), CAST(:supports AS text), CAST(:kind AS text), CAST(:doc AS uuid), CAST(:url AS text), CAST(:quote AS text),
       CAST(:note AS text), CAST(:session_ref AS text)
 WHERE NOT EXISTS (SELECT 1 FROM person_evidence e WHERE e.person_id = CAST(:person AS uuid) AND e.supports = CAST(:supports AS text)
                     AND e.document_id IS NOT DISTINCT FROM CAST(:doc AS uuid) AND e.url IS NOT DISTINCT FROM CAST(:url AS text)
                     AND e.quote IS NOT DISTINCT FROM CAST(:quote AS text))"""
Q["rel_evidence_for"] = """
SELECT e.id, e.supports, e.source_kind, e.document_id, coalesce(d.title, rd.title) AS document_title,
       coalesce(e.url, d.canonical_url, rd.url) AS url, e.quote, e.note, e.observed_at, d.published_at, e.research_document_id,
       rd.origin AS research_origin
  FROM person_evidence e LEFT JOIN source_documents d ON d.id = e.document_id
  LEFT JOIN research_documents rd ON rd.id = e.research_document_id
 WHERE e.person_id = CAST(:id AS uuid) ORDER BY e.observed_at DESC"""
Q["rel_link_upsert"] = """
INSERT INTO opportunity_people (opportunity_id, person_id, role_on_opportunity, relevance_basis, status)
VALUES (CAST(:opp AS uuid), CAST(:person AS uuid), CAST(:role AS text), CAST(:basis AS text), CAST(:status AS text))
ON CONFLICT (opportunity_id, person_id) DO UPDATE
   SET role_on_opportunity = CASE WHEN opportunity_people.role_on_opportunity IN ('unknown','named_in_source')
                                  THEN EXCLUDED.role_on_opportunity ELSE opportunity_people.role_on_opportunity END
RETURNING (xmax = 0) AS inserted"""
Q["rel_link_set"] = """
UPDATE opportunity_people SET role_on_opportunity = coalesce(CAST(:role AS text), role_on_opportunity),
       status = coalesce(CAST(:status AS text), status),
       relevance_basis = coalesce(CAST(:basis AS text), relevance_basis)
 WHERE opportunity_id = CAST(:opp AS uuid) AND person_id = CAST(:person AS uuid)"""
Q["rel_opportunity_people"] = f"""
SELECT {_PERSON_COLS}, op.role_on_opportunity, op.relevance_basis, op.status AS link_status, op.added_at
  FROM opportunity_people op JOIN people p ON p.id = op.person_id JOIN person_state ps ON ps.person_id = p.id
  LEFT JOIN organisations org ON org.id = p.organisation_id
 WHERE op.opportunity_id = CAST(:id AS uuid)
 ORDER BY op.status = 'not_relevant', CASE ps.state WHEN 'existing_relationship' THEN 0 WHEN 'introduction_available' THEN 1
          WHEN 'identity_confirmed' THEN 2 ELSE 3 END, op.added_at"""
Q["rel_org_people_not_linked"] = f"""
SELECT {_PERSON_COLS}
  FROM opportunities o JOIN people p ON p.organisation_id = coalesce(o.airline_id, o.organisation_id) AND NOT p.is_internal
  JOIN person_state ps ON ps.person_id = p.id LEFT JOIN organisations org ON org.id = p.organisation_id
 WHERE o.id = CAST(:id AS uuid)
   AND NOT EXISTS (SELECT 1 FROM opportunity_people op WHERE op.opportunity_id = o.id AND op.person_id = p.id)"""
Q["rel_person_opportunities"] = """
SELECT o.id, o.title, o.module, o.record_type, o.progress, o.tender_status, o.deadline_utc, op.role_on_opportunity, op.relevance_basis,
       op.status AS link_status
  FROM opportunity_people op JOIN opportunities o ON o.id = op.opportunity_id
 WHERE op.person_id = CAST(:id AS uuid) ORDER BY o.deadline_utc NULLS LAST, o.updated_at DESC"""
Q["rel_relationship_add"] = """
INSERT INTO person_relationships (person_id, holder_label, nature, basis, session_ref)
VALUES (CAST(:person AS uuid), CAST(:holder AS text), CAST(:nature AS text), CAST(:basis AS text), CAST(:session_ref AS text)) RETURNING id"""
Q["rel_person_owner_if_empty"] = """
UPDATE people SET relationship_owner = CAST(:owner AS text), updated_at = now()
 WHERE id = CAST(:id AS uuid) AND (relationship_owner IS NULL OR trim(relationship_owner) = '')"""
Q["rel_relationship_status"] = """
UPDATE person_relationships SET status = CAST(:status AS text) WHERE id = CAST(:id AS uuid) RETURNING person_id"""
Q["rel_relationships_for"] = """
SELECT id, holder_label, nature, basis, status, recorded_at FROM person_relationships WHERE person_id = CAST(:id AS uuid)
 ORDER BY status, recorded_at DESC"""
Q["rel_route_add"] = """
INSERT INTO introduction_routes (target_person_id, opportunity_id, introducer_person_id, introducer_label, wfc_holder_label,
                                 connection_basis, evidence_url, notes, session_ref)
VALUES (CAST(:target AS uuid), CAST(:opp AS uuid), CAST(:introducer AS uuid), CAST(:introducer_label AS text), CAST(:holder AS text),
        CAST(:basis AS text), CAST(:url AS text), CAST(:notes AS text), CAST(:session_ref AS text)) RETURNING id"""
Q["rel_route_get"] = "SELECT * FROM introduction_routes WHERE id = CAST(:id AS uuid)"
Q["rel_route_update"] = """
UPDATE introduction_routes SET status = CAST(:status AS text), willingness_confirmed = CAST(:willing AS boolean),
       willingness_basis = CAST(:willing_basis AS text), notes = coalesce(CAST(:notes AS text), notes), updated_at = now()
 WHERE id = CAST(:id AS uuid)"""
Q["rel_routes_for"] = """
SELECT i.*, coalesce(ip.full_name, i.introducer_label) AS introducer, o.title AS opportunity_title
  FROM introduction_routes i LEFT JOIN people ip ON ip.id = i.introducer_person_id LEFT JOIN opportunities o ON o.id = i.opportunity_id
 WHERE i.target_person_id = CAST(:id AS uuid) ORDER BY i.status = 'declined', i.updated_at DESC"""
Q["rel_engagement_add"] = """
INSERT INTO engagements (organisation_id, person_id, opportunity_id, occurred_at, kind, summary, owner_label, outcome, next_step, direction,
                         session_ref)
SELECT p.organisation_id, p.id, CAST(:opp AS uuid), CAST(:occurred_at AS timestamptz), CAST(:kind AS text), CAST(:summary AS text),
       CAST(:owner AS text), CAST(:outcome AS text), CAST(:next_step AS text), coalesce(CAST(:direction AS text), 'outbound'), CAST(:session_ref AS text)
  FROM people p WHERE p.id = CAST(:person AS uuid) RETURNING id"""
Q["rel_engagements_for"] = """
SELECT e.id, e.occurred_at, e.kind, e.summary, e.owner_label, e.outcome, e.next_step, e.direction, e.opportunity_id, o.title AS opportunity_title
  FROM engagements e LEFT JOIN opportunities o ON o.id = e.opportunity_id
 WHERE e.person_id = CAST(:id AS uuid) ORDER BY e.occurred_at DESC"""
Q["rel_engagements_for_opportunity"] = """
SELECT e.id, e.occurred_at, e.kind, e.summary, e.owner_label, e.outcome, e.next_step, p.full_name AS person, p.id AS person_id
  FROM engagements e LEFT JOIN people p ON p.id = e.person_id
 WHERE e.opportunity_id = CAST(:id AS uuid) ORDER BY e.occurred_at DESC"""

# ---- research runs
Q["rel_research_insert"] = """
INSERT INTO relationship_research_runs (opportunity_id, methods, unavailable, organisations, target_roles, candidates_found, gaps, cost_usd,
                                        finished_at, session_ref)
VALUES (CAST(:opp AS uuid), ARRAY(SELECT jsonb_array_elements_text(CAST(:methods AS jsonb))), CAST(:unavailable AS jsonb), CAST(:orgs AS jsonb),
        CAST(:roles AS jsonb), CAST(:found AS int), CAST(:gaps AS jsonb), CAST(:cost AS numeric), now(), CAST(:session_ref AS text))
RETURNING id"""
Q["rel_research_latest"] = """
SELECT * FROM relationship_research_runs WHERE opportunity_id = CAST(:id AS uuid) ORDER BY started_at DESC LIMIT 1"""

# ---- light workspace
Q["ws_progress_set"] = """
UPDATE opportunities SET progress = CAST(:to AS text), closed_reason = CASE WHEN CAST(:to AS text) = 'closed' THEN CAST(:closed_reason AS text) END,
       updated_at = now()
 WHERE id = CAST(:id AS uuid) AND merged_into_id IS NULL RETURNING id"""
Q["ws_saved_set"] = """
UPDATE opportunities SET saved_at = CASE WHEN CAST(:saved AS boolean) THEN coalesce(saved_at, now()) END, updated_at = now()
 WHERE id = CAST(:id AS uuid) RETURNING id"""
Q["ws_owner_set"] = "UPDATE opportunities SET owner_label = CAST(:owner AS text), updated_at = now() WHERE id = CAST(:id AS uuid) RETURNING id"
Q["ws_next_action_set"] = """
UPDATE opportunities SET next_action = CAST(:action AS text), next_action_due = CAST(:due AS date), updated_at = now()
 WHERE id = CAST(:id AS uuid) RETURNING id"""
Q["ws_note_add"] = """
INSERT INTO opportunity_notes (opportunity_id, body, author_label, session_ref)
VALUES (CAST(:id AS uuid), CAST(:body AS text), CAST(:author AS text), CAST(:session_ref AS text)) RETURNING id"""
Q["ws_notes"] = "SELECT id, body, author_label, created_at FROM opportunity_notes WHERE opportunity_id = CAST(:id AS uuid) ORDER BY created_at DESC"
Q["ws_track_signal"] = """
INSERT INTO opportunities (module, dedup_key, title, organisation_id, record_type, tracked_from_signal_id, progress)
SELECT s.module, 'tracked:' || s.id::text, s.title,
       (SELECT c.subject_organisation_id FROM signal_claims sc JOIN claims c ON c.id = sc.claim_id
         WHERE sc.signal_id = s.id AND c.subject_organisation_id IS NOT NULL ORDER BY c.created_at LIMIT 1),
       'commercial', s.id, 'new'
  FROM signals s WHERE s.id = CAST(:signal AS uuid)
ON CONFLICT (module, dedup_key) DO UPDATE SET updated_at = now()
RETURNING id"""
Q["ws_track_geo"] = """
INSERT INTO opportunity_geography (opportunity_id, country_code, role, support)
SELECT CAST(:opp AS uuid), g.country_code, g.role, 'supported' FROM signal_geography g
 WHERE g.signal_id = CAST(:signal AS uuid) AND g.support = 'supported'
ON CONFLICT DO NOTHING"""

# ---- overview helpers
Q["overview_people_recent"] = f"""
SELECT {_PERSON_COLS},
       (SELECT json_agg(json_build_object('id', o.id, 'title', o.title)) FROM opportunity_people op JOIN opportunities o ON o.id = op.opportunity_id
         WHERE op.person_id = p.id AND op.status <> 'not_relevant') AS linked
  FROM people p JOIN person_state ps ON ps.person_id = p.id LEFT JOIN organisations org ON org.id = p.organisation_id
 WHERE EXISTS (SELECT 1 FROM opportunity_people op WHERE op.person_id = p.id AND op.status <> 'not_relevant')
 ORDER BY greatest(p.updated_at, p.created_at) DESC LIMIT CAST(:limit AS int)"""
Q["overview_changes"] = """
SELECT h.changed_at, h.field, h.from_value, h.to_value, h.reason, o.id AS opportunity_id, o.title
  FROM opportunity_status_history h JOIN opportunities o ON o.id = h.opportunity_id
 WHERE h.field IN ('tender_status','deadline','progress','merge','record_type')
 ORDER BY h.changed_at DESC LIMIT CAST(:limit AS int)"""
Q["overview_saved_searches"] = """
SELECT ss.id, ss.name, ss.geo_mode, ss.countries::text[] AS countries, ss.regions, ss.modules, ss.keywords, ss.organisation,
       (SELECT sc.interval_minutes FROM schedules sc WHERE sc.scope_search_id = ss.id AND sc.enabled LIMIT 1) AS schedule_minutes,
       (SELECT max(r.finished_at) FROM discovery_runs r WHERE r.search_id = ss.id) AS last_run_at,
       (SELECT r.status FROM discovery_runs r WHERE r.search_id = ss.id ORDER BY r.created_at DESC LIMIT 1) AS last_status,
       (SELECT r.id FROM discovery_runs r WHERE r.search_id = ss.id ORDER BY r.created_at DESC LIMIT 1) AS last_run_id
  FROM discovery_searches ss WHERE ss.saved AND ss.deleted_at IS NULL
 ORDER BY last_run_at DESC NULLS LAST, ss.name LIMIT 12"""


# ---------------------------------------------------------------- wfc_0012 (28 Oct 2026, second continuation: relationship research)
Q["org_research_pages_set"] = """
UPDATE organisations SET website = coalesce(CAST(:website AS text), website), newsroom_url = CAST(:newsroom AS text),
       leadership_url = CAST(:leadership AS text), updated_at = now()
 WHERE id = CAST(:id AS uuid) RETURNING id"""
Q["org_find_for_person"] = """
SELECT o.id, o.canonical_name FROM organisations o WHERE o.merged_into_id IS NULL AND (lower(o.canonical_name) = lower(CAST(:name AS text))
   OR EXISTS (SELECT 1 FROM organisation_aliases al WHERE al.organisation_id = o.id AND al.alias_norm = CAST(:norm AS text)))
ORDER BY o.created_at LIMIT 1"""

# ---- research documents
_RDOC_COLS = """rd.id, rd.opportunity_id, rd.organisation_id, org.canonical_name AS organisation, rd.origin, rd.url, rd.source_document_id,
       rd.title, rd.page_kind, rd.found_via, rd.status, rd.status_reason, rd.sections_total, rd.sections_read, rd.ai_status,
       rd.ai_sections_read, rd.people_found, rd.added_at, rd.fetched_at, rd.updated_at"""
Q["rdoc_add"] = """
INSERT INTO research_documents (opportunity_id, discovery_id, organisation_id, origin, url, source_document_id, title, page_kind, found_via,
                                status, status_reason, body_text, content_sha256, session_ref)
VALUES (CAST(:opp AS uuid), CAST(:disc AS uuid), CAST(:org AS uuid), CAST(:origin AS text), CAST(:url AS text), CAST(:source_doc AS uuid), CAST(:title AS text),
        CAST(:page_kind AS text), CAST(:found_via AS text), CAST(:status AS text), CAST(:reason AS text), CAST(:body AS text),
        CAST(:sha AS text), CAST(:session_ref AS text))
ON CONFLICT DO NOTHING RETURNING id"""
Q["rdoc_get"] = f"""
SELECT {_RDOC_COLS}, rd.body_text, rd.content_sha256 FROM research_documents rd LEFT JOIN organisations org ON org.id = rd.organisation_id
 WHERE rd.id = CAST(:id AS uuid)"""
Q["rdoc_for_opp"] = f"""
SELECT {_RDOC_COLS} FROM research_documents rd LEFT JOIN organisations org ON org.id = rd.organisation_id
 WHERE (rd.opportunity_id = CAST(:id AS uuid) OR rd.discovery_id = CAST(:disc AS uuid))
 ORDER BY CASE rd.status WHEN 'queued' THEN 0 WHEN 'partial' THEN 1 WHEN 'failed' THEN 2 WHEN 'read' THEN 3 ELSE 4 END,
          CASE rd.origin WHEN 'opportunity_source' THEN 0 WHEN 'user_document' THEN 1 WHEN 'user_url' THEN 2 WHEN 'organisation_page' THEN 3
                         WHEN 'followed_link' THEN 4 WHEN 'search_result' THEN 5 ELSE 6 END, rd.added_at"""
Q["rdoc_pending"] = f"""
SELECT {_RDOC_COLS}, rd.body_text FROM research_documents rd LEFT JOIN organisations org ON org.id = rd.organisation_id
 WHERE (rd.opportunity_id = CAST(:id AS uuid) OR rd.discovery_id = CAST(:disc AS uuid)) AND rd.status = 'queued'
 ORDER BY CASE rd.origin WHEN 'opportunity_source' THEN 0 WHEN 'user_document' THEN 1 WHEN 'user_url' THEN 2 WHEN 'organisation_page' THEN 3
                         WHEN 'followed_link' THEN 4 WHEN 'search_result' THEN 5 ELSE 6 END, rd.added_at"""
Q["rdoc_ai_pending"] = f"""
SELECT {_RDOC_COLS}, rd.body_text FROM research_documents rd LEFT JOIN organisations org ON org.id = rd.organisation_id
 WHERE (rd.opportunity_id = CAST(:id AS uuid) OR rd.discovery_id = CAST(:disc AS uuid)) AND rd.status IN ('read','partial') AND rd.body_text IS NOT NULL
   AND rd.ai_sections_read < rd.sections_total AND rd.ai_status IN ('not_run','not_connected','partial','budget_refused','failed')
 ORDER BY rd.added_at"""
Q["rdoc_requeue_failed"] = """
UPDATE research_documents SET status = 'queued', status_reason = 'retried after: ' || coalesce(status_reason, 'failure'), updated_at = now()
 WHERE (opportunity_id = CAST(:id AS uuid) OR discovery_id = CAST(:disc AS uuid)) AND status = 'failed'
   AND coalesce(status_reason, '') NOT LIKE 'retried after:%'
RETURNING id"""
Q["rdoc_read"] = """
UPDATE research_documents SET status = CAST(:status AS text), status_reason = CAST(:reason AS text),
       title = coalesce(CAST(:title AS text), title), page_kind = coalesce(CAST(:page_kind AS text), page_kind),
       body_text = coalesce(CAST(:body AS text), body_text), content_sha256 = coalesce(CAST(:sha AS text), content_sha256),
       url = coalesce(url, CAST(:final_url AS text)), sections_total = CAST(:sections_total AS int), sections_read = CAST(:sections_read AS int),
       fetched_at = coalesce(CAST(:fetched AS timestamptz), fetched_at), updated_at = now()
 WHERE id = CAST(:id AS uuid)"""
Q["rdoc_ai"] = """
UPDATE research_documents SET ai_status = CAST(:ai_status AS text), ai_sections_read = CAST(:ai_read AS int), updated_at = now()
 WHERE id = CAST(:id AS uuid)"""
Q["rdoc_people"] = """
UPDATE research_documents SET people_found = (SELECT count(DISTINCT e.person_id) FROM person_evidence e
                                              WHERE e.research_document_id = CAST(:id AS uuid)), updated_at = now()
 WHERE id = CAST(:id AS uuid)"""

# ---- evidence with research documents, and evidence-backed roles
Q["rel_evidence_add2"] = """
WITH ins AS (
  INSERT INTO person_evidence (person_id, supports, source_kind, document_id, research_document_id, url, quote, note, session_ref)
  VALUES (CAST(:person AS uuid), CAST(:supports AS text), CAST(:kind AS text), CAST(:doc AS uuid), CAST(:rdoc AS uuid), CAST(:url AS text),
          CAST(:quote AS text), CAST(:note AS text), CAST(:session_ref AS text))
  ON CONFLICT DO NOTHING RETURNING id)
SELECT id FROM ins
UNION ALL
SELECT e.id FROM person_evidence e
 WHERE NOT EXISTS (SELECT 1 FROM ins) AND e.person_id = CAST(:person AS uuid) AND e.supports = CAST(:supports AS text)
   AND e.source_kind = CAST(:kind AS text) AND e.document_id IS NOT DISTINCT FROM CAST(:doc AS uuid)
   AND e.research_document_id IS NOT DISTINCT FROM CAST(:rdoc AS uuid) AND coalesce(e.url, '') = coalesce(CAST(:url AS text), '')
   AND md5(coalesce(e.quote, '')) = md5(coalesce(CAST(:quote AS text), ''))
LIMIT 1"""
Q["rel_role_add"] = """
INSERT INTO person_roles (person_id, role_title, organisation_id, organisation_label, role_status, affiliation, binding, evidence_id, source)
VALUES (CAST(:person AS uuid), CAST(:role AS text), CAST(:org AS uuid), CAST(:org_label AS text), CAST(:status AS text),
        CAST(:affiliation AS text), CAST(:binding AS text), CAST(:evidence AS uuid), CAST(:source AS text))
ON CONFLICT DO NOTHING RETURNING id"""
Q["rel_roles_for"] = """
SELECT pr.id, pr.role_title, pr.organisation_id, coalesce(o.canonical_name, pr.organisation_label) AS organisation, pr.role_status,
       pr.affiliation, pr.binding, pr.source, pr.confirmed_at, pr.created_at, e.quote, coalesce(e.url, d.canonical_url, rd.url) AS url,
       coalesce(d.title, rd.title) AS document_title
  FROM person_roles pr LEFT JOIN organisations o ON o.id = pr.organisation_id LEFT JOIN person_evidence e ON e.id = pr.evidence_id
  LEFT JOIN source_documents d ON d.id = e.document_id LEFT JOIN research_documents rd ON rd.id = e.research_document_id
 WHERE pr.person_id = CAST(:id AS uuid)
 ORDER BY CASE pr.role_status WHEN 'current' THEN 0 WHEN 'incoming' THEN 1 ELSE 2 END, pr.created_at"""
Q["rel_roles_for_opp"] = """
SELECT pr.person_id, pr.role_title, coalesce(o.canonical_name, pr.organisation_label) AS organisation, pr.role_status, pr.affiliation,
       pr.binding, pr.source, e.quote
  FROM opportunity_people op JOIN person_roles pr ON pr.person_id = op.person_id LEFT JOIN organisations o ON o.id = pr.organisation_id
  LEFT JOIN person_evidence e ON e.id = pr.evidence_id
 WHERE op.opportunity_id = CAST(:id AS uuid)
 ORDER BY pr.person_id, CASE pr.role_status WHEN 'current' THEN 0 WHEN 'incoming' THEN 1 ELSE 2 END, pr.created_at"""
Q["rel_person_org_if_empty"] = """
UPDATE people SET organisation_id = CAST(:org AS uuid), organisation_label = CASE WHEN CAST(:org AS uuid) IS NULL THEN CAST(:org_label AS text) END,
       updated_at = now()
 WHERE id = CAST(:id AS uuid) AND organisation_id IS NULL AND organisation_label IS NULL"""

# ---- identity matching: never on the name alone when the organisation is unknown
Q["rel_person_by_passage"] = """
SELECT p.id FROM person_evidence e JOIN people p ON p.id = e.person_id AND p.merged_into_id IS NULL
 WHERE lower(regexp_replace(p.full_name, '\\s+', ' ', 'g')) = lower(CAST(:name AS text))
   AND e.source_kind = CAST(:kind AS text) AND e.document_id IS NOT DISTINCT FROM CAST(:doc AS uuid)
   AND e.research_document_id IS NOT DISTINCT FROM CAST(:rdoc AS uuid) AND coalesce(e.url, '') = coalesce(CAST(:url AS text), '')
   AND (md5(coalesce(e.quote, '')) = md5(coalesce(CAST(:quote AS text), ''))
        -- the same passage quoted more or less fully (the rules quote the sentence, the AI extractor may quote part of it)
        OR (length(CAST(:quote AS text)) >= 20 AND length(e.quote) >= 20
            AND (strpos(lower(e.quote), lower(CAST(:quote AS text))) > 0 OR strpos(lower(CAST(:quote AS text)), lower(e.quote)) > 0)))
 ORDER BY p.created_at LIMIT 1"""
# The identical statement republished (a syndicated copy of the same notice, already resolved to this opportunity) names the
# same person: the passage, not the name, is what matches.
Q["rel_person_by_statement_on_opp"] = """
SELECT p.id FROM opportunity_people op JOIN people p ON p.id = op.person_id AND p.merged_into_id IS NULL
 WHERE op.opportunity_id = CAST(:opp AS uuid) AND lower(regexp_replace(p.full_name, '\\s+', ' ', 'g')) = lower(CAST(:name AS text))
   AND EXISTS (SELECT 1 FROM person_evidence e WHERE e.person_id = p.id AND md5(coalesce(e.quote, '')) = md5(CAST(:quote AS text)))
 ORDER BY p.created_at LIMIT 1"""
Q["rel_person_by_name_org"] = """
SELECT p.id FROM people p
 WHERE NOT p.is_internal AND p.merged_into_id IS NULL
   AND lower(regexp_replace(p.full_name, '\\s+', ' ', 'g')) = lower(CAST(:name AS text))
   AND ((CAST(:org AS uuid) IS NOT NULL AND (p.organisation_id = CAST(:org AS uuid)
          OR (p.organisation_id IS NULL AND lower(p.organisation_label) = (SELECT lower(o.canonical_name) FROM organisations o
                                                                           WHERE o.id = CAST(:org AS uuid)))
          OR EXISTS (SELECT 1 FROM person_roles pr WHERE pr.person_id = p.id AND pr.organisation_id = CAST(:org AS uuid))))
        OR (CAST(:org AS uuid) IS NULL AND CAST(:org_label AS text) IS NOT NULL AND p.organisation_id IS NULL
            AND lower(p.organisation_label) = lower(CAST(:org_label AS text))))
 ORDER BY p.created_at LIMIT 1"""
Q["rel_people_same_name"] = """
SELECT p.id, p.organisation_id, p.organisation_label FROM people p
 WHERE NOT p.is_internal AND p.merged_into_id IS NULL AND p.id <> CAST(:id AS uuid)
   AND lower(regexp_replace(p.full_name, '\\s+', ' ', 'g')) = lower(CAST(:name AS text))"""
Q["dup_add"] = """
INSERT INTO person_duplicate_candidates (person_a, person_b, reason, session_ref)
VALUES (CAST(:a AS uuid), CAST(:b AS uuid), CAST(:reason AS text), CAST(:session_ref AS text)) ON CONFLICT DO NOTHING RETURNING id"""
_DUP_PERSON = """json_build_object('id', p.id, 'full_name', p.full_name, 'role_title', p.role_title,
       'organisation', coalesce(o.canonical_name, p.organisation_label), 'origin', p.origin, 'created_at', p.created_at,
       'evidence', (SELECT count(*) FROM person_evidence e WHERE e.person_id = p.id),
       'opportunities', (SELECT json_agg(json_build_object('id', op2.opportunity_id, 'title', oo.title))
                           FROM opportunity_people op2 JOIN opportunities oo ON oo.id = op2.opportunity_id WHERE op2.person_id = p.id),
       'state', (SELECT ps.state FROM person_state ps WHERE ps.person_id = p.id))"""
Q["dup_list"] = f"""
SELECT d.id, d.reason, d.status, d.created_at, d.decided_at, d.decision_note,
       (SELECT {_DUP_PERSON} FROM people p LEFT JOIN organisations o ON o.id = p.organisation_id WHERE p.id = d.person_a) AS a,
       (SELECT {_DUP_PERSON} FROM people p LEFT JOIN organisations o ON o.id = p.organisation_id WHERE p.id = d.person_b) AS b,
       (SELECT m.id FROM person_merges m WHERE m.duplicate_id = d.id AND m.undone_at IS NULL LIMIT 1) AS merge_id
  FROM person_duplicate_candidates d
 WHERE (CAST(:status AS text) IS NULL OR d.status = CAST(:status AS text))
   AND (CAST(:person AS uuid) IS NULL OR CAST(:person AS uuid) IN (d.person_a, d.person_b))
 ORDER BY d.status = 'open' DESC, d.created_at DESC LIMIT 200"""
Q["dup_get"] = "SELECT * FROM person_duplicate_candidates WHERE id = CAST(:id AS uuid)"
Q["dup_decide"] = """
UPDATE person_duplicate_candidates SET status = CAST(:status AS text), decided_at = CASE WHEN CAST(:status AS text) = 'open' THEN NULL ELSE now() END,
       decision_note = CAST(:note AS text)
 WHERE id = CAST(:id AS uuid) RETURNING id"""
Q["dup_open_count"] = "SELECT count(*) FROM person_duplicate_candidates WHERE status = 'open'"

# ---- reversible merge: every moved row is listed so the merge can be undone exactly
Q["merge_snapshot"] = """
SELECT json_build_object(
  'evidence', (SELECT coalesce(json_agg(id), '[]') FROM person_evidence WHERE person_id = CAST(:m AS uuid)),
  'roles', (SELECT coalesce(json_agg(id), '[]') FROM person_roles WHERE person_id = CAST(:m AS uuid)),
  'relationships', (SELECT coalesce(json_agg(id), '[]') FROM person_relationships WHERE person_id = CAST(:m AS uuid)),
  'routes_target', (SELECT coalesce(json_agg(id), '[]') FROM introduction_routes WHERE target_person_id = CAST(:m AS uuid)),
  'routes_introducer', (SELECT coalesce(json_agg(id), '[]') FROM introduction_routes WHERE introducer_person_id = CAST(:m AS uuid)),
  'engagements', (SELECT coalesce(json_agg(id), '[]') FROM engagements WHERE person_id = CAST(:m AS uuid)),
  'links', (SELECT coalesce(json_agg(json_build_object('opportunity_id', opportunity_id, 'role', role_on_opportunity,
                                                       'basis', relevance_basis, 'status', status, 'added_at', added_at,
                                                       'kept_had_link', EXISTS (SELECT 1 FROM opportunity_people k
                                                           WHERE k.opportunity_id = op.opportunity_id AND k.person_id = CAST(:k AS uuid)))), '[]')
              FROM opportunity_people op WHERE person_id = CAST(:m AS uuid))) AS moved,
  (SELECT row_to_json(p) FROM (SELECT role_title, organisation_id, organisation_label, identity_confirmed_at, identity_basis,
                                      last_verified_at, linkedin_profile_url, linkedin_confirmed_at, relationship_owner, remit_text, remit_basis,
                                      next_action, notes FROM people WHERE id = CAST(:k AS uuid)) p) AS kept_before"""
Q["merge_move"] = """
WITH ev AS (UPDATE person_evidence SET person_id = CAST(:k AS uuid) WHERE person_id = CAST(:m AS uuid) RETURNING 1),
     ro AS (UPDATE person_roles SET person_id = CAST(:k AS uuid) WHERE person_id = CAST(:m AS uuid) RETURNING 1),
     re AS (UPDATE person_relationships SET person_id = CAST(:k AS uuid) WHERE person_id = CAST(:m AS uuid) RETURNING 1),
     rt AS (UPDATE introduction_routes SET target_person_id = CAST(:k AS uuid) WHERE target_person_id = CAST(:m AS uuid) RETURNING 1),
     ri AS (UPDATE introduction_routes SET introducer_person_id = CAST(:k AS uuid) WHERE introducer_person_id = CAST(:m AS uuid) RETURNING 1),
     en AS (UPDATE engagements SET person_id = CAST(:k AS uuid) WHERE person_id = CAST(:m AS uuid) RETURNING 1),
     li AS (INSERT INTO opportunity_people (opportunity_id, person_id, role_on_opportunity, relevance_basis, status, added_at)
            SELECT opportunity_id, CAST(:k AS uuid), role_on_opportunity, relevance_basis, status, added_at FROM opportunity_people
             WHERE person_id = CAST(:m AS uuid) ON CONFLICT (opportunity_id, person_id) DO NOTHING RETURNING 1),
     dl AS (DELETE FROM opportunity_people WHERE person_id = CAST(:m AS uuid) RETURNING 1)
SELECT (SELECT count(*) FROM ev) + (SELECT count(*) FROM ro) + (SELECT count(*) FROM re) + (SELECT count(*) FROM rt) + (SELECT count(*) FROM ri)
       + (SELECT count(*) FROM en) + (SELECT count(*) FROM li) + (SELECT count(*) FROM dl)"""
Q["merge_fill_kept"] = """
UPDATE people k SET role_title = coalesce(k.role_title, m.role_title),
       organisation_id = coalesce(k.organisation_id, CASE WHEN k.organisation_label IS NULL THEN m.organisation_id END),
       organisation_label = coalesce(k.organisation_label, CASE WHEN k.organisation_id IS NULL THEN m.organisation_label END),
       identity_confirmed_at = coalesce(k.identity_confirmed_at, m.identity_confirmed_at), identity_basis = coalesce(k.identity_basis, m.identity_basis),
       last_verified_at = greatest(k.last_verified_at, m.last_verified_at),
       linkedin_profile_url = coalesce(k.linkedin_profile_url, m.linkedin_profile_url),
       linkedin_confirmed_at = coalesce(k.linkedin_confirmed_at, m.linkedin_confirmed_at),
       relationship_owner = coalesce(k.relationship_owner, m.relationship_owner), remit_text = coalesce(k.remit_text, m.remit_text),
       remit_basis = coalesce(k.remit_basis, m.remit_basis), next_action = coalesce(k.next_action, m.next_action),
       notes = coalesce(k.notes, m.notes), updated_at = now()
  FROM people m WHERE k.id = CAST(:k AS uuid) AND m.id = CAST(:m AS uuid)"""
Q["merge_mark"] = """
UPDATE people SET merged_into_id = CAST(:k AS uuid), updated_at = now() WHERE id = CAST(:m AS uuid) AND merged_into_id IS NULL RETURNING id"""
Q["merge_insert"] = """
INSERT INTO person_merges (kept_person_id, merged_person_id, duplicate_id, moved, kept_before, note, session_ref)
VALUES (CAST(:k AS uuid), CAST(:m AS uuid), CAST(:dup AS uuid), CAST(:moved AS jsonb), CAST(:kept_before AS jsonb), CAST(:note AS text),
        CAST(:session_ref AS text)) RETURNING id"""
Q["merge_get"] = "SELECT * FROM person_merges WHERE id = CAST(:id AS uuid)"
Q["merges_for"] = """
SELECT m.id, m.kept_person_id, k.full_name AS kept_name, m.merged_person_id, x.full_name AS merged_name, m.merged_at, m.undone_at, m.note
  FROM person_merges m JOIN people k ON k.id = m.kept_person_id JOIN people x ON x.id = m.merged_person_id
 WHERE CAST(:id AS uuid) IN (m.kept_person_id, m.merged_person_id) ORDER BY m.merged_at DESC"""
Q["unmerge_rows"] = """
WITH ev AS (UPDATE person_evidence SET person_id = CAST(:m AS uuid) WHERE id IN (SELECT (jsonb_array_elements_text(CAST(:ev AS jsonb)))::uuid) RETURNING 1),
     ro AS (UPDATE person_roles SET person_id = CAST(:m AS uuid) WHERE id IN (SELECT (jsonb_array_elements_text(CAST(:ro AS jsonb)))::uuid) RETURNING 1),
     re AS (UPDATE person_relationships SET person_id = CAST(:m AS uuid) WHERE id IN (SELECT (jsonb_array_elements_text(CAST(:re AS jsonb)))::uuid) RETURNING 1),
     rt AS (UPDATE introduction_routes SET target_person_id = CAST(:m AS uuid) WHERE id IN (SELECT (jsonb_array_elements_text(CAST(:rt AS jsonb)))::uuid) RETURNING 1),
     ri AS (UPDATE introduction_routes SET introducer_person_id = CAST(:m AS uuid) WHERE id IN (SELECT (jsonb_array_elements_text(CAST(:ri AS jsonb)))::uuid) RETURNING 1),
     en AS (UPDATE engagements SET person_id = CAST(:m AS uuid) WHERE id IN (SELECT (jsonb_array_elements_text(CAST(:en AS jsonb)))::uuid) RETURNING 1)
SELECT (SELECT count(*) FROM ev) + (SELECT count(*) FROM ro) + (SELECT count(*) FROM re) + (SELECT count(*) FROM rt) + (SELECT count(*) FROM ri)
       + (SELECT count(*) FROM en)"""
Q["unmerge_link_restore"] = """
INSERT INTO opportunity_people (opportunity_id, person_id, role_on_opportunity, relevance_basis, status, added_at)
VALUES (CAST(:opp AS uuid), CAST(:m AS uuid), CAST(:role AS text), CAST(:basis AS text), CAST(:status AS text), CAST(:added_at AS timestamptz))
ON CONFLICT (opportunity_id, person_id) DO NOTHING"""
Q["unmerge_link_remove_kept"] = "DELETE FROM opportunity_people WHERE opportunity_id = CAST(:opp AS uuid) AND person_id = CAST(:k AS uuid)"
Q["unmerge_restore_kept"] = """
UPDATE people SET role_title = CAST(:b AS jsonb)->>'role_title', organisation_id = CAST(CAST(:b AS jsonb)->>'organisation_id' AS uuid),
       organisation_label = CAST(:b AS jsonb)->>'organisation_label',
       identity_confirmed_at = CAST(CAST(:b AS jsonb)->>'identity_confirmed_at' AS timestamptz), identity_basis = CAST(:b AS jsonb)->>'identity_basis',
       last_verified_at = CAST(CAST(:b AS jsonb)->>'last_verified_at' AS timestamptz),
       linkedin_profile_url = CAST(:b AS jsonb)->>'linkedin_profile_url',
       linkedin_confirmed_at = CAST(CAST(:b AS jsonb)->>'linkedin_confirmed_at' AS timestamptz),
       relationship_owner = CAST(:b AS jsonb)->>'relationship_owner', remit_text = CAST(:b AS jsonb)->>'remit_text',
       remit_basis = CAST(:b AS jsonb)->>'remit_basis', next_action = CAST(:b AS jsonb)->>'next_action', notes = CAST(:b AS jsonb)->>'notes',
       updated_at = now()
 WHERE id = CAST(:k AS uuid)"""
Q["unmerge_mark"] = """
UPDATE people SET merged_into_id = NULL, updated_at = now() WHERE id = CAST(:m AS uuid) AND merged_into_id = CAST(:k AS uuid) RETURNING id"""
Q["merge_undone"] = "UPDATE person_merges SET undone_at = now() WHERE id = CAST(:id AS uuid) AND undone_at IS NULL RETURNING id"

# ---- research runs (outcome and coverage)
Q["rel_research_insert2"] = """
INSERT INTO relationship_research_runs (opportunity_id, methods, unavailable, organisations, target_roles, candidates_found, gaps, cost_usd,
                                        outcome, coverage, searches, finished_at, session_ref)
VALUES (CAST(:opp AS uuid), ARRAY(SELECT jsonb_array_elements_text(CAST(:methods AS jsonb))), CAST(:unavailable AS jsonb), CAST(:orgs AS jsonb),
        CAST(:roles AS jsonb), CAST(:found AS int), CAST(:gaps AS jsonb), CAST(:cost AS numeric), CAST(:outcome AS text),
        CAST(:coverage AS jsonb), CAST(:searches AS jsonb), now(), CAST(:session_ref AS text))
RETURNING id"""
Q["rel_routes_for_opp"] = """
SELECT i.id, i.target_person_id, t.full_name AS target, coalesce(ip.full_name, i.introducer_label) AS introducer, i.wfc_holder_label,
       i.connection_basis, i.evidence_url, i.willingness_confirmed, i.willingness_basis, i.status, i.updated_at
  FROM introduction_routes i JOIN people t ON t.id = i.target_person_id AND t.merged_into_id IS NULL
  LEFT JOIN people ip ON ip.id = i.introducer_person_id
 WHERE i.opportunity_id = CAST(:id AS uuid)
    OR i.target_person_id IN (SELECT op.person_id FROM opportunity_people op WHERE op.opportunity_id = CAST(:id AS uuid) AND op.status <> 'not_relevant')
 ORDER BY CASE i.status WHEN 'available' THEN 0 WHEN 'requested' THEN 1 WHEN 'made' THEN 2 WHEN 'possible' THEN 3 ELSE 4 END, i.updated_at DESC"""
Q["rel_relationships_for_opp"] = """
SELECT r.id, r.person_id, p.full_name AS person, r.holder_label, r.nature, r.basis, r.status, r.recorded_at
  FROM person_relationships r JOIN people p ON p.id = r.person_id AND p.merged_into_id IS NULL
 WHERE r.person_id IN (SELECT op.person_id FROM opportunity_people op WHERE op.opportunity_id = CAST(:id AS uuid) AND op.status <> 'not_relevant')
    OR r.person_id IN (SELECT p2.id FROM opportunities o JOIN people p2 ON p2.organisation_id = coalesce(o.airline_id, o.organisation_id)
                       WHERE o.id = CAST(:id AS uuid))
 ORDER BY r.status, r.recorded_at DESC"""


# ---------------------------------------------------------------- wfc_0013 (29 Oct 2026: ATLAS v1.0 relationship parameters, open-market discovery)
Q["disc_insert"] = """
INSERT INTO contact_discoveries (organisation_id, organisation_label, countries, region_code, capability_area, role_focus, brief,
                                 requested_by_label, session_ref, purpose, brief_text, airport_iata, organisation_kinds)
VALUES (CAST(:org AS uuid), CAST(:org_label AS text), ARRAY(SELECT jsonb_array_elements_text(CAST(:countries AS jsonb)))::char(2)[],
        CAST(:region AS text), CAST(:module AS text), CAST(:role_focus AS text), CAST(:brief AS text), CAST(:by AS text), CAST(:session_ref AS text),
        CAST(:purpose AS text), CAST(:brief_text AS text), CAST(:airport AS char(3)), ARRAY(SELECT jsonb_array_elements_text(CAST(:kinds AS jsonb))))
RETURNING id"""
Q["disc_finish"] = """
UPDATE contact_discoveries SET status = 'finished', outcome = CAST(:outcome AS text),
       methods = ARRAY(SELECT jsonb_array_elements_text(CAST(:methods AS jsonb))), unavailable = CAST(:unavailable AS jsonb),
       coverage = CAST(:coverage AS jsonb), searches = CAST(:searches AS jsonb),
       people_found = (SELECT count(*) FROM discovery_people dp WHERE dp.discovery_id = CAST(:id AS uuid)),
       runs = runs + 1, cost_usd = cost_usd + CAST(:cost AS numeric), finished_at = now()
 WHERE id = CAST(:id AS uuid)"""
Q["disc_reopen"] = "UPDATE contact_discoveries SET status = 'running' WHERE id = CAST(:id AS uuid) RETURNING id"
_DISC_COLS = """d.id, d.organisation_id, coalesce(o.canonical_name, d.organisation_label) AS organisation, o.kind AS organisation_kind,
       o.website, d.countries::text[] AS countries, d.region_code, d.capability_area, d.role_focus, d.brief, d.status, d.outcome, d.methods,
       d.unavailable, d.coverage, d.searches, d.people_found, d.runs, d.cost_usd, d.started_at, d.finished_at, d.requested_by_label,
       d.purpose, d.brief_text, d.airport_iata::text AS airport_iata, d.organisation_kinds,
       (SELECT count(*) FROM discovery_organisations x WHERE x.discovery_id = d.id) AS organisations_found"""
Q["disc_get"] = f"SELECT {_DISC_COLS} FROM contact_discoveries d LEFT JOIN organisations o ON o.id = d.organisation_id WHERE d.id = CAST(:id AS uuid)"
Q["disc_list"] = f"""
SELECT {_DISC_COLS} FROM contact_discoveries d LEFT JOIN organisations o ON o.id = d.organisation_id
 WHERE (CAST(:purpose AS text) IS NULL OR d.purpose = CAST(:purpose AS text))
 ORDER BY d.started_at DESC LIMIT CAST(:limit AS int)"""
Q["disc_person_link"] = """
INSERT INTO discovery_people (discovery_id, person_id, new_record) VALUES (CAST(:disc AS uuid), CAST(:person AS uuid), CAST(:new AS boolean))
ON CONFLICT (discovery_id, person_id) DO NOTHING"""
Q["disc_person_relevance"] = """
UPDATE discovery_people SET relevance_score = CAST(:score AS int), relevance = CAST(:relevance AS jsonb)
 WHERE discovery_id = CAST(:disc AS uuid) AND person_id = CAST(:person AS uuid)"""
Q["disc_people"] = """
SELECT dp.person_id, dp.relevance_score, dp.relevance, dp.new_record, p.full_name, p.role_title, p.organisation_id,
       coalesce(o.canonical_name, p.organisation_label) AS organisation, o.kind AS organisation_kind, o.country::text AS organisation_country,
       p.remit_countries::text[] AS remit_countries, p.capability_area, p.linkedin_profile_url, ps.state,
       (SELECT pr.binding FROM person_roles pr WHERE pr.person_id = p.id ORDER BY pr.role_status = 'current' DESC, pr.created_at LIMIT 1) AS binding,
       (SELECT rd.page_kind FROM person_evidence e JOIN research_documents rd ON rd.id = e.research_document_id
         WHERE e.person_id = p.id AND rd.discovery_id = dp.discovery_id ORDER BY rd.page_kind = 'leadership' DESC LIMIT 1) AS page_kind,
       (SELECT coalesce(e.url, rd.url) FROM person_evidence e LEFT JOIN research_documents rd ON rd.id = e.research_document_id
         WHERE e.person_id = p.id AND e.supports IN ('role','relevance') ORDER BY e.supports = 'role' DESC, e.observed_at LIMIT 1) AS source_url,
       (SELECT e.quote FROM person_evidence e WHERE e.person_id = p.id AND e.supports IN ('role','relevance')
         ORDER BY e.supports = 'role' DESC, e.observed_at LIMIT 1) AS quote
  FROM discovery_people dp JOIN people p ON p.id = dp.person_id LEFT JOIN organisations o ON o.id = p.organisation_id
  LEFT JOIN person_state ps ON ps.person_id = p.id
 WHERE dp.discovery_id = CAST(:id AS uuid) ORDER BY dp.relevance_score DESC, p.full_name"""
Q["person_set_capability_area"] = """
UPDATE people SET capability_area = coalesce(capability_area, CAST(:module AS text)), updated_at = now() WHERE id = CAST(:id AS uuid)"""

# stakeholder judgements (recorded by a person, with a basis)
Q["person_judgement_set"] = """
UPDATE people SET stakeholder_type = CAST(:stakeholder_type AS text), decision_authority = CAST(:decision_authority AS text),
       posture = CAST(:posture AS text), judgement_basis = CAST(:basis AS text), judgement_by_label = CAST(:by AS text), judgement_at = now(),
       key_interests = coalesce(CAST(:key_interests AS text), key_interests), strategic_account = CAST(:strategic AS boolean), updated_at = now()
 WHERE id = CAST(:id AS uuid) RETURNING id"""

# engagement statistics for health
Q["rel_engagement_stats"] = """
SELECT count(*) FILTER (WHERE e.occurred_at >= now() - interval '365 days') AS engagements_12m,
       count(*) FILTER (WHERE e.direction = 'outbound') AS outbound,
       count(*) FILTER (WHERE e.direction = 'outbound' AND coalesce(e.outcome, 'pending') NOT IN ('no_response','pending')) AS answered,
       count(*) FILTER (WHERE e.outcome = 'positive') AS positive, count(*) FILTER (WHERE e.outcome = 'neutral') AS neutral,
       count(*) FILTER (WHERE e.outcome = 'negative') AS negative, max(e.occurred_at) AS last_engagement, min(e.occurred_at) AS first_engagement,
       count(*) AS total
  FROM engagements e WHERE e.person_id = CAST(:id AS uuid)"""
Q["rel_engagements_recent"] = """
SELECT e.occurred_at, e.outcome, e.kind, e.direction FROM engagements e
 WHERE e.person_id = CAST(:id AS uuid) AND e.occurred_at >= now() - interval '200 days' ORDER BY e.occurred_at DESC"""
Q["rel_engagements_recent_all"] = """
SELECT e.person_id, e.occurred_at, e.outcome, e.kind, e.direction FROM engagements e
 WHERE e.occurred_at >= now() - interval '200 days' ORDER BY e.occurred_at DESC"""
Q["rel_engagement_stats_all"] = """
SELECT e.person_id,
       count(*) FILTER (WHERE e.occurred_at >= now() - interval '365 days') AS engagements_12m,
       count(*) FILTER (WHERE e.direction = 'outbound') AS outbound,
       count(*) FILTER (WHERE e.direction = 'outbound' AND coalesce(e.outcome, 'pending') NOT IN ('no_response','pending')) AS answered,
       count(*) FILTER (WHERE e.outcome = 'positive') AS positive, count(*) FILTER (WHERE e.outcome = 'neutral') AS neutral,
       count(*) FILTER (WHERE e.outcome = 'negative') AS negative, max(e.occurred_at) AS last_engagement, min(e.occurred_at) AS first_engagement,
       count(*) AS total
  FROM engagements e GROUP BY e.person_id"""
# live opportunities each person is linked to (for alignment and the questions)
Q["rel_person_live_links_all"] = """
SELECT op.person_id, o.id AS opportunity_id, o.title, o.module, o.record_type, o.tender_status, o.progress, o.deadline_utc,
       coalesce(o.deadline_utc, o.deadline_latest_utc) AS deadline_at, o.created_at,
       ARRAY(SELECT DISTINCT g.country_code::text FROM opportunity_geography g WHERE g.opportunity_id = o.id
             AND g.support IN ('supported','internal_record')) AS countries,
       (SELECT count(*) FROM claims c JOIN signal_claims sc ON sc.claim_id = c.id
         WHERE sc.signal_id = coalesce(o.signal_id, o.tracked_from_signal_id) AND c.review_status = 'confirmed') AS reviewed_claims,
       coalesce(cov.level, 'none') AS coverage, s.classification, coalesce(o.freight_scope, s.freight_scope) AS freight_scope,
       (s.tender_state->>'status_conflict') AS status_conflict,
       coalesce(CAST(s.tender_state->>'published_at' AS timestamptz), s.first_published_at) AS source_date
  FROM opportunity_people op JOIN opportunities o ON o.id = op.opportunity_id AND o.merged_into_id IS NULL
  LEFT JOIN signals s ON s.id = coalesce(o.signal_id, o.tracked_from_signal_id)
  LEFT JOIN opportunity_relationship_coverage cov ON cov.opportunity_id = o.id
 WHERE op.status <> 'not_relevant' AND o.record_type NOT IN ('historical','excluded') AND coalesce(o.progress, 'new') <> 'closed'
   AND coalesce(o.tender_status, '') NOT IN ('cancelled','awarded','closed','expired','historical')"""
Q["rel_people_all_for_health"] = """
SELECT p.id, p.full_name, p.role_title, coalesce(o.canonical_name, p.organisation_label) AS organisation, o.kind AS organisation_kind,
       o.country::text AS organisation_country, p.remit_countries::text[] AS remit_countries, p.stakeholder_type, p.decision_authority,
       p.posture, p.judgement_basis, p.judgement_at, p.strategic_account, p.relationship_owner, p.next_action, p.next_action_due,
       p.capability_area, ps.state, p.created_at
  FROM people p JOIN person_state ps ON ps.person_id = p.id LEFT JOIN organisations o ON o.id = p.organisation_id
 WHERE NOT p.is_internal AND p.merged_into_id IS NULL"""
Q["saved_search_countries"] = """
SELECT DISTINCT unnest(ss.countries)::text AS code FROM discovery_searches ss WHERE ss.saved AND ss.deleted_at IS NULL AND ss.countries IS NOT NULL"""
# live opportunities and their stakeholder coverage (who are we missing)
Q["rel_live_opportunities_stakeholders"] = """
SELECT o.id, o.title, o.module, o.record_type, o.tender_status, o.progress, coalesce(o.deadline_utc, o.deadline_latest_utc) AS deadline_at,
       coalesce(cov.level, 'none') AS coverage,
       ARRAY(SELECT DISTINCT p.stakeholder_type FROM opportunity_people op JOIN people p ON p.id = op.person_id
              WHERE op.opportunity_id = o.id AND op.status <> 'not_relevant' AND p.merged_into_id IS NULL) AS stakeholder_types,
       ARRAY(SELECT DISTINCT op.role_on_opportunity FROM opportunity_people op JOIN people p ON p.id = op.person_id
              JOIN person_state ps ON ps.person_id = p.id
              WHERE op.opportunity_id = o.id AND op.status <> 'not_relevant' AND p.merged_into_id IS NULL AND ps.state <> 'research_candidate'
              ) AS roles_confirmed,
       (SELECT count(*) FROM opportunity_people op WHERE op.opportunity_id = o.id AND op.status <> 'not_relevant') AS people
  FROM opportunities o LEFT JOIN opportunity_relationship_coverage cov ON cov.opportunity_id = o.id
 WHERE o.merged_into_id IS NULL AND o.record_type NOT IN ('historical','excluded') AND coalesce(o.progress, 'new') <> 'closed'
   AND coalesce(o.tender_status, '') NOT IN ('cancelled','awarded','closed','expired','historical')
 ORDER BY o.created_at DESC"""

# outreach drafts: written by ATLAS, sent by a person
Q["outreach_insert"] = """
INSERT INTO outreach_drafts (person_id, opportunity_id, channel, subject, body, source, basis, cost_usd, session_ref)
VALUES (CAST(:person AS uuid), CAST(:opp AS uuid), CAST(:channel AS text), CAST(:subject AS text), CAST(:body AS text), CAST(:source AS text),
        CAST(:basis AS jsonb), CAST(:cost AS numeric), CAST(:session_ref AS text)) RETURNING id"""
Q["outreach_get"] = """
SELECT d.*, p.full_name AS person, o.title AS opportunity_title FROM outreach_drafts d JOIN people p ON p.id = d.person_id
  LEFT JOIN opportunities o ON o.id = d.opportunity_id WHERE d.id = CAST(:id AS uuid)"""
Q["outreach_for"] = """
SELECT d.id, d.opportunity_id, o.title AS opportunity_title, d.channel, d.subject, d.body, d.source, d.basis, d.status, d.sent_at, d.sent_by_label,
       d.sent_note, d.created_at
  FROM outreach_drafts d LEFT JOIN opportunities o ON o.id = d.opportunity_id
 WHERE d.person_id = CAST(:id AS uuid) ORDER BY d.created_at DESC"""
Q["outreach_update"] = """
UPDATE outreach_drafts SET subject = coalesce(CAST(:subject AS text), subject), body = coalesce(CAST(:body AS text), body), updated_at = now()
 WHERE id = CAST(:id AS uuid) AND status = 'draft' RETURNING id"""
Q["outreach_status"] = """
UPDATE outreach_drafts SET status = CAST(:status AS text), sent_at = CASE WHEN CAST(:status AS text) = 'sent' THEN now() END,
       sent_by_label = CAST(:by AS text), sent_note = CAST(:note AS text), updated_at = now()
 WHERE id = CAST(:id AS uuid) AND status = 'draft' RETURNING id"""
Q["org_get_for_research"] = """
SELECT o.id, o.canonical_name AS name, o.kind, o.country::text AS country, o.website, o.newsroom_url, o.leadership_url
  FROM organisations o WHERE o.id = CAST(:id AS uuid) AND o.merged_into_id IS NULL"""


# ---------------------------------------------------------------- wfc_0014 (29 Oct 2026: open-web discovery)
Q["document_set_web_publisher"] = """
UPDATE source_documents SET doc_family = CAST(:family AS text), doc_authority = CAST(:authority AS text) WHERE id = CAST(:id AS uuid)"""
Q["organisation_websites"] = "SELECT website FROM organisations WHERE website IS NOT NULL AND merged_into_id IS NULL"
Q["source_open_web"] = "SELECT * FROM sources WHERE source_type = 'web_search' AND deleted_at IS NULL ORDER BY created_at LIMIT 1"


# ---------------------------------------------------------------- wfc_0015 (29 Oct 2026: research purposes; company intelligence; supplied data)
Q["rdoc_bodies"] = f"""
SELECT {_RDOC_COLS}, rd.body_text FROM research_documents rd LEFT JOIN organisations org ON org.id = rd.organisation_id
 WHERE rd.discovery_id = CAST(:disc AS uuid) AND rd.status IN ('read','partial') AND rd.body_text IS NOT NULL ORDER BY rd.added_at"""
Q["org_airline_names"] = "SELECT canonical_name FROM organisations WHERE kind = 'airline' AND merged_into_id IS NULL"
Q["org_website"] = "SELECT website FROM organisations WHERE id = CAST(:id AS uuid)"
Q["rdoc_set_org"] = "UPDATE research_documents SET organisation_id = coalesce(organisation_id, CAST(:org AS uuid)) WHERE id = CAST(:id AS uuid)"
Q["org_insert_profile"] = """
INSERT INTO organisations (canonical_name, kind, country, website, origin, airport_iata, carrier_type, supplied_at, resolution_status)
VALUES (CAST(:name AS text), CAST(:kind AS text), CAST(:country AS text), CAST(:website AS text), CAST(:origin AS text), CAST(:airport AS char(3)),
        CAST(:carrier_type AS text), CASE WHEN CAST(:origin AS text) = 'supplied' THEN now() END,
        CASE WHEN CAST(:origin AS text) IN ('discovery','supplied') THEN 'auto_created' ELSE 'resolved' END)
RETURNING id"""
Q["org_profile_fill"] = """
UPDATE organisations SET website = coalesce(website, CAST(:website AS text)), country = coalesce(country, CAST(:country AS text)),
       kind = CASE WHEN kind = 'other' AND CAST(:kind AS text) IS NOT NULL THEN CAST(:kind AS text) ELSE kind END,
       description = coalesce(description, CAST(:description AS text)), services_text = coalesce(services_text, CAST(:services AS text)),
       locations_text = coalesce(locations_text, CAST(:locations AS text)), parent_group = coalesce(parent_group, CAST(:parent AS text)),
       airport_iata = coalesce(airport_iata, CAST(:airport AS char(3))),
       carrier_type = CASE WHEN carrier_type IS NULL OR carrier_type = 'unknown' THEN coalesce(CAST(:carrier_type AS text), carrier_type) ELSE carrier_type END,
       capability_areas = (SELECT ARRAY(SELECT DISTINCT x FROM unnest(capability_areas || ARRAY(SELECT jsonb_array_elements_text(CAST(:areas AS jsonb)))) x)),
       last_researched_at = CASE WHEN CAST(:researched AS boolean) THEN now() ELSE last_researched_at END, updated_at = now()
 WHERE id = CAST(:id AS uuid) RETURNING id"""
Q["org_profile_edit"] = """
UPDATE organisations SET website = coalesce(CAST(:website AS text), website), kind = coalesce(CAST(:kind AS text), kind),
       country = coalesce(CAST(:country AS text), country), description = coalesce(CAST(:description AS text), description),
       services_text = coalesce(CAST(:services AS text), services_text), locations_text = coalesce(CAST(:locations AS text), locations_text),
       parent_group = coalesce(CAST(:parent AS text), parent_group), airport_iata = coalesce(CAST(:airport AS char(3)), airport_iata),
       carrier_type = coalesce(CAST(:carrier_type AS text), carrier_type), updated_at = now()
 WHERE id = CAST(:id AS uuid) AND merged_into_id IS NULL RETURNING id"""
Q["org_verify"] = """
UPDATE organisations SET verified_at = now(), verification_basis = CAST(:basis AS text), updated_at = now()
 WHERE id = CAST(:id AS uuid) AND merged_into_id IS NULL RETURNING id"""
Q["org_contact_upsert"] = """
INSERT INTO organisation_contacts (organisation_id, kind, value, purpose, status, source_url, source_note, evidence_id, session_ref)
VALUES (CAST(:org AS uuid), CAST(:kind AS text), CAST(:value AS text), CAST(:purpose AS text), CAST(:status AS text), CAST(:url AS text),
        CAST(:note AS text), CAST(:evidence AS uuid), CAST(:session_ref AS text))
ON CONFLICT (organisation_id, kind, lower(value)) DO UPDATE
   SET status = CASE WHEN organisation_contacts.status = 'verified' THEN 'verified'
                     WHEN EXCLUDED.status = 'published' THEN 'published' ELSE organisation_contacts.status END,
       source_url = coalesce(EXCLUDED.source_url, organisation_contacts.source_url),
       evidence_id = coalesce(EXCLUDED.evidence_id, organisation_contacts.evidence_id), observed_at = now()
RETURNING id, (xmax = 0) AS inserted"""
Q["org_contact_status"] = """
UPDATE organisation_contacts SET status = CAST(:status AS text), verified_at = CASE WHEN CAST(:status AS text) = 'verified' THEN now() END,
       source_note = coalesce(CAST(:note AS text), source_note)
 WHERE id = CAST(:id AS uuid) AND organisation_id = CAST(:org AS uuid) RETURNING id"""
Q["org_evidence_add"] = """
INSERT INTO organisation_evidence (organisation_id, supports, source_kind, research_document_id, url, quote, note, supplied_import_id, session_ref)
VALUES (CAST(:org AS uuid), CAST(:supports AS text), CAST(:source_kind AS text), CAST(:rdoc AS uuid), CAST(:url AS text), CAST(:quote AS text),
        CAST(:note AS text), CAST(:import_id AS uuid), CAST(:session_ref AS text))
ON CONFLICT DO NOTHING RETURNING id"""
Q["org_evidence_find"] = """
SELECT id FROM organisation_evidence WHERE organisation_id = CAST(:org AS uuid) AND supports = CAST(:supports AS text)
   AND source_kind = CAST(:source_kind AS text) AND coalesce(research_document_id::text, '') = coalesce(CAST(:rdoc AS text), '')
   AND coalesce(url, '') = coalesce(CAST(:url AS text), '') AND md5(coalesce(quote, '')) = md5(coalesce(CAST(:quote AS text), ''))
   AND md5(coalesce(note, '')) = md5(coalesce(CAST(:note AS text), '')) LIMIT 1"""
Q["org_rel_upsert"] = """
INSERT INTO organisation_relationships (organisation_id, counterparty_id, counterparty_code, counterparty_label, relationship, territory_countries,
                                        airport_iata, status, basis, evidence_id, session_ref)
VALUES (CAST(:org AS uuid), CAST(:counterparty AS uuid), CAST(:code AS text), CAST(:label AS text), CAST(:relationship AS text),
        ARRAY(SELECT jsonb_array_elements_text(CAST(:territories AS jsonb)))::char(2)[], CAST(:airport AS char(3)), CAST(:status AS text),
        CAST(:basis AS text), CAST(:evidence AS uuid), CAST(:session_ref AS text))
ON CONFLICT (organisation_id, relationship, coalesce(counterparty_id::text, ''), coalesce(upper(counterparty_code), ''), coalesce(lower(counterparty_label), ''),
             coalesce(airport_iata, '')) DO UPDATE
   SET status = CASE WHEN organisation_relationships.status IN ('confirmed','lapsed','not_established') THEN organisation_relationships.status
                     WHEN EXCLUDED.status = 'sourced' THEN 'sourced' ELSE organisation_relationships.status END,
       basis = CASE WHEN EXCLUDED.status = 'sourced' AND organisation_relationships.status = 'supplied' THEN EXCLUDED.basis ELSE organisation_relationships.basis END,
       evidence_id = coalesce(EXCLUDED.evidence_id, organisation_relationships.evidence_id), observed_at = now()
RETURNING id, (xmax = 0) AS inserted"""
Q["org_rel_status"] = """
UPDATE organisation_relationships SET status = CAST(:status AS text), basis = CAST(:basis AS text), verified_at = now(), verified_by_label = CAST(:by AS text)
 WHERE id = CAST(:id AS uuid) AND organisation_id = CAST(:org AS uuid) RETURNING id"""
Q["org_relationships"] = """
SELECT r.id, r.counterparty_id, coalesce(c.canonical_name, r.counterparty_label) AS counterparty, r.counterparty_code, r.relationship,
       r.territory_countries::text[] AS territory_countries, r.airport_iata::text AS airport_iata, r.status, r.basis, r.observed_at, r.verified_at,
       r.verified_by_label, c.carrier_type AS counterparty_carrier_type, e.url AS evidence_url, e.quote AS evidence_quote, e.source_kind AS evidence_source
  FROM organisation_relationships r LEFT JOIN organisations c ON c.id = r.counterparty_id LEFT JOIN organisation_evidence e ON e.id = r.evidence_id
 WHERE r.organisation_id = CAST(:org AS uuid)
 ORDER BY CASE r.status WHEN 'confirmed' THEN 0 WHEN 'sourced' THEN 1 WHEN 'supplied' THEN 2 ELSE 3 END, r.relationship, coalesce(c.canonical_name, r.counterparty_label)"""
Q["org_represented_by"] = """
SELECT r.id, r.organisation_id AS agent_id, a.canonical_name AS agent, a.country::text AS agent_country, r.relationship, r.status, r.basis,
       r.airport_iata::text AS airport_iata, r.territory_countries::text[] AS territory_countries
  FROM organisation_relationships r JOIN organisations a ON a.id = r.organisation_id
 WHERE r.counterparty_id = CAST(:org AS uuid) ORDER BY a.canonical_name"""
Q["org_contacts"] = """
SELECT c.id, c.kind, c.value, c.purpose, c.status, c.source_url, c.source_note, c.observed_at, c.verified_at, e.quote AS evidence_quote
  FROM organisation_contacts c LEFT JOIN organisation_evidence e ON e.id = c.evidence_id
 WHERE c.organisation_id = CAST(:org AS uuid)
 ORDER BY CASE c.status WHEN 'verified' THEN 0 WHEN 'published' THEN 1 WHEN 'supplied' THEN 2 ELSE 3 END, c.value"""
Q["org_evidence"] = """
SELECT e.id, e.supports, e.source_kind, e.research_document_id, coalesce(e.url, rd.url) AS url, e.quote, e.note, e.observed_at, rd.title AS document_title,
       i.name AS supplied_import
  FROM organisation_evidence e LEFT JOIN research_documents rd ON rd.id = e.research_document_id LEFT JOIN supplied_imports i ON i.id = e.supplied_import_id
 WHERE e.organisation_id = CAST(:org AS uuid) ORDER BY e.observed_at, e.supports"""
Q["org_people"] = """
SELECT p.id, p.full_name, p.role_title, p.remit_countries::text[] AS remit_countries, p.linkedin_profile_url, p.origin, ps.state,
       (SELECT e.quote FROM person_evidence e WHERE e.person_id = p.id AND e.supports IN ('role','relevance') ORDER BY e.supports = 'role' DESC, e.observed_at LIMIT 1) AS quote,
       (SELECT coalesce(e.url, rd.url) FROM person_evidence e LEFT JOIN research_documents rd ON rd.id = e.research_document_id
         WHERE e.person_id = p.id AND e.supports IN ('role','relevance') ORDER BY e.supports = 'role' DESC, e.observed_at LIMIT 1) AS source_url,
       (SELECT count(*) FROM person_relationships r WHERE r.person_id = p.id AND r.status = 'active') AS relationships
  FROM people p LEFT JOIN person_state ps ON ps.person_id = p.id
 WHERE p.organisation_id = CAST(:org AS uuid) AND p.merged_into_id IS NULL ORDER BY p.full_name"""
Q["org_profile_get"] = """
SELECT o.id, o.canonical_name, o.kind, o.country::text AS country, o.website, o.newsroom_url, o.leadership_url, o.origin, o.description, o.services_text,
       o.locations_text, o.parent_group, o.airport_iata::text AS airport_iata, o.carrier_type, o.supplied_at, o.verified_at, o.verification_basis,
       o.last_researched_at, o.capability_areas, o.resolution_status, o.created_at, o.updated_at, a.iata_code,
       (SELECT coalesce(json_agg(al.alias ORDER BY al.alias), '[]'::json) FROM organisation_aliases al WHERE al.organisation_id = o.id) AS aliases,
       (SELECT count(*) FROM opportunities op WHERE op.merged_into_id IS NULL AND (op.organisation_id = o.id OR op.airline_id = o.id OR op.origin_organisation_id = o.id)) AS opportunities,
       (SELECT coalesce(json_agg(json_build_object('id', op.id, 'title', op.title, 'record_type', op.record_type, 'progress', op.progress, 'origin_interpretation', op.origin_interpretation)
                ORDER BY op.created_at DESC), '[]'::json)
          FROM opportunities op WHERE op.merged_into_id IS NULL AND (op.organisation_id = o.id OR op.airline_id = o.id OR op.origin_organisation_id = o.id)) AS opportunity_list,
       (SELECT coalesce(json_agg(json_build_object('discovery_id', d.id, 'brief', d.brief, 'purpose', d.purpose, 'started_at', d.started_at,
                                                   'relevance_score', x.relevance_score) ORDER BY d.started_at DESC), '[]'::json)
          FROM discovery_organisations x JOIN contact_discoveries d ON d.id = x.discovery_id WHERE x.organisation_id = o.id) AS discoveries
  FROM organisations o LEFT JOIN airlines a ON a.organisation_id = o.id WHERE o.id = CAST(:id AS uuid) AND o.merged_into_id IS NULL"""
Q["companies_list"] = """
SELECT o.id, o.canonical_name, o.kind, o.country::text AS country, o.website, o.origin, o.airport_iata::text AS airport_iata, o.carrier_type,
       o.supplied_at, o.verified_at, o.last_researched_at, o.capability_areas, o.updated_at, a.iata_code,
       (SELECT count(*) FROM organisation_contacts c WHERE c.organisation_id = o.id AND c.kind = 'email') AS emails,
       (SELECT count(*) FROM organisation_contacts c WHERE c.organisation_id = o.id AND c.status IN ('published','verified')) AS emails_current,
       (SELECT count(*) FROM organisation_relationships r WHERE r.organisation_id = o.id AND r.status <> 'not_established') AS relationships,
       (SELECT count(*) FROM organisation_relationships r WHERE r.organisation_id = o.id AND r.status IN ('sourced','confirmed')) AS relationships_current,
       (SELECT count(*) FROM organisation_relationships r WHERE r.counterparty_id = o.id AND r.status <> 'not_established') AS represented_by,
       (SELECT count(*) FROM people p WHERE p.organisation_id = o.id AND p.merged_into_id IS NULL) AS people,
       (SELECT count(*) FROM organisation_evidence e WHERE e.organisation_id = o.id) AS evidence,
       (SELECT count(*) FROM opportunities op WHERE op.merged_into_id IS NULL AND (op.organisation_id = o.id OR op.airline_id = o.id OR op.origin_organisation_id = o.id)) AS opportunities,
       (SELECT max(x.relevance_score) FROM discovery_organisations x WHERE x.organisation_id = o.id) AS best_relevance,
       count(*) OVER () AS total
  FROM organisations o LEFT JOIN airlines a ON a.organisation_id = o.id
 WHERE o.merged_into_id IS NULL
   AND (CAST(:kind AS text) IS NULL OR o.kind = CAST(:kind AS text))
   AND (CAST(:country AS text) IS NULL OR o.country = CAST(:country AS text))
   AND (CAST(:airport AS text) IS NULL OR o.airport_iata = CAST(:airport AS char(3)))
   AND (CAST(:origin AS text) IS NULL OR o.origin = CAST(:origin AS text))
   AND (CAST(:carrier_type AS text) IS NULL OR o.carrier_type = CAST(:carrier_type AS text))
   AND (CAST(:state AS text) IS NULL
        OR (CAST(:state AS text) = 'verified' AND o.verified_at IS NOT NULL)
        OR (CAST(:state AS text) = 'awaiting_verification' AND o.verified_at IS NULL AND o.supplied_at IS NOT NULL)
        OR (CAST(:state AS text) = 'researched' AND o.last_researched_at IS NOT NULL)
        OR (CAST(:state AS text) = 'unverified' AND o.verified_at IS NULL))
   AND (CAST(:discovery AS uuid) IS NULL OR EXISTS (SELECT 1 FROM discovery_organisations x WHERE x.organisation_id = o.id AND x.discovery_id = CAST(:discovery AS uuid)))
   AND (CAST(:q AS text) IS NULL OR o.canonical_name ILIKE '%' || CAST(:q AS text) || '%'
        OR EXISTS (SELECT 1 FROM organisation_aliases al WHERE al.organisation_id = o.id AND al.alias ILIKE '%' || CAST(:q AS text) || '%')
        OR EXISTS (SELECT 1 FROM organisation_relationships r WHERE r.organisation_id = o.id AND (r.counterparty_label ILIKE '%' || CAST(:q AS text) || '%' OR r.counterparty_code = upper(CAST(:q AS text)))))
 ORDER BY CASE WHEN CAST(:sort AS text) = 'relevance' THEN -(SELECT coalesce(max(x.relevance_score), 0) FROM discovery_organisations x WHERE x.organisation_id = o.id) END,
          CASE WHEN CAST(:sort AS text) = 'recent' THEN o.updated_at END DESC NULLS LAST, o.canonical_name
 LIMIT CAST(:limit AS int) OFFSET CAST(:offset AS int)"""
Q["disc_org_link"] = """
INSERT INTO discovery_organisations (discovery_id, organisation_id, new_record) VALUES (CAST(:disc AS uuid), CAST(:org AS uuid), CAST(:new AS boolean))
ON CONFLICT (discovery_id, organisation_id) DO NOTHING"""
Q["disc_org_relevance"] = """
UPDATE discovery_organisations SET relevance_score = CAST(:score AS int), relevance = CAST(:relevance AS jsonb)
 WHERE discovery_id = CAST(:disc AS uuid) AND organisation_id = CAST(:org AS uuid)"""
Q["disc_orgs"] = """
SELECT x.organisation_id, x.relevance_score, x.relevance, x.new_record, o.canonical_name, o.kind, o.country::text AS country, o.website, o.origin,
       o.airport_iata::text AS airport_iata, o.carrier_type, o.verified_at, o.supplied_at, o.services_text, o.locations_text, o.parent_group,
       (SELECT coalesce(json_agg(json_build_object('value', c.value, 'status', c.status) ORDER BY c.value), '[]'::json) FROM organisation_contacts c
         WHERE c.organisation_id = o.id AND c.kind = 'email') AS emails,
       (SELECT coalesce(json_agg(json_build_object('counterparty', coalesce(c2.canonical_name, r.counterparty_label), 'code', r.counterparty_code,
                                                   'relationship', r.relationship, 'status', r.status) ORDER BY r.observed_at), '[]'::json)
          FROM organisation_relationships r LEFT JOIN organisations c2 ON c2.id = r.counterparty_id WHERE r.organisation_id = o.id) AS relationships,
       (SELECT count(*) FROM people p WHERE p.organisation_id = o.id AND p.merged_into_id IS NULL) AS people,
       (SELECT count(*) FROM organisation_evidence e WHERE e.organisation_id = o.id) AS evidence,
       (SELECT e.quote FROM organisation_evidence e WHERE e.organisation_id = o.id AND e.source_kind <> 'supplied' ORDER BY e.supports = 'identity' DESC, e.observed_at LIMIT 1) AS quote,
       (SELECT coalesce(e.url, rd.url) FROM organisation_evidence e LEFT JOIN research_documents rd ON rd.id = e.research_document_id
         WHERE e.organisation_id = o.id AND e.source_kind <> 'supplied' ORDER BY e.supports = 'identity' DESC, e.observed_at LIMIT 1) AS source_url
  FROM discovery_organisations x JOIN organisations o ON o.id = x.organisation_id
 WHERE x.discovery_id = CAST(:id AS uuid) ORDER BY x.relevance_score DESC, o.canonical_name"""
Q["org_by_code"] = """
SELECT a.organisation_id AS id FROM airlines a JOIN organisations o ON o.id = a.organisation_id WHERE a.iata_code = CAST(:code AS text) AND o.merged_into_id IS NULL LIMIT 1"""
Q["supplied_import_insert"] = """
INSERT INTO supplied_imports (name, filename, sha256, airport_iata, country, notes, imported_by, session_ref)
VALUES (CAST(:name AS text), CAST(:filename AS text), CAST(:sha AS text), CAST(:airport AS char(3)), CAST(:country AS char(2)), CAST(:notes AS text),
        CAST(:by AS text), CAST(:session_ref AS text)) RETURNING id"""
Q["supplied_import_by_sha"] = "SELECT id, name, imported_at FROM supplied_imports WHERE sha256 = CAST(:sha AS text) ORDER BY imported_at LIMIT 1"
Q["supplied_import_finish"] = """
UPDATE supplied_imports SET rows_total = CAST(:rows AS int), organisations = CAST(:orgs AS int), relationships = CAST(:rels AS int), contacts = CAST(:contacts AS int)
 WHERE id = CAST(:id AS uuid)"""
Q["supplied_row_insert"] = """
INSERT INTO supplied_rows (import_id, sheet, row_number, raw, organisation_id, note)
VALUES (CAST(:import_id AS uuid), CAST(:sheet AS text), CAST(:row AS int), CAST(:raw AS jsonb), CAST(:org AS uuid), CAST(:note AS text)) RETURNING id"""
Q["supplied_imports_list"] = """
SELECT i.*, i.airport_iata::text AS airport_iata, i.country::text AS country,
       (SELECT count(*) FROM supplied_rows r WHERE r.import_id = i.id AND r.organisation_id IS NOT NULL) AS rows_linked,
       (SELECT count(DISTINCT r.organisation_id) FROM supplied_rows r JOIN organisations o ON o.id = r.organisation_id WHERE r.import_id = i.id AND o.verified_at IS NOT NULL) AS organisations_verified
  FROM supplied_imports i ORDER BY i.imported_at DESC"""
Q["supplied_import_get"] = "SELECT i.*, i.airport_iata::text AS airport_iata, i.country::text AS country FROM supplied_imports i WHERE i.id = CAST(:id AS uuid)"
Q["supplied_rows_for"] = """
SELECT r.id, r.sheet, r.row_number, r.raw, r.organisation_id, o.canonical_name AS organisation, o.verified_at, r.note
  FROM supplied_rows r LEFT JOIN organisations o ON o.id = r.organisation_id WHERE r.import_id = CAST(:id AS uuid) ORDER BY r.sheet, r.row_number"""
Q["opportunity_from_company"] = """
INSERT INTO opportunities (module, dedup_key, title, organisation_id, origin_organisation_id, origin_interpretation, record_type, progress, owner_label)
VALUES (CAST(:module AS text), 'company:' || CAST(:org AS text) || ':' || CAST(:module AS text) || ':' || md5(CAST(:title AS text)), CAST(:title AS text),
        CAST(:org AS uuid), CAST(:org AS uuid), CAST(:interpretation AS text), 'commercial', 'new', CAST(:by AS text))
ON CONFLICT (module, dedup_key) DO UPDATE SET updated_at = now() RETURNING id, (xmax = 0) AS inserted"""
Q["opportunity_geo_add"] = """
INSERT INTO opportunity_geography (opportunity_id, country_code, role, support) VALUES (CAST(:opp AS uuid), CAST(:country AS char(2)), 'delivery', 'supported')
ON CONFLICT DO NOTHING"""
Q["cp_company_summary"] = """
SELECT (SELECT count(*) FROM organisations o WHERE o.merged_into_id IS NULL AND o.origin IN ('discovery','research')) AS researched,
       (SELECT count(*) FROM organisations o WHERE o.merged_into_id IS NULL AND o.origin = 'supplied' AND o.verified_at IS NULL) AS awaiting_verification,
       (SELECT count(*) FROM organisations o WHERE o.merged_into_id IS NULL AND o.verified_at IS NOT NULL) AS verified,
       (SELECT count(*) FROM organisations o WHERE o.merged_into_id IS NULL AND o.last_researched_at > now() - interval '30 days') AS researched_30d,
       (SELECT count(*) FROM organisation_relationships r WHERE r.status IN ('sourced','confirmed')) AS representation_sourced,
       (SELECT count(*) FROM organisation_relationships r WHERE r.status = 'supplied') AS representation_supplied,
       (SELECT count(*) FROM people p WHERE p.merged_into_id IS NULL AND p.origin IN ('discovery','research','document')) AS people_identified,
       (SELECT count(*) FROM people p LEFT JOIN person_state ps ON ps.person_id = p.id WHERE p.merged_into_id IS NULL AND coalesce(ps.state,'research_candidate') = 'research_candidate') AS people_candidates,
       (SELECT count(*) FROM people p JOIN person_state ps ON ps.person_id = p.id WHERE p.merged_into_id IS NULL AND ps.state = 'confirmed') AS people_confirmed,
       (SELECT count(*) FROM contact_discoveries d WHERE d.started_at > now() - interval '30 days') AS discoveries_30d"""
Q["cp_companies_by_country"] = """
SELECT o.country::text AS country, count(*) AS companies, count(*) FILTER (WHERE o.verified_at IS NOT NULL) AS verified,
       count(*) FILTER (WHERE o.origin = 'supplied' AND o.verified_at IS NULL) AS awaiting
  FROM organisations o WHERE o.merged_into_id IS NULL AND o.country IS NOT NULL AND o.origin IN ('discovery','research','supplied')
 GROUP BY o.country ORDER BY companies DESC, o.country LIMIT 12"""
Q["cp_market_signals"] = """
SELECT s.id, s.title, s.classification, s.first_published_at, s.module,
       (SELECT g.country_code::text FROM signal_geography g WHERE g.signal_id = s.id ORDER BY g.support = 'supported' DESC LIMIT 1) AS country
  FROM signals s WHERE s.merged_into_id IS NULL AND s.classification IN ('market_signal','freight_candidate')
 ORDER BY coalesce(s.first_published_at, s.created_at) DESC LIMIT CAST(:limit AS int)"""
Q["cp_market_counts"] = """
SELECT count(*) FILTER (WHERE s.classification = 'market_signal') AS market_signals,
       count(*) FILTER (WHERE s.classification = 'market_signal' AND coalesce(s.first_published_at, s.created_at) > now() - interval '30 days') AS market_signals_30d,
       count(*) FILTER (WHERE s.classification = 'freight_candidate') AS freight_candidates
  FROM signals s WHERE s.merged_into_id IS NULL"""
