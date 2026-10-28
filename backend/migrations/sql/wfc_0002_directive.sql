-- VECTA Connect | ATLAS | DYNAMIC MARKET INTELLIGENCE
-- WFC lineage, revision wfc_0002 (completion directive, 26 October 2026).
--
-- Applied on top of wfc_0001 by alembic/versions/wfc_0002_directive.py and
-- directly by the PostgreSQL test harness. Adds: geography reference data,
-- source management, country discovery searches and runs, per-field claim
-- validation, tender identity and merge review, extraction review queue,
-- opportunity scope (station, delivery date, credentials), approval basis,
-- master-data and remaining import datasets, import file binding.
-- The country/region seed at the end is generated from
-- app/reference/geography.py (tools/gen_geography_sql.py).

UPDATE schema_meta SET value = 'wfc_0002' WHERE key = 'revision';

-- =====================================================================
-- 1. GEOGRAPHY
-- =====================================================================
CREATE TABLE countries (
    code      char(2) PRIMARY KEY CHECK (code ~ '^[A-Z]{2}$'),
    name      text NOT NULL,
    un_region text,
    un_subregion text
);

CREATE TABLE regions (
    code text PRIMARY KEY CHECK (code ~ '^[A-Z0-9_]{2,40}$'),
    name text NOT NULL,
    kind text NOT NULL CHECK (kind IN ('un_region','un_subregion','economic','custom'))
);

CREATE TABLE region_countries (
    region_code  text NOT NULL REFERENCES regions(code) ON DELETE CASCADE,
    country_code char(2) NOT NULL REFERENCES countries(code),
    PRIMARY KEY (region_code, country_code)
);

ALTER TABLE territories ADD COLUMN country_code char(2) REFERENCES countries(code);
ALTER TABLE organisations ADD COLUMN resolution_status text NOT NULL DEFAULT 'confirmed'
    CHECK (resolution_status IN ('confirmed','auto_created'));

-- =====================================================================
-- 2. SOURCE MANAGEMENT
-- =====================================================================
ALTER TABLE sources
    ADD COLUMN source_type text NOT NULL DEFAULT 'web_page'
        CHECK (source_type IN ('web_page','listing','rss','search_template','file_import')),
    ADD COLUMN country_coverage char(2)[] NOT NULL DEFAULT '{}',   -- ISO codes; empty + not global = coverage unknown
    ADD COLUMN global_coverage boolean NOT NULL DEFAULT false,
    ADD COLUMN language text,                                     -- BCP 47 primary language of the source
    ADD COLUMN local_language_permitted boolean NOT NULL DEFAULT true,
    ADD COLUMN modules text[] NOT NULL DEFAULT '{}',             -- capability areas; empty = all
    ADD COLUMN refresh_minutes integer CHECK (refresh_minutes IS NULL OR refresh_minutes >= 15),
    ADD COLUMN query_template text,                               -- search_template only: {keywords} {country} {country_name}
    ADD COLUMN max_items integer NOT NULL DEFAULT 20 CHECK (max_items BETWEEN 1 AND 200),
    ADD COLUMN notes text,
    ADD COLUMN deleted_at timestamptz;
UPDATE sources SET source_type = 'file_import' WHERE name LIKE 'Import: %';
CREATE UNIQUE INDEX ux_sources_name ON sources (lower(name)) WHERE deleted_at IS NULL;

ALTER TABLE ingestion_runs ADD COLUMN discovery_run_id uuid;
ALTER TABLE ingestion_runs ADD COLUMN error text;

-- =====================================================================
-- 3. DOCUMENTS, EXTRACTION, CLAIM FIELDS
-- =====================================================================
ALTER TABLE source_documents
    ADD COLUMN language text,
    ADD COLUMN body_text text,                       -- readable text; stored only when retention is permitted
    ADD COLUMN summary_en text,
    ADD COLUMN summary_is_translation boolean NOT NULL DEFAULT false,
    ADD COLUMN extraction_status text NOT NULL DEFAULT 'pending'
        CHECK (extraction_status IN ('pending','extracted','no_claims','partial','failed','not_connected','budget_refused','manual')),
    ADD COLUMN extraction_detail text,
    ADD COLUMN extracted_at timestamptz;

ALTER TABLE claims DROP CONSTRAINT claims_claim_type_check;
ALTER TABLE claims ADD CONSTRAINT claims_claim_type_check CHECK (claim_type IN (
    'route_launch','route_suspension','gssa_tender','tender_deadline','tender_scope','tender_status','representation_change',
    'tcm_signal','capacity_statement','partnership','eligibility','service_tender','other'));
ALTER TABLE claims
    ADD COLUMN signal_key text,
    ADD COLUMN tender_ref text,
    ADD COLUMN procurement_cycle text,
    ADD COLUMN subject_label text,
    ADD COLUMN review_status text NOT NULL DEFAULT 'proposed'
        CHECK (review_status IN ('proposed','confirmed','corrected','rejected')),
    ADD COLUMN reviewed_at timestamptz,
    ADD COLUMN review_note text;
ALTER TABLE claim_evidence ADD COLUMN excluded_at timestamptz;   -- set when a reviewer rejects the claim from this document

-- One row per material field per supporting document. A field is a fact only
-- when its own quote, found verbatim in the document, states the value.
CREATE TABLE claim_fields (
    id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    claim_id           uuid NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
    source_document_id uuid NOT NULL REFERENCES source_documents(id),
    field              text NOT NULL CHECK (field IN ('organisation','airline','opportunity_type','country','issuer_country',
                           'contract_territory','origin','destination','tender_ref','procurement_cycle','status','deadline',
                           'eligibility','published_value','service')),
    value              text NOT NULL,                 -- as stated
    normalised         text NOT NULL,                 -- comparable form (ISO code, UTC instant, upper-case ref ...)
    quote              text,
    support            text NOT NULL CHECK (support IN ('supported','unsupported','not_applicable')),
    reason             text NOT NULL,
    assessed_by        text NOT NULL CHECK (assessed_by IN ('rule','ai_proposed','human')),
    superseded_at      timestamptz,
    created_at         timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX ux_claim_fields_live ON claim_fields (claim_id, source_document_id, field, normalised) WHERE superseded_at IS NULL;
CREATE INDEX ix_claim_fields_claim ON claim_fields (claim_id);

-- Extracted claims that failed validation, and whole outputs quarantined, wait here for a reviewer.
CREATE TABLE extraction_rejections (
    id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_document_id uuid NOT NULL REFERENCES source_documents(id) ON DELETE CASCADE,
    ai_call_id         uuid REFERENCES ai_calls(id),
    claim_index        integer,
    reason             text NOT NULL,
    raw                jsonb NOT NULL,
    status             text NOT NULL DEFAULT 'open' CHECK (status IN ('open','resolved','dismissed')),
    resolution_note    text,
    created_at         timestamptz NOT NULL DEFAULT now(),
    resolved_at        timestamptz
);
CREATE INDEX ix_extraction_rejections_open ON extraction_rejections (created_at) WHERE status = 'open';

-- =====================================================================
-- 4. SIGNALS: identity, geography, tender state, merge review
-- =====================================================================
ALTER TABLE signals
    ADD COLUMN identity_basis text NOT NULL DEFAULT 'legacy'
        CHECK (identity_basis IN ('legacy','tender_ref','procurement_cycle','announcement','route','subject')),
    ADD COLUMN tender_ref text,
    ADD COLUMN procurement_cycle text,
    ADD COLUMN subject_organisation_id uuid REFERENCES organisations(id),
    ADD COLUMN tender_state jsonb,
    ADD COLUMN related_modules text[] NOT NULL DEFAULT '{}',
    ADD COLUMN first_published_at timestamptz,
    ADD COLUMN last_evidence_at timestamptz,
    ADD COLUMN merged_into_id uuid REFERENCES signals(id);

CREATE TABLE signal_geography (
    signal_id    uuid NOT NULL REFERENCES signals(id) ON DELETE CASCADE,
    country_code char(2) NOT NULL REFERENCES countries(code),
    role         text NOT NULL CHECK (role IN ('delivery','issuer','contract_territory','origin','destination')),
    support      text NOT NULL CHECK (support IN ('supported','unverified')),
    PRIMARY KEY (signal_id, country_code, role)
);
CREATE INDEX ix_signal_geography_country ON signal_geography (country_code);

CREATE TABLE merge_candidates (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_type   text NOT NULL CHECK (entity_type IN ('signal','organisation')),
    left_id       uuid NOT NULL,
    right_id      uuid NOT NULL,
    reason        text NOT NULL,
    score         numeric(5,4),
    status        text NOT NULL DEFAULT 'open' CHECK (status IN ('open','merged','kept_separate')),
    decision_note text,
    created_at    timestamptz NOT NULL DEFAULT now(),
    decided_at    timestamptz,
    CHECK (left_id <> right_id),
    UNIQUE (entity_type, left_id, right_id)
);

-- =====================================================================
-- 5. OPPORTUNITIES: scope, geography, approval basis, merge
-- =====================================================================
ALTER TABLE opportunities
    ADD COLUMN station_airport_id uuid REFERENCES airports(id),
    ADD COLUMN delivery_start date,
    ADD COLUMN required_credentials text[] NOT NULL DEFAULT '{}',
    ADD COLUMN approval_basis jsonb,          -- scope + evidence fingerprint the approval was given on
    ADD COLUMN merged_into_id uuid REFERENCES opportunities(id),
    ADD COLUMN origin_ref text,               -- internal record that produced a module opportunity (e.g. agreement gap)
    ADD COLUMN tender_status text,            -- resolved from authoritative evidence: open/revised/cancelled/awarded/expired/unknown
    ADD COLUMN notes text,
    ADD COLUMN module_facts jsonb NOT NULL DEFAULT '{}'::jsonb;  -- facts from the internal records a module opportunity came from

CREATE TABLE opportunity_geography (
    opportunity_id uuid NOT NULL REFERENCES opportunities(id) ON DELETE CASCADE,
    country_code   char(2) NOT NULL REFERENCES countries(code),
    role           text NOT NULL CHECK (role IN ('delivery','issuer','contract_territory','origin','destination')),
    support        text NOT NULL CHECK (support IN ('supported','unverified','internal_record')),
    PRIMARY KEY (opportunity_id, country_code, role)
);
CREATE INDEX ix_opportunity_geography_country ON opportunity_geography (country_code);

ALTER TABLE opportunity_status_history DROP CONSTRAINT opportunity_status_history_field_check;
ALTER TABLE opportunity_status_history ADD CONSTRAINT opportunity_status_history_field_check
    CHECK (field IN ('commercial_stage','qualification_status','deadline','tender_status','scope','owner','merge'));

-- Credentials a service always requires (e.g. a dangerous-goods licence for handling).
CREATE TABLE service_credential_requirements (
    service_id      uuid NOT NULL REFERENCES services(id),
    credential_type text NOT NULL,
    PRIMARY KEY (service_id, credential_type)
);
ALTER TABLE training_credentials ADD COLUMN external_id text;
ALTER TABLE training_credentials ADD COLUMN station_airport_id uuid REFERENCES airports(id);
ALTER TABLE training_credentials ADD COLUMN source_id uuid REFERENCES sources(id);
CREATE UNIQUE INDEX ux_training_credentials_ext ON training_credentials (source_id, external_id) WHERE external_id IS NOT NULL;

-- =====================================================================
-- 6. COUNTRY-BASED DISCOVERY
-- =====================================================================
CREATE TABLE discovery_searches (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name          text,
    saved         boolean NOT NULL DEFAULT false,
    geo_mode      text NOT NULL CHECK (geo_mode IN ('country','countries','region','worldwide')),
    countries     char(2)[] NOT NULL DEFAULT '{}',
    regions       text[] NOT NULL DEFAULT '{}',
    modules       text[] NOT NULL DEFAULT '{}',     -- empty = all nine capability areas
    organisation  text,
    airline       text,
    keywords      text,
    date_from     date,
    date_to       date,
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    deleted_at    timestamptz,
    CHECK (geo_mode = 'worldwide' OR cardinality(countries) > 0 OR cardinality(regions) > 0),
    CHECK (date_to IS NULL OR date_from IS NULL OR date_to >= date_from),
    CHECK (NOT saved OR name IS NOT NULL)
);

CREATE TABLE discovery_runs (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    search_id       uuid REFERENCES discovery_searches(id),
    source_id       uuid REFERENCES sources(id),       -- single-source manual run
    job_id          uuid REFERENCES jobs(id),
    trigger         text NOT NULL CHECK (trigger IN ('manual','schedule','retry')),
    status          text NOT NULL DEFAULT 'queued'
                    CHECK (status IN ('queued','running','completed','partial','failed','cancelled')),
    outcome         text CHECK (outcome IN ('results','no_relevant_results','partial_coverage','source_failure','incomplete','no_sources','cancelled')),
    plan            jsonb NOT NULL DEFAULT '{}'::jsonb,   -- countries, sources selected, coverage gaps
    progress        jsonb NOT NULL DEFAULT '{}'::jsonb,
    counts          jsonb NOT NULL DEFAULT '{}'::jsonb,
    estimated_cost_usd numeric(12,4),
    actual_cost_usd numeric(12,4),
    created_at      timestamptz NOT NULL DEFAULT now(),
    started_at      timestamptz,
    finished_at     timestamptz,
    error           text,
    CHECK (search_id IS NOT NULL OR source_id IS NOT NULL)
);
CREATE INDEX ix_discovery_runs_search ON discovery_runs (search_id, created_at DESC);

CREATE TABLE discovery_run_sources (
    run_id     uuid NOT NULL REFERENCES discovery_runs(id) ON DELETE CASCADE,
    source_id  uuid NOT NULL REFERENCES sources(id),
    status     text NOT NULL CHECK (status IN ('pending','succeeded','failed','skipped','cancelled')),
    detail     text,
    documents  integer NOT NULL DEFAULT 0,
    new_documents integer NOT NULL DEFAULT 0,
    failures   integer NOT NULL DEFAULT 0,
    PRIMARY KEY (run_id, source_id)
);

CREATE TABLE discovery_results (
    run_id         uuid NOT NULL REFERENCES discovery_runs(id) ON DELETE CASCADE,
    signal_id      uuid NOT NULL REFERENCES signals(id),
    opportunity_id uuid REFERENCES opportunities(id),
    is_new         boolean NOT NULL,
    match          jsonb NOT NULL,     -- why it matched: geography roles, capability area, source, dates
    PRIMARY KEY (run_id, signal_id)
);

ALTER TABLE schedules DROP CONSTRAINT schedules_job_type_check;
ALTER TABLE schedules ADD CONSTRAINT schedules_job_type_check
    CHECK (job_type IN ('discovery','discovery_search','import','briefing','connector_health'));
ALTER TABLE schedules ADD COLUMN scope_search_id uuid REFERENCES discovery_searches(id);
ALTER TABLE schedules ADD COLUMN name text;
ALTER TABLE schedules ADD COLUMN updated_at timestamptz NOT NULL DEFAULT now();
CREATE TRIGGER trg_touch_schedules BEFORE UPDATE ON schedules FOR EACH ROW EXECUTE FUNCTION touch_updated_at();
CREATE TRIGGER trg_touch_discovery_searches BEFORE UPDATE ON discovery_searches FOR EACH ROW EXECUTE FUNCTION touch_updated_at();
UPDATE schedules SET name = CASE job_type WHEN 'briefing' THEN 'Expire passed deadlines' ELSE 'Connector health' END;

ALTER TABLE jobs ADD COLUMN retry_of uuid REFERENCES jobs(id);
ALTER TABLE jobs ADD COLUMN progress jsonb;

-- =====================================================================
-- 7. IMPORTS: file binding, partial disclosure
-- =====================================================================
CREATE TABLE import_files (
    import_job_id    uuid PRIMARY KEY REFERENCES import_jobs(id) ON DELETE CASCADE,
    content          bytea NOT NULL,
    naive_timezone   text,
    plan_fingerprint char(64) NOT NULL       -- sha256 of the planned effects + errors shown in the preview
);
ALTER TABLE import_jobs ADD COLUMN preview_job_id uuid REFERENCES import_jobs(id);
ALTER TABLE import_jobs ADD COLUMN partial boolean NOT NULL DEFAULT false;
CREATE UNIQUE INDEX ux_import_commit_per_preview ON import_jobs (preview_job_id) WHERE mode = 'commit';
ALTER TABLE import_jobs DROP CONSTRAINT import_jobs_status_check;
ALTER TABLE import_jobs ADD CONSTRAINT import_jobs_status_check
    CHECK (status IN ('pending','validated','committed','failed','reversed','superseded'));

ALTER TABLE gateway_connections ADD COLUMN source_id uuid REFERENCES sources(id);
ALTER TABLE gateway_connections ADD COLUMN external_id text;
CREATE UNIQUE INDEX ux_gateway_connections_ext ON gateway_connections (source_id, external_id) WHERE external_id IS NOT NULL;
ALTER TABLE gateway_connections ADD COLUMN flight_number text;

ALTER TABLE channel_events ADD COLUMN forwarder_id uuid REFERENCES forwarders(organisation_id);
ALTER TABLE channel_events ADD COLUMN provenance_id uuid REFERENCES provenance(id);
ALTER TABLE financial_aggregates ADD COLUMN provenance_id uuid REFERENCES provenance(id);
ALTER TABLE road_feeder_services ADD COLUMN updated_at timestamptz NOT NULL DEFAULT now();
CREATE TRIGGER trg_touch_road_feeder_services BEFORE UPDATE ON road_feeder_services FOR EACH ROW EXECUTE FUNCTION touch_updated_at();

ALTER TABLE people ADD COLUMN external_id text;
CREATE UNIQUE INDEX ux_people_external ON people (external_id) WHERE external_id IS NOT NULL;

-- Exception ownership (service and operations module)
ALTER TABLE operational_exceptions ADD COLUMN owner_person_id uuid REFERENCES people(id);

-- Network development: discovered signals attached as supporting evidence.
CREATE TABLE network_candidate_signals (
    candidate_id uuid NOT NULL REFERENCES network_candidates(id) ON DELETE CASCADE,
    signal_id    uuid NOT NULL REFERENCES signals(id),
    linked_at    timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (candidate_id, signal_id)
);

-- Custom regions created by the shared login are 'custom' rows in regions.
