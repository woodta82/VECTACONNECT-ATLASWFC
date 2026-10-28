-- VECTA Connect | ATLAS | DYNAMIC MARKET INTELLIGENCE
-- WFC lineage, revision wfc_0001: complete schema for an EMPTY database.
--
-- This file is executed verbatim by alembic/versions/wfc_0001_initial.py and
-- is also applied directly by tests/sql/run_sql_tests.sh against a real
-- PostgreSQL 16 server. It is the single source of schema truth: no
-- create_all(), no startup ALTER TABLE.
--
-- Conventions: uuid PKs, timestamptz in UTC, numeric(18,4) money with an
-- explicit ISO-4217 currency, enumerations as text + CHECK, NULL means
-- "unknown" (never defaulted to zero/false where the business meaning is
-- unknown).

CREATE TABLE schema_meta (
    key   text PRIMARY KEY,
    value text NOT NULL
);
INSERT INTO schema_meta (key, value) VALUES ('lineage', 'wfc'), ('revision', 'wfc_0001');

-- =====================================================================
-- 1. AUTHENTICATION: one shared credential, server-side sessions
-- =====================================================================
CREATE TABLE auth_credential (
    singleton            boolean PRIMARY KEY DEFAULT true CHECK (singleton),
    username             text NOT NULL,
    password_hash        text NOT NULL CHECK (password_hash LIKE 'pbkdf2_sha256$%'),
    password_changed_at  timestamptz NOT NULL DEFAULT now(),
    sessions_valid_after timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE auth_sessions (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    token_hash      text NOT NULL UNIQUE,
    csrf_token_hash text NOT NULL,
    created_at      timestamptz NOT NULL DEFAULT now(),
    last_used_at    timestamptz NOT NULL DEFAULT now(),
    expires_at      timestamptz NOT NULL,
    revoked_at      timestamptz,
    ip              text,
    user_agent      text
);
CREATE INDEX ix_auth_sessions_live ON auth_sessions (expires_at) WHERE revoked_at IS NULL;

CREATE TABLE login_throttle (
    throttle_key text NOT NULL,           -- 'ip:<addr>' or 'account'
    failed_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_login_throttle_key_time ON login_throttle (throttle_key, failed_at);

CREATE TABLE audit_events (
    id          bigserial PRIMARY KEY,
    occurred_at timestamptz NOT NULL DEFAULT now(),
    event_type  text NOT NULL,
    actor       text NOT NULL DEFAULT 'shared_account',  -- never an individual
    session_ref text,                                     -- first 12 hex of session token hash
    request_id  text,
    ip          text,
    user_agent  text,
    entity_type text,
    entity_id   text,
    detail      jsonb NOT NULL DEFAULT '{}'::jsonb     -- metadata only, never secrets/payloads
);
CREATE INDEX ix_audit_events_type_time ON audit_events (event_type, occurred_at DESC);

-- =====================================================================
-- 2. PROVENANCE and INGESTION
-- =====================================================================
CREATE TABLE connectors (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    code           text NOT NULL UNIQUE,
    name           text NOT NULL,
    kind           text NOT NULL CHECK (kind IN ('file_import','public_web','rss','api')),
    status         text NOT NULL DEFAULT 'not_connected'
                   CHECK (status IN ('not_connected','configured','healthy','degraded','disabled')),
    credential_ref text,          -- name of an env var / secret, never the secret itself
    permitted_scope text,
    capabilities   jsonb NOT NULL DEFAULT '[]'::jsonb,
    last_success_at timestamptz,
    last_error     text,
    created_at     timestamptz NOT NULL DEFAULT now(),
    updated_at     timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE sources (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    connector_id        uuid REFERENCES connectors(id),
    name                text NOT NULL,
    family              text NOT NULL,              -- publisher family for independence checks
    base_url            text,
    authority           text NOT NULL DEFAULT 'unverified'
                        CHECK (authority IN ('unverified','trade_press','company_release','official_portal','internal_record')),
    authorisation_note  text,
    retention_permitted boolean NOT NULL DEFAULT false,
    enabled             boolean NOT NULL DEFAULT false,  -- disabled until configured
    freshness_sla_hours integer,
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE ingestion_runs (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id   uuid REFERENCES sources(id),
    job_id      uuid,
    started_at  timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,
    status      text NOT NULL DEFAULT 'running' CHECK (status IN ('running','succeeded','failed','cancelled')),
    stats       jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE provenance (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    kind             text NOT NULL CHECK (kind IN ('import_row','source_document','manual_entry','connector')),
    import_job_id    uuid,
    import_row_number integer,
    source_document_id uuid,
    note             text,
    created_at       timestamptz NOT NULL DEFAULT now()
);

-- =====================================================================
-- 3. NETWORK
-- =====================================================================
CREATE TABLE operating_companies (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name              text NOT NULL UNIQUE,
    legal_entity_name text,         -- NULL: brand only / legal entity not established
    country           char(2),
    is_group_member   boolean NOT NULL DEFAULT true,
    provenance_id     uuid REFERENCES provenance(id),
    created_at        timestamptz NOT NULL DEFAULT now(),
    updated_at        timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE brands (
    id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    operating_company_id uuid NOT NULL REFERENCES operating_companies(id),
    name                 text NOT NULL,
    UNIQUE (operating_company_id, name)
);

CREATE TABLE organisations (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    canonical_name text NOT NULL,
    kind           text NOT NULL CHECK (kind IN ('airline','forwarder','gssa','airport_operator','trucking_provider','shipper','other')),
    country        char(2),
    website        text,
    merged_into_id uuid REFERENCES organisations(id),
    provenance_id  uuid REFERENCES provenance(id),
    created_at     timestamptz NOT NULL DEFAULT now(),
    updated_at     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_organisations_name ON organisations (lower(canonical_name));

CREATE TABLE organisation_aliases (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organisation_id uuid NOT NULL REFERENCES organisations(id),
    alias           text NOT NULL,
    alias_norm      text NOT NULL,
    provenance_id   uuid REFERENCES provenance(id),
    UNIQUE (organisation_id, alias_norm)
);
CREATE INDEX ix_org_alias_norm ON organisation_aliases (alias_norm);

CREATE TABLE organisation_merges (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    survivor_id uuid NOT NULL REFERENCES organisations(id),
    merged_id   uuid NOT NULL REFERENCES organisations(id),
    reason      text NOT NULL,
    proposed_by text NOT NULL CHECK (proposed_by IN ('fuzzy_match','manual')),
    decided_at  timestamptz NOT NULL DEFAULT now(),
    reversed_at timestamptz,
    CHECK (survivor_id <> merged_id)
);

CREATE TABLE airlines (
    organisation_id uuid PRIMARY KEY REFERENCES organisations(id),
    iata_code       char(2) CHECK (iata_code ~ '^[A-Z0-9]{2}$'),
    icao_code       char(3) CHECK (icao_code ~ '^[A-Z]{3}$'),
    awb_prefix      char(3) CHECK (awb_prefix ~ '^[0-9]{3}$')
);
CREATE UNIQUE INDEX ux_airlines_icao ON airlines (icao_code) WHERE icao_code IS NOT NULL;

CREATE TABLE forwarders (
    organisation_id uuid PRIMARY KEY REFERENCES organisations(id),
    network         text
);

CREATE TABLE airports (
    id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    iata_code char(3) NOT NULL UNIQUE CHECK (iata_code ~ '^[A-Z]{3}$'),
    icao_code char(4) CHECK (icao_code ~ '^[A-Z]{4}$'),
    name      text NOT NULL,
    country   char(2) NOT NULL,
    timezone  text NOT NULL            -- IANA, e.g. Asia/Dubai
);

CREATE TABLE territories (
    id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    code      text NOT NULL UNIQUE,     -- ISO country code, region code, or station IATA
    name      text NOT NULL,
    kind      text NOT NULL CHECK (kind IN ('country','region','station'))
);

CREATE TABLE trade_lanes (
    id                     uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    origin_airport_id      uuid NOT NULL REFERENCES airports(id),
    destination_airport_id uuid NOT NULL REFERENCES airports(id),
    UNIQUE (origin_airport_id, destination_airport_id),     -- directional: A->B and B->A are distinct rows
    CHECK (origin_airport_id <> destination_airport_id)
);

-- =====================================================================
-- 4. CAPABILITY
-- =====================================================================
CREATE TABLE services (
    id       uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    code     text NOT NULL UNIQUE,
    name     text NOT NULL,
    category text NOT NULL CHECK (category IN ('gssa','tcm','handling','trucking','data_processing','accounting','invoicing','collections','training','technology'))
);

INSERT INTO services (code, name, category) VALUES
    ('GSSA', 'General sales and service agency', 'gssa'),
    ('TCM', 'Total cargo management', 'tcm'),
    ('HANDLING', 'Cargo handling', 'handling'),
    ('TRUCKING', 'Road feeder / trucking', 'trucking'),
    ('DATA_PROCESSING', 'Data processing', 'data_processing'),
    ('ACCOUNTING', 'Accounting', 'accounting'),
    ('INVOICING', 'Invoicing', 'invoicing'),
    ('COLLECTIONS', 'Collections', 'collections'),
    ('TRAINING', 'Training', 'training'),
    ('TECHNOLOGY', 'Technology and solutions', 'technology');

CREATE TABLE capability_records (
    id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    operating_company_id uuid NOT NULL REFERENCES operating_companies(id),
    service_id           uuid NOT NULL REFERENCES services(id),
    station_airport_id   uuid REFERENCES airports(id),
    status               text NOT NULL DEFAULT 'unverified' CHECK (status IN ('verified','unverified','withdrawn')),
    verification_owner   text,
    verified_at          date,
    valid_from           date,
    valid_to             date,             -- NULL = unknown, never assumed open-ended
    commodity_restrictions text,
    resource_constraints text,
    languages            text[],
    capacity_note        text,
    evidence_note        text,
    provenance_id        uuid REFERENCES provenance(id),
    created_at           timestamptz NOT NULL DEFAULT now(),
    updated_at           timestamptz NOT NULL DEFAULT now(),
    CHECK (valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from)
);

CREATE UNIQUE INDEX ux_capability_scope ON capability_records
    (operating_company_id, service_id, coalesce(station_airport_id, '00000000-0000-0000-0000-000000000000'::uuid));

CREATE TABLE training_credentials (
    id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    operating_company_id uuid NOT NULL REFERENCES operating_companies(id),
    service_id           uuid REFERENCES services(id),
    credential_type      text NOT NULL,
    holder_description   text,
    issued_on            date,
    expires_on           date,             -- NULL = unknown (taken only from records)
    provenance_id        uuid REFERENCES provenance(id),
    created_at           timestamptz NOT NULL DEFAULT now()
);

-- =====================================================================
-- 5. CONTRACTS
-- =====================================================================
CREATE TABLE representation_agreements (
    id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    external_id          text,
    airline_id           uuid NOT NULL REFERENCES airlines(organisation_id),
    operating_company_id uuid NOT NULL REFERENCES operating_companies(id),
    effective_from       date,
    effective_to         date,
    renewal_date         date,
    notice_date          date,
    exclusivity          text NOT NULL DEFAULT 'unknown' CHECK (exclusivity IN ('exclusive','non_exclusive','unknown')),
    appointment_rights   text NOT NULL DEFAULT 'unknown' CHECK (appointment_rights IN ('may_extend','requires_consent','prohibited','unknown')),
    remuneration_model   text NOT NULL DEFAULT 'unknown' CHECK (remuneration_model IN ('commission','fixed_fee','tcm_margin','hybrid','unknown')),
    remuneration_terms   jsonb,            -- as stated in the contract; NULL = unknown
    source_use_restrictions text,
    status               text NOT NULL DEFAULT 'active' CHECK (status IN ('draft','active','expired','terminated')),
    provenance_id        uuid REFERENCES provenance(id),
    created_at           timestamptz NOT NULL DEFAULT now(),
    updated_at           timestamptz NOT NULL DEFAULT now(),
    UNIQUE (external_id)
);

CREATE TABLE agreement_services (
    agreement_id uuid NOT NULL REFERENCES representation_agreements(id) ON DELETE CASCADE,
    service_id   uuid NOT NULL REFERENCES services(id),
    PRIMARY KEY (agreement_id, service_id)
);

CREATE TABLE agreement_territories (
    agreement_id uuid NOT NULL REFERENCES representation_agreements(id) ON DELETE CASCADE,
    territory_id uuid NOT NULL REFERENCES territories(id),
    PRIMARY KEY (agreement_id, territory_id)
);

CREATE TABLE third_party_appointments (
    id                     uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    airline_id             uuid NOT NULL REFERENCES airlines(organisation_id),
    territory_id           uuid NOT NULL REFERENCES territories(id),
    service_id             uuid REFERENCES services(id),
    holder_organisation_id uuid REFERENCES organisations(id),
    exclusivity            text NOT NULL DEFAULT 'unknown' CHECK (exclusivity IN ('exclusive','non_exclusive','unknown')),
    valid_to               date,
    evidence_note          text,
    provenance_id          uuid REFERENCES provenance(id)
);

-- =====================================================================
-- 6. INTELLIGENCE
-- =====================================================================
CREATE TABLE announcement_families (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    family_key  text NOT NULL UNIQUE,      -- normalised fingerprint of the underlying announcement
    first_seen_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE source_documents (
    id                     uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id              uuid REFERENCES sources(id),
    ingestion_run_id       uuid REFERENCES ingestion_runs(id),
    announcement_family_id uuid REFERENCES announcement_families(id),
    original_url           text NOT NULL,
    canonical_url          text NOT NULL,
    publisher              text,
    published_at           timestamptz,
    event_date             date,
    retrieved_at           timestamptz NOT NULL,
    content_hash           char(64) NOT NULL,
    content_type           text,
    byte_size              integer,
    title                  text,
    excerpt                text,
    page_ref               text,
    snapshot_path          text,               -- NULL when retention is not permitted
    access_restrictions    text,
    parser_version         text NOT NULL,
    UNIQUE (canonical_url, content_hash)       -- same content re-fetched = same document
);

CREATE TABLE document_checks (
    id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_document_id uuid NOT NULL REFERENCES source_documents(id) ON DELETE CASCADE,
    check_type         text NOT NULL CHECK (check_type IN ('reachability','authenticity','relevance','current_status')),
    result             text NOT NULL CHECK (result IN ('pass','fail','unknown')),
    detail             text,
    checked_at         timestamptz NOT NULL DEFAULT now(),
    UNIQUE (source_document_id, check_type, checked_at)
);

CREATE TABLE claims (
    id                     uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    claim_type             text NOT NULL CHECK (claim_type IN (
                              'route_launch','route_suspension','gssa_tender','tender_deadline','tender_scope',
                              'tender_status','representation_change','tcm_signal','capacity_statement',
                              'partnership','eligibility','other')),
    claim_key              text NOT NULL,          -- deterministic key: type + subject identifiers
    subject_organisation_id uuid REFERENCES organisations(id),
    airline_id             uuid REFERENCES airlines(organisation_id),
    territory_id           uuid REFERENCES territories(id),
    trade_lane_id          uuid REFERENCES trade_lanes(id),
    value                  jsonb NOT NULL DEFAULT '{}'::jsonb,
    deadline_utc           timestamptz,
    deadline_source_tz     text,
    status                 text NOT NULL DEFAULT 'unverified'
                           CHECK (status IN ('unverified','supported','contradicted','superseded','withdrawn')),
    superseded_by_id       uuid REFERENCES claims(id),
    created_at             timestamptz NOT NULL DEFAULT now(),
    updated_at             timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_claims_key ON claims (claim_key);

CREATE TABLE claim_evidence (
    id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    claim_id           uuid NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
    source_document_id uuid NOT NULL REFERENCES source_documents(id),
    stance             text NOT NULL CHECK (stance IN ('supports','contradicts','mentions')),
    excerpt            text,
    page_ref           text,
    assessed_by        text NOT NULL CHECK (assessed_by IN ('rule','ai_proposed','human')),
    created_at         timestamptz NOT NULL DEFAULT now(),
    UNIQUE (claim_id, source_document_id, stance)
);

CREATE TABLE signals (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    module         text NOT NULL CHECK (module IN ('airline_representation','account_growth','forwarder_sales','capacity_lanes',
                                                    'service_operations','trucking_gateways','outsourcing_training',
                                                    'technology_solutions','network_development')),
    classification text NOT NULL CHECK (classification IN ('market_signal','unverified_lead','qualified_opportunity','risk_alert','research_item')),
    signal_key     text NOT NULL,
    title          text NOT NULL,
    summary        text,
    gaps           jsonb NOT NULL DEFAULT '[]'::jsonb,   -- explicit missing information
    created_at     timestamptz NOT NULL DEFAULT now(),
    updated_at     timestamptz NOT NULL DEFAULT now(),
    UNIQUE (module, signal_key)
);

CREATE TABLE signal_claims (
    signal_id uuid NOT NULL REFERENCES signals(id) ON DELETE CASCADE,
    claim_id  uuid NOT NULL REFERENCES claims(id),
    PRIMARY KEY (signal_id, claim_id)
);

-- =====================================================================
-- 7. COMMERCIAL WORK
-- =====================================================================
CREATE TABLE people (                        -- descriptive owners/contacts, NOT logins
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    full_name       text NOT NULL,
    role_title      text,
    organisation_id uuid REFERENCES organisations(id),
    operating_company_id uuid REFERENCES operating_companies(id),
    email           text,
    is_internal     boolean NOT NULL DEFAULT false,
    provenance_id   uuid REFERENCES provenance(id),
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE opportunities (
    id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    module               text NOT NULL,
    signal_id            uuid REFERENCES signals(id),
    dedup_key            text NOT NULL,
    title                text NOT NULL,
    airline_id           uuid REFERENCES airlines(organisation_id),
    organisation_id      uuid REFERENCES organisations(id),
    territory_id         uuid REFERENCES territories(id),
    service_id           uuid REFERENCES services(id),
    operating_company_id uuid REFERENCES operating_companies(id),
    commercial_stage     text NOT NULL DEFAULT 'new' CHECK (commercial_stage IN
                           ('new','reviewing','qualified','pursuing','proposal','negotiation','won','lost','deferred','expired')),
    qualification_status text NOT NULL DEFAULT 'incomplete' CHECK (qualification_status IN
                           ('incomplete','blocked','ready_for_review','approved_for_pursuit')),
    deadline_utc         timestamptz,
    deadline_source_tz   text,
    owner_person_id      uuid REFERENCES people(id),
    competition_group_id uuid,              -- alternatives competing for the same mandate
    is_acquisition_research boolean NOT NULL DEFAULT false,
    created_at           timestamptz NOT NULL DEFAULT now(),
    updated_at           timestamptz NOT NULL DEFAULT now(),
    UNIQUE (module, dedup_key),
    CHECK (NOT is_acquisition_research)     -- acquisition research lives in network_candidates, never the sales pipeline
);
CREATE INDEX ix_opportunities_deadline ON opportunities (deadline_utc);

CREATE TABLE opportunity_status_history (
    id             bigserial PRIMARY KEY,
    opportunity_id uuid NOT NULL REFERENCES opportunities(id) ON DELETE CASCADE,
    field          text NOT NULL CHECK (field IN ('commercial_stage','qualification_status')),
    from_value     text,
    to_value       text NOT NULL,
    reason         text,
    session_ref    text,
    changed_at     timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE qualification_checks (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    opportunity_id uuid NOT NULL REFERENCES opportunities(id) ON DELETE CASCADE,
    check_code     text NOT NULL,
    result         text NOT NULL CHECK (result IN ('pass','fail','unknown','review_required')),
    blocking       boolean NOT NULL DEFAULT false,
    rationale      text NOT NULL,
    evidence_refs  jsonb NOT NULL DEFAULT '[]'::jsonb,
    evaluated_at   timestamptz NOT NULL DEFAULT now(),
    reviewer_note  text,
    UNIQUE (opportunity_id, check_code)
);

CREATE TABLE qualification_overrides (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    opportunity_id uuid NOT NULL REFERENCES opportunities(id) ON DELETE CASCADE,
    check_code     text NOT NULL,
    override_result text NOT NULL CHECK (override_result IN ('pass','fail','review_required')),
    reason         text NOT NULL CHECK (length(trim(reason)) >= 10),
    session_ref    text NOT NULL,
    created_at     timestamptz NOT NULL DEFAULT now(),
    expires_at     timestamptz,
    revoked_at     timestamptz
);

CREATE TABLE tasks (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    dedup_key       text NOT NULL UNIQUE,
    title           text NOT NULL,
    source_type     text NOT NULL,
    source_id       uuid,
    owner_person_id uuid REFERENCES people(id),
    due_at_utc      timestamptz,
    status          text NOT NULL DEFAULT 'open' CHECK (status IN ('open','in_progress','done','cancelled')),
    created_at      timestamptz NOT NULL DEFAULT now(),
    completed_at    timestamptz
);

CREATE TABLE engagements (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organisation_id uuid REFERENCES organisations(id),
    person_id       uuid REFERENCES people(id),
    opportunity_id  uuid REFERENCES opportunities(id),
    occurred_at     timestamptz NOT NULL,
    kind            text NOT NULL CHECK (kind IN ('meeting','call','email','proposal','visit','other')),
    summary         text NOT NULL,
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE account_ownership (
    organisation_id      uuid NOT NULL REFERENCES organisations(id),
    operating_company_id uuid NOT NULL REFERENCES operating_companies(id),
    owner_person_id      uuid NOT NULL REFERENCES people(id),
    PRIMARY KEY (organisation_id, operating_company_id)
);

CREATE TABLE referrals (
    id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    opportunity_id       uuid NOT NULL REFERENCES opportunities(id),
    from_company_id      uuid NOT NULL REFERENCES operating_companies(id),
    to_company_id        uuid NOT NULL REFERENCES operating_companies(id),
    status               text NOT NULL DEFAULT 'proposed' CHECK (status IN ('proposed','accepted','declined','closed')),
    created_at           timestamptz NOT NULL DEFAULT now(),
    CHECK (from_company_id <> to_company_id),
    UNIQUE (opportunity_id, to_company_id)
);

CREATE TABLE proposals (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    opportunity_id uuid REFERENCES opportunities(id),
    airline_id     uuid REFERENCES airlines(organisation_id),
    territory_id   uuid REFERENCES territories(id),
    submitted_on   date,
    outcome        text CHECK (outcome IN ('won','lost','withdrawn','pending')),
    outcome_reason text,
    provenance_id  uuid REFERENCES provenance(id)
);

CREATE TABLE commercial_values (
    opportunity_id         uuid PRIMARY KEY REFERENCES opportunities(id) ON DELETE CASCADE,
    currency               char(3),
    airline_revenue        numeric(18,4),
    wfc_remuneration       numeric(18,4),
    incremental_costs      numeric(18,4),
    guarantee_exposure     numeric(18,4),
    duration_months        integer,
    retained_contribution  numeric(18,4),
    basis                  text NOT NULL DEFAULT 'unknown' CHECK (basis IN ('contract','scenario','unknown')),
    assumptions            jsonb NOT NULL DEFAULT '[]'::jsonb,
    value_kind             text NOT NULL DEFAULT 'potential' CHECK (value_kind IN ('potential','won','realised')),
    updated_at             timestamptz NOT NULL DEFAULT now(),
    CHECK (currency IS NOT NULL OR (airline_revenue IS NULL AND wfc_remuneration IS NULL AND incremental_costs IS NULL
                                     AND guarantee_exposure IS NULL AND retained_contribution IS NULL))
);

CREATE TABLE realised_values (
    id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    opportunity_id       uuid NOT NULL REFERENCES opportunities(id),
    attributed_company_id uuid NOT NULL REFERENCES operating_companies(id),
    period_start         date NOT NULL,
    period_end           date NOT NULL,
    currency             char(3) NOT NULL,
    contribution         numeric(18,4) NOT NULL,
    provenance_id        uuid REFERENCES provenance(id),
    UNIQUE (opportunity_id, period_start, period_end)     -- one attribution per period: no double counting
);

-- Scoring: versioned, deterministic
CREATE TABLE scoring_model_versions (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    module      text NOT NULL,
    version     text NOT NULL,
    definition  jsonb NOT NULL,
    provisional boolean NOT NULL DEFAULT true,
    created_at  timestamptz NOT NULL DEFAULT now(),
    UNIQUE (module, version)
);

CREATE TABLE assessments (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    opportunity_id   uuid NOT NULL REFERENCES opportunities(id) ON DELETE CASCADE,
    model_version_id uuid NOT NULL REFERENCES scoring_model_versions(id),
    dimension        text NOT NULL CHECK (dimension IN ('attractiveness','evidence_confidence','readiness','risk')),
    score            numeric(5,2),          -- NULL when coverage is insufficient
    coverage         numeric(5,4) NOT NULL,
    status           text NOT NULL CHECK (status IN ('scored','insufficient_evidence','blocked')),
    factors          jsonb NOT NULL,
    computed_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_assessments_opp ON assessments (opportunity_id, dimension, computed_at DESC);

-- Network development (separate from the sales pipeline)
CREATE TABLE network_candidates (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    kind            text NOT NULL CHECK (kind IN ('coverage_gap','partner','referral','acquisition_research')),
    organisation_id uuid REFERENCES organisations(id),
    territory_id    uuid REFERENCES territories(id),
    service_id      uuid REFERENCES services(id),
    title           text NOT NULL,
    status          text NOT NULL DEFAULT 'open' CHECK (status IN ('open','assessing','parked','closed')),
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE fit_assessments (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    network_candidate_id uuid NOT NULL REFERENCES network_candidates(id) ON DELETE CASCADE,
    result              text NOT NULL CHECK (result IN ('strong','partial','weak','insufficient_evidence')),
    rationale           jsonb NOT NULL,
    evidence_claim_ids  uuid[] NOT NULL DEFAULT '{}',
    assessed_at         timestamptz NOT NULL DEFAULT now()
);

-- =====================================================================
-- 8. PERFORMANCE DATA
-- =====================================================================
CREATE TABLE quotes (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id           uuid NOT NULL REFERENCES sources(id),
    external_id         text NOT NULL,
    forwarder_id        uuid REFERENCES forwarders(organisation_id),
    airline_id          uuid REFERENCES airlines(organisation_id),
    trade_lane_id       uuid REFERENCES trade_lanes(id),
    operating_company_id uuid REFERENCES operating_companies(id),
    quoted_at           timestamptz NOT NULL,
    status              text NOT NULL CHECK (status IN ('open','won','lost','expired','cancelled')),
    lost_reason         text,
    chargeable_weight_kg numeric(14,3),
    amount              numeric(18,4),
    currency            char(3),
    owner_person_id     uuid REFERENCES people(id),
    provenance_id       uuid REFERENCES provenance(id),
    updated_at          timestamptz NOT NULL DEFAULT now(),
    UNIQUE (source_id, external_id)
);

CREATE TABLE bookings (
    id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id            uuid NOT NULL REFERENCES sources(id),
    external_id          text NOT NULL,
    forwarder_id         uuid REFERENCES forwarders(organisation_id),
    airline_id           uuid REFERENCES airlines(organisation_id),
    trade_lane_id        uuid REFERENCES trade_lanes(id),
    operating_company_id uuid REFERENCES operating_companies(id),
    flight_date          date,
    booked_at            timestamptz NOT NULL,
    status               text NOT NULL CHECK (status IN ('confirmed','amended','cancelled')),
    actual_weight_kg     numeric(14,3),
    chargeable_weight_kg numeric(14,3),
    volume_m3            numeric(14,3),
    revenue              numeric(18,4),
    currency             char(3),
    fx_rate_to_reporting numeric(18,8),
    fx_source            text,
    fx_date              date,
    source_updated_at    timestamptz,
    provenance_id        uuid REFERENCES provenance(id),
    updated_at           timestamptz NOT NULL DEFAULT now(),
    UNIQUE (source_id, external_id),
    CHECK (revenue IS NULL OR currency IS NOT NULL)
);
CREATE INDEX ix_bookings_forwarder ON bookings (forwarder_id, flight_date);
CREATE INDEX ix_bookings_airline ON bookings (airline_id);
CREATE INDEX ix_bookings_lane_date ON bookings (trade_lane_id, flight_date);
CREATE INDEX ix_quotes_forwarder_time ON quotes (forwarder_id, quoted_at);

CREATE TABLE capacity_snapshots (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id     uuid NOT NULL REFERENCES sources(id),
    external_id   text NOT NULL,
    airline_id    uuid REFERENCES airlines(organisation_id),
    trade_lane_id uuid NOT NULL REFERENCES trade_lanes(id),
    flight_number text,
    period_start  date NOT NULL,
    period_end    date NOT NULL,
    basis         text NOT NULL CHECK (basis IN ('weight_kg','volume_m3')),
    capacity_type text NOT NULL CHECK (capacity_type IN ('offered','bookable','allotted')),
    amount        numeric(16,3) NOT NULL CHECK (amount >= 0),
    snapshot_at   timestamptz NOT NULL,
    provenance_id uuid REFERENCES provenance(id),
    UNIQUE (source_id, external_id)
);

CREATE TABLE operational_exceptions (
    id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id            uuid REFERENCES sources(id),
    external_id          text,
    dedup_key            text NOT NULL,
    exception_type       text NOT NULL CHECK (exception_type IN ('reservation','supervision','post_flight')),
    severity             text NOT NULL CHECK (severity IN ('low','medium','high','critical')),
    customer_organisation_id uuid REFERENCES organisations(id),
    operating_company_id uuid REFERENCES operating_companies(id),
    booking_id           uuid REFERENCES bookings(id),
    description          text NOT NULL,
    deadline_utc         timestamptz,
    status               text NOT NULL DEFAULT 'open' CHECK (status IN ('open','acknowledged','resolved')),
    opened_at            timestamptz NOT NULL DEFAULT now(),
    resolved_at          timestamptz
);
CREATE UNIQUE INDEX ux_opex_active_dedup ON operational_exceptions (dedup_key) WHERE status <> 'resolved';

CREATE TABLE operational_exception_history (
    id           bigserial PRIMARY KEY,
    exception_id uuid NOT NULL REFERENCES operational_exceptions(id) ON DELETE CASCADE,
    from_status  text,
    to_status    text NOT NULL,
    note         text,
    changed_at   timestamptz NOT NULL DEFAULT now()
);

-- Every imported exception report, keyed by its source id. Several reports
-- may describe the same underlying problem (same dedup key); re-importing a
-- report is recognised here and never creates another exception, alert or task.
CREATE TABLE exception_reports (
    source_id    uuid NOT NULL REFERENCES sources(id),
    external_id  text NOT NULL,
    exception_id uuid NOT NULL REFERENCES operational_exceptions(id),
    report       jsonb NOT NULL,
    updated_at   timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (source_id, external_id)
);

CREATE TABLE stations (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    code       text NOT NULL UNIQUE,
    name       text NOT NULL,
    is_offline boolean NOT NULL DEFAULT true,      -- offline station = no own flights
    country    char(2),
    timezone   text
);

CREATE TABLE road_feeder_services (
    id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id             uuid REFERENCES sources(id),
    external_id           text,
    provider_organisation_id uuid REFERENCES organisations(id),
    origin_station_id     uuid NOT NULL REFERENCES stations(id),
    gateway_airport_id    uuid NOT NULL REFERENCES airports(id),
    departure_days        smallint[],              -- ISO weekday numbers
    departure_time_local  time,
    transit_minutes       integer,
    restrictions          text,
    provenance_id         uuid REFERENCES provenance(id),
    UNIQUE (source_id, external_id)
);

CREATE TABLE gateway_connections (
    id                       uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    gateway_airport_id       uuid NOT NULL REFERENCES airports(id),
    airline_id               uuid REFERENCES airlines(organisation_id),
    trade_lane_id            uuid REFERENCES trade_lanes(id),
    departure_days           smallint[],
    departure_time_local     time,
    connection_cutoff_minutes integer,             -- NULL = cutoff unknown => unresolved
    provenance_id            uuid REFERENCES provenance(id)
);

CREATE TABLE channel_events (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id           uuid NOT NULL REFERENCES sources(id),
    external_id         text NOT NULL,
    event_type          text NOT NULL CHECK (event_type IN ('search','quote_request','quote','booking','integration_failure')),
    session_key         text,
    booking_external_id text,
    channel             text NOT NULL,
    occurred_at         timestamptz NOT NULL,
    detail              jsonb NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (source_id, external_id)
);

CREATE TABLE financial_aggregates (
    id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id            uuid NOT NULL REFERENCES sources(id),
    operating_company_id uuid NOT NULL REFERENCES operating_companies(id),
    period_start         date NOT NULL,
    period_end           date NOT NULL,
    metric               text NOT NULL,
    amount               numeric(18,4) NOT NULL,
    currency             char(3) NOT NULL,
    basis                text NOT NULL,
    UNIQUE (source_id, operating_company_id, period_start, period_end, metric, currency)
);

-- =====================================================================
-- 9. IMPORTS
-- =====================================================================
CREATE TABLE import_jobs (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    dataset        text NOT NULL,
    source_id      uuid REFERENCES sources(id),
    file_name      text NOT NULL,
    file_sha256    char(64) NOT NULL,
    schema_version text NOT NULL,
    mapping        jsonb NOT NULL DEFAULT '{}'::jsonb,
    mode           text NOT NULL CHECK (mode IN ('dry_run','commit')),
    status         text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','validated','committed','failed','reversed')),
    totals         jsonb NOT NULL DEFAULT '{}'::jsonb,
    session_ref    text,
    created_at     timestamptz NOT NULL DEFAULT now(),
    committed_at   timestamptz,
    reversed_at    timestamptz,
    reversal_reason text
);

CREATE TABLE import_row_errors (
    id            bigserial PRIMARY KEY,
    import_job_id uuid NOT NULL REFERENCES import_jobs(id) ON DELETE CASCADE,
    row_number    integer NOT NULL,
    field         text,
    error_code    text NOT NULL,
    message       text NOT NULL,
    raw_row       jsonb NOT NULL
);

CREATE TABLE import_row_effects (           -- traceability + reversal
    id            bigserial PRIMARY KEY,
    import_job_id uuid NOT NULL REFERENCES import_jobs(id) ON DELETE CASCADE,
    row_number    integer NOT NULL,
    target_table  text NOT NULL,
    target_id     uuid NOT NULL,
    action        text NOT NULL CHECK (action IN ('insert','update','unchanged')),
    previous      jsonb
);

-- =====================================================================
-- 10. AUTOMATION: durable jobs, schedules, budgets, AI calls
-- =====================================================================
CREATE TABLE schedules (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    job_type        text NOT NULL CHECK (job_type IN ('discovery','import','briefing','connector_health')),
    scope_source_id uuid REFERENCES sources(id),
    scope_region    text,
    scope_module    text,
    interval_minutes integer NOT NULL CHECK (interval_minutes >= 15),
    timezone        text NOT NULL DEFAULT 'Asia/Dubai',
    overlap_policy  text NOT NULL DEFAULT 'skip' CHECK (overlap_policy IN ('skip','queue')),
    enabled         boolean NOT NULL DEFAULT false,
    next_run_at     timestamptz,
    last_success_at timestamptz,
    last_failure_at timestamptz,
    created_at      timestamptz NOT NULL DEFAULT now()
);

INSERT INTO schedules (job_type, interval_minutes, timezone, overlap_policy, enabled) VALUES
    ('briefing', 60, 'Asia/Dubai', 'skip', true),          -- expires opportunities whose deadline has passed
    ('connector_health', 360, 'Asia/Dubai', 'skip', true);

CREATE TABLE jobs (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    job_type         text NOT NULL,
    execution_key    text NOT NULL UNIQUE,           -- e.g. schedule:<id>:<slot> => duplicate schedulers cannot double-enqueue
    schedule_id      uuid REFERENCES schedules(id),
    payload          jsonb NOT NULL DEFAULT '{}'::jsonb,
    status           text NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','running','succeeded','failed','dead','cancelled')),
    run_after        timestamptz NOT NULL DEFAULT now(),
    attempts         integer NOT NULL DEFAULT 0,
    max_attempts     integer NOT NULL DEFAULT 5,
    lease_owner      text,
    lease_expires_at timestamptz,
    checkpoint       jsonb,
    last_error       text,
    estimated_cost   numeric(12,4) NOT NULL DEFAULT 0,
    created_at       timestamptz NOT NULL DEFAULT now(),
    finished_at      timestamptz
);
CREATE INDEX ix_jobs_ready ON jobs (run_after) WHERE status = 'queued';

CREATE TABLE job_attempts (
    id          bigserial PRIMARY KEY,
    job_id      uuid NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    attempt     integer NOT NULL,
    worker      text NOT NULL,
    started_at  timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,
    outcome     text CHECK (outcome IN ('succeeded','failed','lease_expired','cancelled')),
    error       text,
    UNIQUE (job_id, attempt)
);

CREATE TABLE budget_periods (
    period_month   date PRIMARY KEY CHECK (extract(day FROM period_month) = 1),
    cap_usd        numeric(12,4) NOT NULL CHECK (cap_usd >= 0),
    warn_at_usd    numeric(12,4) NOT NULL,
    per_run_cap_usd numeric(12,4) NOT NULL
);

CREATE TABLE budget_reservations (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    period_month date NOT NULL REFERENCES budget_periods(period_month),
    job_id       uuid REFERENCES jobs(id),
    reserved_usd numeric(12,4) NOT NULL CHECK (reserved_usd >= 0),
    actual_usd   numeric(12,4),
    status       text NOT NULL DEFAULT 'reserved' CHECK (status IN ('reserved','settled','released')),
    created_at   timestamptz NOT NULL DEFAULT now(),
    settled_at   timestamptz
);

CREATE TABLE ai_calls (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id          uuid REFERENCES jobs(id),
    provider        text NOT NULL,
    model           text NOT NULL,
    prompt_version  text NOT NULL,
    schema_version  text NOT NULL,
    input_tokens    integer,
    output_tokens   integer,
    retrieval_charges_usd numeric(12,4),
    estimated_cost_usd numeric(12,4) NOT NULL,
    actual_cost_usd numeric(12,4),
    status          text NOT NULL CHECK (status IN ('succeeded','failed','quarantined')),
    error           text,
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE ai_quarantine (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    ai_call_id  uuid NOT NULL REFERENCES ai_calls(id),
    reason      text NOT NULL,
    raw_output  text NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE notifications (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    dedup_key      text NOT NULL UNIQUE,
    kind           text NOT NULL,
    title          text NOT NULL,
    body           text,
    entity_type    text,
    entity_id      uuid,
    delivery_state text NOT NULL DEFAULT 'pending' CHECK (delivery_state IN ('pending','delivered','failed','suppressed')),
    created_at     timestamptz NOT NULL DEFAULT now(),
    read_at        timestamptz
);

CREATE TABLE system_flags (
    key        text PRIMARY KEY,
    value      jsonb NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);
INSERT INTO system_flags (key, value) VALUES
    ('ai_kill_switch', 'true'::jsonb),               -- AI spend disabled until explicitly enabled
    ('reporting_timezone', '"Asia/Dubai"'::jsonb);

-- =====================================================================
-- 11. FUNCTIONS: concurrency-safe primitives used by the worker
-- =====================================================================

-- Claim the next ready job with a lease. SKIP LOCKED => concurrent workers
-- never receive the same job; expired leases are reclaimable after a crash.
CREATE FUNCTION claim_next_job(p_worker text, p_lease_seconds integer)
RETURNS SETOF jobs LANGUAGE plpgsql AS $$
DECLARE
    v_id uuid;
BEGIN
    -- Jobs whose worker died (lease expired while running): record the lost
    -- attempt, then requeue, or dead-letter once max_attempts is reached, so a
    -- job that keeps crashing its worker cannot retry forever.
    UPDATE job_attempts a SET finished_at = now(), outcome = 'lease_expired'
      FROM jobs j
     WHERE a.job_id = j.id AND a.attempt = j.attempts AND a.finished_at IS NULL
       AND j.status = 'running' AND j.lease_expires_at < now();
    UPDATE jobs SET status = CASE WHEN attempts >= max_attempts THEN 'dead' ELSE 'queued' END,
                    finished_at = CASE WHEN attempts >= max_attempts THEN now() ELSE NULL END,
                    last_error = coalesce(last_error, 'worker lease expired'),
                    lease_owner = NULL, lease_expires_at = NULL
     WHERE status = 'running' AND lease_expires_at < now();

    SELECT id INTO v_id FROM jobs
     WHERE status = 'queued' AND run_after <= now()
     ORDER BY run_after, created_at
     FOR UPDATE SKIP LOCKED
     LIMIT 1;
    IF v_id IS NULL THEN
        RETURN;
    END IF;

    RETURN QUERY
    UPDATE jobs SET status = 'running', attempts = attempts + 1, lease_owner = p_worker,
                    lease_expires_at = now() + make_interval(secs => p_lease_seconds)
     WHERE id = v_id
    RETURNING *;
END $$;

-- Reserve budget atomically. The per-month row lock serialises concurrent
-- reservations so the cap cannot be exceeded by racing jobs.
-- Returns the reservation id, or NULL if the kill switch is on or the
-- per-run / monthly cap would be exceeded.
CREATE FUNCTION reserve_budget(p_job uuid, p_amount numeric, p_at timestamptz DEFAULT now())
RETURNS uuid LANGUAGE plpgsql AS $$
DECLARE
    v_month date := date_trunc('month', p_at AT TIME ZONE 'UTC')::date;
    v_period budget_periods%ROWTYPE;
    v_committed numeric;
    v_id uuid;
BEGIN
    IF (SELECT value FROM system_flags WHERE key = 'ai_kill_switch') = 'true'::jsonb THEN
        RETURN NULL;
    END IF;
    SELECT * INTO v_period FROM budget_periods WHERE period_month = v_month FOR UPDATE;
    IF NOT FOUND OR p_amount > v_period.per_run_cap_usd THEN
        RETURN NULL;
    END IF;
    SELECT coalesce(sum(CASE WHEN status = 'reserved' THEN reserved_usd
                             WHEN status = 'settled'  THEN greatest(actual_usd, 0) ELSE 0 END), 0)
      INTO v_committed
      FROM budget_reservations WHERE period_month = v_month;
    IF v_committed + p_amount > v_period.cap_usd THEN
        RETURN NULL;
    END IF;
    INSERT INTO budget_reservations (period_month, job_id, reserved_usd)
    VALUES (v_month, p_job, p_amount) RETURNING id INTO v_id;
    RETURN v_id;
END $$;

-- Every table carries updated_at maintenance where it has the column.
CREATE FUNCTION touch_updated_at() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN NEW.updated_at := now(); RETURN NEW; END $$;

DO $$
DECLARE t text;
BEGIN
    FOR t IN SELECT table_name FROM information_schema.columns
              WHERE table_schema = 'public' AND column_name = 'updated_at'
    LOOP
        EXECUTE format('CREATE TRIGGER trg_touch_%1$s BEFORE UPDATE ON %1$I FOR EACH ROW EXECUTE FUNCTION touch_updated_at()', t);
    END LOOP;
END $$;
