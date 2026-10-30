-- VECTA Connect | ATLAS | DYNAMIC MARKET INTELLIGENCE — wfc_0016 (30 Oct 2026: one workspace; staged research; global airport
-- directory; cargo scope; canonical company and person records). Additive and idempotent. Nothing is deleted.
UPDATE schema_meta SET value = 'wfc_0016' WHERE key = 'revision';

-- ------------------------------------------------------------------ reference datasets and the global airport directory
CREATE TABLE IF NOT EXISTS reference_datasets (
    key          text PRIMARY KEY,
    name         text NOT NULL,
    source       text NOT NULL,                -- where the data comes from (publisher, file)
    url          text,
    licence      text,
    version      text,                         -- the dataset's own version or the date of the file
    refreshed_at timestamptz,                  -- when the dataset was refreshed by its publisher (as stated by the file or the loader)
    loaded_at    timestamptz NOT NULL DEFAULT now(),
    rows_loaded  int NOT NULL DEFAULT 0,
    notes        text
);

-- The directory: every airport of the maintained dataset, with or without an IATA code. `ident` is the dataset's stable identifier
-- (the ICAO code where one exists, otherwise the dataset's local identifier). The WFC `airports` table (stations used by WFC data)
-- is untouched. Presence here never means an airport handles cargo.
CREATE TABLE IF NOT EXISTS airport_directory (
    ident              text PRIMARY KEY,
    iata               char(3),
    icao               char(4),
    name               text NOT NULL,
    city               text,
    country            char(2) NOT NULL,
    region_code        text,                   -- ISO 3166-2 where the dataset gives it
    type               text NOT NULL DEFAULT 'unknown',   -- large_airport, medium_airport, small_airport, heliport, seaplane_base, closed, unknown
    status             text NOT NULL DEFAULT 'unknown' CHECK (status IN ('open','closed','unknown')),
    scheduled_service  boolean,
    latitude           numeric(9,6),
    longitude          numeric(9,6),
    aliases            text[] NOT NULL DEFAULT '{}',      -- other names and keywords from the dataset
    source_key         text NOT NULL REFERENCES reference_datasets(key),
    source_id          text,                              -- the dataset's own id for the row
    refreshed_at       timestamptz,
    search_text        text GENERATED ALWAYS AS (lower(coalesce(iata, '') || ' ' || coalesce(icao, '') || ' ' || ident || ' ' || name || ' ' || coalesce(city, '') || ' ' || country)) STORED
);
CREATE INDEX IF NOT EXISTS ix_airport_directory_iata ON airport_directory (iata) WHERE iata IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_airport_directory_country ON airport_directory (country, type);
CREATE INDEX IF NOT EXISTS ix_airport_directory_search ON airport_directory (search_text text_pattern_ops);

-- ------------------------------------------------------------------ airport scope on research, companies and opportunities
ALTER TABLE discovery_searches ADD COLUMN IF NOT EXISTS airports text[] NOT NULL DEFAULT '{}';      -- directory idents
ALTER TABLE contact_discoveries ADD COLUMN IF NOT EXISTS airports text[] NOT NULL DEFAULT '{}';

-- Where an organisation is and what it serves are different facts: an office, a station it operates, an airport it serves from
-- elsewhere, a hub or gateway. Each entry carries its status and basis.
CREATE TABLE IF NOT EXISTS organisation_airports (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organisation_id uuid NOT NULL REFERENCES organisations(id),
    airport_ident   text NOT NULL,
    role            text NOT NULL CHECK (role IN ('office','station','served','gateway','hub','destination')),
    status          text NOT NULL DEFAULT 'sourced' CHECK (status IN ('supplied','sourced','confirmed','lapsed')),
    basis           text NOT NULL,
    evidence_id     uuid REFERENCES organisation_evidence(id),
    observed_at     timestamptz NOT NULL DEFAULT now(),
    verified_at     timestamptz,
    session_ref     text
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_organisation_airports ON organisation_airports (organisation_id, airport_ident, role);

CREATE TABLE IF NOT EXISTS opportunity_airports (
    opportunity_id uuid NOT NULL REFERENCES opportunities(id) ON DELETE CASCADE,
    airport_ident  text NOT NULL,
    role           text NOT NULL CHECK (role IN ('scope','origin','destination','gateway','station')),
    support        text NOT NULL DEFAULT 'supported' CHECK (support IN ('supported','unverified','internal_record')),
    basis          text,
    PRIMARY KEY (opportunity_id, airport_ident, role)
);

-- ------------------------------------------------------------------ cargo scope and canonical company records
ALTER TABLE organisations ADD COLUMN IF NOT EXISTS freight_scope text NOT NULL DEFAULT 'unresolved';
ALTER TABLE organisations DROP CONSTRAINT IF EXISTS organisations_freight_scope_check;
ALTER TABLE organisations ADD CONSTRAINT organisations_freight_scope_check
    CHECK (freight_scope IN ('freighter','belly','mixed','cargo_services','passenger_only','unresolved'));
ALTER TABLE organisations ADD COLUMN IF NOT EXISTS freight_scope_basis text;
ALTER TABLE organisations ADD COLUMN IF NOT EXISTS contact_url text;
ALTER TABLE organisations ADD COLUMN IF NOT EXISTS website_basis text;                -- why the website is believed official
ALTER TABLE organisations ADD COLUMN IF NOT EXISTS research_status jsonb NOT NULL DEFAULT '{}'::jsonb;   -- per field: status, searched_at, detail
ALTER TABLE organisation_contacts ADD COLUMN IF NOT EXISTS department text;           -- cargo sales, reservations, operations, claims…

-- Duplicate review and reversible merges for organisations (the same discipline as people).
CREATE TABLE IF NOT EXISTS company_duplicates (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    left_id     uuid NOT NULL REFERENCES organisations(id),
    right_id    uuid NOT NULL REFERENCES organisations(id),
    reason      text NOT NULL,
    status      text NOT NULL DEFAULT 'open' CHECK (status IN ('open','dismissed','merged')),
    note        text,
    created_at  timestamptz NOT NULL DEFAULT now(),
    resolved_at timestamptz,
    session_ref text,
    CHECK (left_id <> right_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_company_duplicates ON company_duplicates (least(left_id, right_id), greatest(left_id, right_id));
CREATE TABLE IF NOT EXISTS company_merge_log (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    keep_id    uuid NOT NULL REFERENCES organisations(id),
    merged_id  uuid NOT NULL REFERENCES organisations(id),
    note       text,
    moved      jsonb NOT NULL DEFAULT '{}'::jsonb,       -- what was re-pointed, so the merge can be undone
    merged_at  timestamptz NOT NULL DEFAULT now(),
    undone_at  timestamptz,
    session_ref text
);

-- ------------------------------------------------------------------ people: published professional e-mail, research status
ALTER TABLE people ADD COLUMN IF NOT EXISTS published_email text;
ALTER TABLE people ADD COLUMN IF NOT EXISTS published_email_status text;
ALTER TABLE people DROP CONSTRAINT IF EXISTS people_published_email_status_check;
ALTER TABLE people ADD CONSTRAINT people_published_email_status_check
    CHECK (published_email_status IS NULL OR published_email_status IN ('published','verified','lapsed'));
ALTER TABLE people ADD COLUMN IF NOT EXISTS published_email_source_url text;
ALTER TABLE people ADD COLUMN IF NOT EXISTS research_status jsonb NOT NULL DEFAULT '{}'::jsonb;

-- ------------------------------------------------------------------ staged, resumable research
-- One row per entity and stage: identify → official identity → company → people → relationships → commercial relevance.
CREATE TABLE IF NOT EXISTS research_stages (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_type text NOT NULL CHECK (entity_type IN ('opportunity','organisation','person')),
    entity_id   uuid NOT NULL,
    stage       text NOT NULL CHECK (stage IN ('identify','identity','company','people','relationships','relevance')),
    status      text NOT NULL DEFAULT 'not_run' CHECK (status IN ('not_run','running','done','incomplete','failed','not_applicable')),
    detail      text,
    counts      jsonb NOT NULL DEFAULT '{}'::jsonb,
    attempts    int NOT NULL DEFAULT 0,
    started_at  timestamptz,
    finished_at timestamptz,
    session_ref text
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_research_stages ON research_stages (entity_type, entity_id, stage);
CREATE INDEX IF NOT EXISTS ix_research_stages_entity ON research_stages (entity_type, entity_id);

-- Research documents can belong to an organisation's own research (not an opportunity, not a discovery).
ALTER TABLE research_documents ADD COLUMN IF NOT EXISTS research_organisation_id uuid REFERENCES organisations(id);
CREATE INDEX IF NOT EXISTS ix_research_documents_org_research ON research_documents (research_organisation_id) WHERE research_organisation_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS ux_research_documents_org_url ON research_documents (research_organisation_id, url)
    WHERE url IS NOT NULL AND research_organisation_id IS NOT NULL;
-- A research document belongs to exactly one scope: an opportunity, a discovery, or a company's own research.
ALTER TABLE research_documents DROP CONSTRAINT IF EXISTS research_documents_scope_check;
ALTER TABLE research_documents ADD CONSTRAINT research_documents_scope_check
    CHECK ((opportunity_id IS NOT NULL)::int + (discovery_id IS NOT NULL)::int + (research_organisation_id IS NOT NULL)::int = 1);
