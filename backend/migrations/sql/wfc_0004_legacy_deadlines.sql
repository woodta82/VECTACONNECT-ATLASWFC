-- VECTA Connect | ATLAS | DYNAMIC MARKET INTELLIGENCE — wfc_0004, part 2 (amendments of 26 Oct 2026, item 6).
-- Idempotent: only rows with a stored instant and no stated-precision record (deadline_info IS NULL) are touched.
-- 6. MIGRATED DEADLINES. Before wfc_0003, a deadline was always stored as an instant: a date-only notice became
-- 00:00 UTC and an extractor's zone guess became fact. wfc_0003 carried those values forward unchanged. Here, every
-- deadline without a stated-precision record is immediately taken OUT of "exact" status:
--   * 00:00 UTC (whatever zone was recorded), or midnight in the recorded zone -> date only, on that date
--   * any other stored time                   -> a local time; the recorded zone is only an ASSUMPTION
-- No legacy value stays an exact instant.
-- and a one-off job ('deadline_revalidation') re-reads each claim's own source quote with the current rules and
-- replaces the record with what the evidence actually states. Opportunities follow their claims.
CREATE OR REPLACE FUNCTION pg_temp.legacy_deadline(p_utc timestamptz, p_tz text) RETURNS jsonb LANGUAGE plpgsql AS $$
-- NO legacy value is kept as an exact instant: earlier versions could have inferred the time (00:00 for a date-only
-- notice) and the zone (an extractor's guess). Until the evidence is re-read:
--   * 00:00 in the recorded zone (or UTC when none is valid) -> date only, on that LOCAL date;
--   * any other time -> a local time with the recorded zone kept as an ASSUMPTION (not a source fact).
DECLARE
  v_zone text := NULL;
  v_local timestamp;
  v_day date;
BEGIN
  IF p_tz IS NOT NULL THEN
    BEGIN
      v_local := p_utc AT TIME ZONE p_tz;
      v_zone := p_tz;
    EXCEPTION WHEN others THEN
      v_zone := NULL;
    END;
  END IF;
  IF v_zone IS NULL OR (p_utc AT TIME ZONE 'UTC')::time = '00:00'::time THEN
    -- exactly 00:00 UTC is the old "date only" inference whatever zone was recorded with it: use the UTC date
    v_local := p_utc AT TIME ZONE 'UTC';
  END IF;
  v_day := v_local::date;
  IF v_local::time = '00:00'::time THEN
    RETURN jsonb_build_object('precision','date','day',v_day,'local_time',NULL,'zone',NULL,'offset_minutes',NULL,'exact_utc',NULL,
      'earliest_utc', to_char(v_day::timestamp - interval '14 hours', 'YYYY-MM-DD"T"HH24:MI:SS"+00:00"'),
      'latest_utc',   to_char(v_day::timestamp + interval '36 hours', 'YYYY-MM-DD"T"HH24:MI:SS"+00:00"'),
      'assumed_zone',NULL,'assumed_utc',NULL,'migrated',true,'revalidated',false,'verified',false,'recorded_zone',p_tz,
      'notes', jsonb_build_array('migrated: an earlier version stored this deadline as midnight (' || coalesce(v_zone,'UTC') ||
                                 '); the time was not stated, so only the date is kept until the evidence is re-checked'));
  END IF;
  RETURN jsonb_build_object('precision','local_time','day',v_day,'local_time',to_char(v_local,'HH24:MI'),'zone',NULL,'offset_minutes',NULL,
    'exact_utc',NULL,
    'earliest_utc', to_char(v_day::timestamp + v_local::time - interval '14 hours', 'YYYY-MM-DD"T"HH24:MI:SS"+00:00"'),
    'latest_utc',   to_char(v_day::timestamp + v_local::time + interval '12 hours', 'YYYY-MM-DD"T"HH24:MI:SS"+00:00"'),
    'assumed_zone', coalesce(v_zone,'UTC'), 'assumed_utc', to_char(p_utc AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS"+00:00"'),
    'migrated',true,'revalidated',false,'verified',false,'recorded_zone',p_tz,
    'notes', jsonb_build_array('migrated: stored by an earlier version as ' || to_char(v_local,'HH24:MI') || ' ' || coalesce(v_zone,'UTC') ||
                               '; the zone may have been inferred, so it is shown as an assumption until the evidence is re-checked'));
END $$;

UPDATE claims SET deadline_info = pg_temp.legacy_deadline(deadline_utc, deadline_source_tz), deadline_utc = NULL, deadline_source_tz = NULL
 WHERE deadline_utc IS NOT NULL AND deadline_info IS NULL;
UPDATE opportunities SET deadline_info = pg_temp.legacy_deadline(deadline_utc, deadline_source_tz),
       deadline_earliest_utc = (pg_temp.legacy_deadline(deadline_utc, deadline_source_tz)->>'earliest_utc')::timestamptz,
       deadline_latest_utc   = (pg_temp.legacy_deadline(deadline_utc, deadline_source_tz)->>'latest_utc')::timestamptz,
       deadline_utc = NULL, deadline_source_tz = NULL
 WHERE deadline_utc IS NOT NULL AND deadline_info IS NULL;


-- Queued only when there is something to revalidate (a fresh install has nothing).
INSERT INTO jobs (job_type, execution_key, payload)
SELECT 'deadline_revalidation', 'deadline-revalidation:wfc_0004', '{}'::jsonb
 WHERE EXISTS (SELECT 1 FROM claims WHERE coalesce((deadline_info->>'migrated')::boolean, false))
    OR EXISTS (SELECT 1 FROM opportunities WHERE coalesce((deadline_info->>'migrated')::boolean, false))
ON CONFLICT (execution_key) DO NOTHING;
