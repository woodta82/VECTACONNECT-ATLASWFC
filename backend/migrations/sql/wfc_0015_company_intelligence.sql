-- VECTA Connect | ATLAS | DYNAMIC MARKET INTELLIGENCE — wfc_0015 (29 Oct 2026: four research purposes; company and people
-- intelligence built directly; supplied data awaiting verification). Additive and idempotent.
UPDATE schema_meta SET value = 'wfc_0015' WHERE key = 'revision';

-- ------------------------------------------------------------------ organisations: kinds and profile
ALTER TABLE organisations DROP CONSTRAINT IF EXISTS organisations_kind_check;
ALTER TABLE organisations ADD CONSTRAINT organisations_kind_check CHECK (kind IN
    ('airline','forwarder','gssa','airport_operator','trucking_provider','shipper','handler','technology_provider','charter_broker',
     'integrator','authority','other'));
ALTER TABLE organisations ADD COLUMN IF NOT EXISTS origin text NOT NULL DEFAULT 'manual';
ALTER TABLE organisations DROP CONSTRAINT IF EXISTS organisations_origin_check;
ALTER TABLE organisations ADD CONSTRAINT organisations_origin_check CHECK (origin IN ('manual','import','research','discovery','supplied'));
ALTER TABLE organisations ADD COLUMN IF NOT EXISTS description text;
ALTER TABLE organisations ADD COLUMN IF NOT EXISTS services_text text;          -- what it does, as stated by a source
ALTER TABLE organisations ADD COLUMN IF NOT EXISTS locations_text text;         -- offices, stations, airports, as stated
ALTER TABLE organisations ADD COLUMN IF NOT EXISTS parent_group text;            -- parent or group, as stated
ALTER TABLE organisations ADD COLUMN IF NOT EXISTS airport_iata char(3);        -- the airport the record is associated with (e.g. a station list)
ALTER TABLE organisations ADD COLUMN IF NOT EXISTS carrier_type text;           -- airlines: how they carry cargo
ALTER TABLE organisations DROP CONSTRAINT IF EXISTS organisations_carrier_type_check;
ALTER TABLE organisations ADD CONSTRAINT organisations_carrier_type_check
    CHECK (carrier_type IS NULL OR carrier_type IN ('passenger_belly','cargo_only','combination','unknown'));
ALTER TABLE organisations ADD COLUMN IF NOT EXISTS supplied_at timestamptz;      -- came from a supplied dataset: awaiting verification
ALTER TABLE organisations ADD COLUMN IF NOT EXISTS verified_at timestamptz;      -- a person checked the record against current sources
ALTER TABLE organisations ADD COLUMN IF NOT EXISTS verification_basis text;
ALTER TABLE organisations ADD COLUMN IF NOT EXISTS last_researched_at timestamptz;
ALTER TABLE organisations ADD COLUMN IF NOT EXISTS capability_areas text[] NOT NULL DEFAULT '{}';
CREATE INDEX IF NOT EXISTS ix_organisations_country_kind ON organisations (country, kind) WHERE merged_into_id IS NULL;
CREATE INDEX IF NOT EXISTS ix_organisations_airport ON organisations (airport_iata) WHERE airport_iata IS NOT NULL;

-- Published contact addresses: each with where it was published (a page on the organisation's own site, a directory, a supplied
-- sheet). Supplied addresses are never shown as current until verified.
CREATE TABLE IF NOT EXISTS organisation_contacts (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organisation_id uuid NOT NULL REFERENCES organisations(id),
    kind            text NOT NULL DEFAULT 'email' CHECK (kind IN ('email','phone')),
    value           text NOT NULL,
    purpose         text,                                   -- e.g. cargo sales, reservations, station, as stated
    status          text NOT NULL DEFAULT 'supplied' CHECK (status IN ('supplied','published','verified','lapsed')),
    source_url      text,
    source_note     text,
    evidence_id     uuid,
    observed_at     timestamptz NOT NULL DEFAULT now(),
    verified_at     timestamptz,
    session_ref     text
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_organisation_contacts ON organisation_contacts (organisation_id, kind, lower(value));

-- Evidence for what is recorded about an organisation (same discipline as person_evidence).
CREATE TABLE IF NOT EXISTS organisation_evidence (
    id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organisation_id      uuid NOT NULL REFERENCES organisations(id),
    supports             text NOT NULL CHECK (supports IN ('identity','kind','website','email','location','service','parent','representation',
                                                           'carrier_type','relevance','note')),
    source_kind          text NOT NULL CHECK (source_kind IN ('research_document','public_page','note','supplied')),
    research_document_id uuid REFERENCES research_documents(id),
    url                  text,
    quote                text,
    note                 text,
    supplied_import_id   uuid,
    observed_at          timestamptz NOT NULL DEFAULT now(),
    session_ref          text
);
CREATE INDEX IF NOT EXISTS ix_organisation_evidence_org ON organisation_evidence (organisation_id);
CREATE UNIQUE INDEX IF NOT EXISTS ux_organisation_evidence_passage ON organisation_evidence
    (organisation_id, supports, source_kind, coalesce(research_document_id::text, ''), coalesce(url, ''), md5(coalesce(quote, '')), md5(coalesce(note, '')))
    WHERE source_kind <> 'note';

-- Representation and business relationships between organisations: an agent (GSA/GSSA/handler) acting for an airline, a partnership.
-- Cargo representation is kept apart from passenger-ticket-sales mandates. "supplied" = from a supplied dataset, awaiting verification.
CREATE TABLE IF NOT EXISTS organisation_relationships (
    id                      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organisation_id         uuid NOT NULL REFERENCES organisations(id),        -- the agent, handler or partner
    counterparty_id         uuid REFERENCES organisations(id),                 -- the airline or partner, when a record exists
    counterparty_code       text,                                              -- IATA code as written (e.g. 'LO')
    counterparty_label      text,                                              -- name as written
    relationship            text NOT NULL CHECK (relationship IN ('cargo_representation','passenger_representation','representation_unspecified',
                                                                  'handling','trucking','partnership','parent','other')),
    territory_countries     char(2)[] NOT NULL DEFAULT '{}',
    airport_iata            char(3),
    status                  text NOT NULL DEFAULT 'supplied' CHECK (status IN ('supplied','sourced','confirmed','lapsed','not_established')),
    basis                   text NOT NULL,
    evidence_id             uuid REFERENCES organisation_evidence(id),
    observed_at             timestamptz NOT NULL DEFAULT now(),
    verified_at             timestamptz,
    verified_by_label       text,
    session_ref             text
);
CREATE INDEX IF NOT EXISTS ix_org_relationships_org ON organisation_relationships (organisation_id);
CREATE INDEX IF NOT EXISTS ix_org_relationships_counterparty ON organisation_relationships (counterparty_id);
CREATE UNIQUE INDEX IF NOT EXISTS ux_org_relationships ON organisation_relationships
    (organisation_id, relationship, coalesce(counterparty_id::text, ''), coalesce(upper(counterparty_code), ''), coalesce(lower(counterparty_label), ''),
     coalesce(airport_iata, ''));

-- ------------------------------------------------------------------ supplied datasets (e.g. a station's GSA list)
CREATE TABLE IF NOT EXISTS supplied_imports (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name           text NOT NULL,
    filename       text,
    sha256         text,
    airport_iata   char(3),
    country        char(2),
    notes          text,
    rows_total     int NOT NULL DEFAULT 0,
    organisations  int NOT NULL DEFAULT 0,
    relationships  int NOT NULL DEFAULT 0,
    contacts       int NOT NULL DEFAULT 0,
    imported_at    timestamptz NOT NULL DEFAULT now(),
    imported_by    text,
    session_ref    text
);
CREATE TABLE IF NOT EXISTS supplied_rows (
    id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    import_id          uuid NOT NULL REFERENCES supplied_imports(id),
    sheet              text,
    row_number         int,
    raw                jsonb NOT NULL,
    organisation_id    uuid REFERENCES organisations(id),
    note               text
);
CREATE INDEX IF NOT EXISTS ix_supplied_rows_import ON supplied_rows (import_id);

-- ------------------------------------------------------------------ research purposes and briefs
-- Discovery searches (Discover) carry the purpose and a plain-language brief. Contact discoveries (open-market research) carry the
-- purpose too: 'people' (as before) or 'companies'.
ALTER TABLE discovery_searches ADD COLUMN IF NOT EXISTS purpose text NOT NULL DEFAULT 'opportunities';
ALTER TABLE discovery_searches DROP CONSTRAINT IF EXISTS discovery_searches_purpose_check;
ALTER TABLE discovery_searches ADD CONSTRAINT discovery_searches_purpose_check CHECK (purpose IN ('opportunities','market'));
ALTER TABLE discovery_searches ADD COLUMN IF NOT EXISTS brief text;
ALTER TABLE contact_discoveries ADD COLUMN IF NOT EXISTS purpose text NOT NULL DEFAULT 'people';
ALTER TABLE contact_discoveries DROP CONSTRAINT IF EXISTS contact_discoveries_purpose_check;
ALTER TABLE contact_discoveries ADD CONSTRAINT contact_discoveries_purpose_check CHECK (purpose IN ('people','companies'));
ALTER TABLE contact_discoveries ADD COLUMN IF NOT EXISTS brief_text text;
ALTER TABLE contact_discoveries ADD COLUMN IF NOT EXISTS airport_iata char(3);
ALTER TABLE contact_discoveries ADD COLUMN IF NOT EXISTS organisation_kinds text[] NOT NULL DEFAULT '{}';

CREATE TABLE IF NOT EXISTS discovery_organisations (
    discovery_id    uuid NOT NULL REFERENCES contact_discoveries(id),
    organisation_id uuid NOT NULL REFERENCES organisations(id),
    relevance_score int NOT NULL DEFAULT 0 CHECK (relevance_score BETWEEN 0 AND 100),
    relevance       jsonb NOT NULL DEFAULT '{}'::jsonb,
    new_record      boolean NOT NULL DEFAULT true,
    added_at        timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (discovery_id, organisation_id)
);
CREATE INDEX IF NOT EXISTS ix_discovery_organisations_org ON discovery_organisations (organisation_id);

-- Opportunities created from a researched company or a market signal carry the interpretation that led to them.
ALTER TABLE opportunities ADD COLUMN IF NOT EXISTS origin_organisation_id uuid REFERENCES organisations(id);
ALTER TABLE opportunities ADD COLUMN IF NOT EXISTS origin_interpretation text;

-- Company discoveries finish with their own outcomes.
ALTER TABLE contact_discoveries DROP CONSTRAINT IF EXISTS contact_discoveries_outcome_check;
ALTER TABLE contact_discoveries ADD CONSTRAINT contact_discoveries_outcome_check
    CHECK (outcome IS NULL OR outcome IN ('people_found','no_people_found','incomplete','not_run','companies_found','no_companies_found'));
