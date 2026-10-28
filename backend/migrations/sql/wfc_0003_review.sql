-- VECTA Connect | ATLAS | DYNAMIC MARKET INTELLIGENCE
-- WFC lineage, revision wfc_0003 (full build review and amendments, 26 October 2026).
--
-- Applied on top of wfc_0002 by alembic/versions/wfc_0003_review.py and directly by the
-- PostgreSQL test harness. Additive only: no existing column changes meaning except that
-- tender deadline_utc columns now hold an exact instant ONLY (NULL when the source states a
-- date or a time without a zone); the stated deadline is kept in deadline_info.

UPDATE schema_meta SET value = 'wfc_0003' WHERE key = 'revision';

-- =====================================================================
-- 1. DEADLINE PRECISION (review §1): the stated deadline as stated
-- =====================================================================
-- deadline_info: domain.deadlines.StatedDeadline as JSON (precision date | local_time | instant,
-- stated day, local time, stated zone, exact instant if any, earliest/latest bounds, assumptions).
ALTER TABLE claims        ADD COLUMN deadline_info jsonb;
ALTER TABLE opportunities ADD COLUMN deadline_info jsonb,
                          ADD COLUMN deadline_earliest_utc timestamptz,   -- internal planning cutoff (labelled)
                          ADD COLUMN deadline_latest_utc timestamptz;     -- expiry only after this
CREATE INDEX ix_opportunities_deadline_latest ON opportunities (deadline_latest_utc) WHERE merged_into_id IS NULL;
-- Existing rows: their deadline_utc was always an instant; carry it into both bounds.
UPDATE opportunities SET deadline_earliest_utc = deadline_utc, deadline_latest_utc = deadline_utc WHERE deadline_utc IS NOT NULL;

-- =====================================================================
-- 2. TRUTHFUL RUN COMPLETION (review §2): a source with any unprocessed target is partial
-- =====================================================================
ALTER TABLE discovery_run_sources DROP CONSTRAINT discovery_run_sources_status_check;
ALTER TABLE discovery_run_sources ADD CONSTRAINT discovery_run_sources_status_check
    CHECK (status IN ('pending','succeeded','partial','failed','skipped','cancelled'));
ALTER TABLE ingestion_runs DROP CONSTRAINT ingestion_runs_status_check;
ALTER TABLE ingestion_runs ADD CONSTRAINT ingestion_runs_status_check CHECK (status IN ('running','succeeded','partial','failed','cancelled'));
-- Every target that was not fully processed: [{url, reason: retrieval_failed | language_not_permitted |
-- extraction_not_run | extraction_rejected | not_fetched_limit | date_unknown_excluded, detail}]
ALTER TABLE discovery_run_sources ADD COLUMN issues jsonb NOT NULL DEFAULT '[]';

-- =====================================================================
-- 3. CUMULATIVE PER-RUN AI BUDGET (review §2): one ceiling per discovery run, shared by its retries
-- =====================================================================
-- budget_root_id: the run whose ceiling this run spends against (a retry points at its original run).
-- budget_cap_usd: the approved upper bound for the whole run family = the plan's upper-bound estimate,
-- never more than the monthly period's per_run_cap_usd at the time the run was planned.
ALTER TABLE discovery_runs ADD COLUMN budget_root_id uuid REFERENCES discovery_runs(id),
                           ADD COLUMN budget_cap_usd numeric(12,4);
ALTER TABLE budget_reservations ADD COLUMN run_id uuid REFERENCES discovery_runs(id);
CREATE INDEX ix_budget_reservations_run ON budget_reservations (run_id) WHERE run_id IS NOT NULL;

-- Atomic: the root run row is locked, so concurrent workers, retries and manual re-extraction of the same
-- run family serialise here. The run total counts open reservations at their reserved amount and settled ones
-- at their actual cost, across all months. The monthly cap, per-call cap and kill switch are then checked by
-- reserve_budget (wfc_0001) in the same transaction.
CREATE FUNCTION reserve_run_budget(p_job uuid, p_run uuid, p_amount numeric, p_at timestamptz DEFAULT now())
RETURNS uuid LANGUAGE plpgsql AS $$
DECLARE
    v_root uuid;
    v_cap numeric;
    v_committed numeric;
    v_id uuid;
BEGIN
    SELECT coalesce(budget_root_id, id) INTO v_root FROM discovery_runs WHERE id = p_run;
    IF v_root IS NULL THEN
        RETURN NULL;
    END IF;
    SELECT budget_cap_usd INTO v_cap FROM discovery_runs WHERE id = v_root FOR UPDATE;
    IF v_cap IS NULL THEN
        RETURN NULL;                       -- a run without an approved bound cannot spend
    END IF;
    SELECT coalesce(sum(CASE WHEN r.status = 'reserved' THEN r.reserved_usd
                             WHEN r.status = 'settled'  THEN greatest(r.actual_usd, 0) ELSE 0 END), 0)
      INTO v_committed
      FROM budget_reservations r JOIN discovery_runs d ON d.id = r.run_id
     WHERE coalesce(d.budget_root_id, d.id) = v_root;
    IF v_committed + p_amount > v_cap THEN
        RETURN NULL;
    END IF;
    v_id := reserve_budget(p_job, p_amount, p_at);
    IF v_id IS NOT NULL THEN
        UPDATE budget_reservations SET run_id = p_run WHERE id = v_id;
    END IF;
    RETURN v_id;
END $$;

-- =====================================================================
-- 4. PUBLICATION DATES AND COVERAGE (review §2)
-- =====================================================================
-- Where a document's publication date came from: 'page' (the article's own metadata), 'feed' (the RSS/Atom
-- item that linked it), or NULL (unknown).
ALTER TABLE source_documents ADD COLUMN published_at_source text CHECK (published_at_source IN ('page','feed'));
UPDATE source_documents SET published_at_source = 'page' WHERE published_at IS NOT NULL;
-- How a date-filtered search treats documents with no known publication date:
-- 'include_unknown' (default): processed and shown, each flagged "date unknown, not verified within the period";
-- 'strict': not processed, and listed on the run as excluded for an unknown date.
ALTER TABLE discovery_searches ADD COLUMN date_filter text NOT NULL DEFAULT 'include_unknown'
    CHECK (date_filter IN ('include_unknown','strict'));
-- Resumable coverage: per source, where the next run continues in the country list when a run hits the
-- per-run country limit ({source_id: {"offset": n, "total": m, "updated_at": ...}}).
ALTER TABLE discovery_searches ADD COLUMN coverage_cursor jsonb NOT NULL DEFAULT '{}';

-- =====================================================================
-- 5. PARTNER FIT: inputs kept so a fit can be invalidated and reassessed (review §2)
-- =====================================================================
-- A fit assessment records what it was based on: the partner organisation, the coverage gaps asked about, and a
-- basis snapshot (each partner claim with its status at the time; which gaps WFC's own active agreements covered).
-- When the current evidence or agreements no longer match the snapshot, the fit is shown as invalidated, with the
-- changes listed, and is reassessed (by a reviewer or the worker's periodic tick).
ALTER TABLE fit_assessments ADD COLUMN organisation_id uuid REFERENCES organisations(id),
                            ADD COLUMN gaps jsonb NOT NULL DEFAULT '[]',
                            ADD COLUMN basis jsonb NOT NULL DEFAULT '{}',
                            ADD COLUMN trigger text NOT NULL DEFAULT 'manual' CHECK (trigger IN ('manual','evidence_changed','agreements_changed','periodic')),
                            ADD COLUMN supersedes_id uuid REFERENCES fit_assessments(id);

-- Runs still queued or running when this migration is applied were approved under the old per-call rule. Their
-- ceiling is what that approval covered: the run's estimate, never more than this month's per-run cap. Finished
-- runs get no ceiling; re-extracting their documents needs an explicit, audited approval (review_service).
UPDATE discovery_runs r SET budget_cap_usd = LEAST(coalesce(r.estimated_cost_usd, 0),
       coalesce((SELECT per_run_cap_usd FROM budget_periods WHERE period_month = date_trunc('month', now() AT TIME ZONE 'UTC')::date), 0))
 WHERE r.status IN ('queued','running') AND r.budget_cap_usd IS NULL AND r.budget_root_id IS NULL;
