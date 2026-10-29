-- VECTA Connect | ATLAS | DYNAMIC MARKET INTELLIGENCE — wfc_0011 (28 Oct 2026: refocus on global opportunity discovery and
-- relationship intelligence). Additive and idempotent: nothing is dropped, every existing opportunity, contact, engagement,
-- evidence record and history row is kept. Existing values are carried into the new fields as described inline.
UPDATE schema_meta SET value = 'wfc_0011' WHERE key = 'revision';

-- ------------------------------------------------------------------ opportunities: record type, progress, light workspace
-- Record type: a tender or procurement opportunity, or a commercial opportunity (a potential the team chose to track, or one
-- derived from WFC's own records). Market signals and historical intelligence stay as signals and are listed beside them.
ALTER TABLE opportunities ADD COLUMN IF NOT EXISTS record_type text NOT NULL DEFAULT 'tender';
ALTER TABLE opportunities DROP CONSTRAINT IF EXISTS opportunities_record_type_check;
ALTER TABLE opportunities ADD CONSTRAINT opportunities_record_type_check CHECK (record_type IN ('tender','commercial'));
UPDATE opportunities SET record_type = 'commercial' WHERE origin_ref IS NOT NULL AND record_type <> 'commercial';

-- Progress flow New -> Reviewing -> Pursuing -> On hold -> Closed (the earlier, longer stage list is kept in commercial_stage
-- and its history; progress is carried over from it).
ALTER TABLE opportunities ADD COLUMN IF NOT EXISTS progress text;
UPDATE opportunities SET progress = CASE commercial_stage
        WHEN 'new' THEN 'new' WHEN 'reviewing' THEN 'reviewing' WHEN 'qualified' THEN 'reviewing'
        WHEN 'pursuing' THEN 'pursuing' WHEN 'proposal' THEN 'pursuing' WHEN 'negotiation' THEN 'pursuing'
        WHEN 'deferred' THEN 'on_hold' ELSE 'closed' END
 WHERE progress IS NULL;
ALTER TABLE opportunities ALTER COLUMN progress SET DEFAULT 'new';
ALTER TABLE opportunities ALTER COLUMN progress SET NOT NULL;
ALTER TABLE opportunities DROP CONSTRAINT IF EXISTS opportunities_progress_check;
ALTER TABLE opportunities ADD CONSTRAINT opportunities_progress_check CHECK (progress IN ('new','reviewing','pursuing','on_hold','closed'));
ALTER TABLE opportunities ADD COLUMN IF NOT EXISTS closed_reason text;
UPDATE opportunities SET closed_reason = commercial_stage
 WHERE progress = 'closed' AND closed_reason IS NULL AND commercial_stage IN ('won','lost','expired');
CREATE INDEX IF NOT EXISTS ix_opportunities_progress ON opportunities (progress);

-- A descriptive owner (free text in the shared workspace, never a login), a saved flag and the next action.
ALTER TABLE opportunities ADD COLUMN IF NOT EXISTS owner_label text;
UPDATE opportunities o SET owner_label = p.full_name FROM people p WHERE p.id = o.owner_person_id AND o.owner_label IS NULL;
ALTER TABLE opportunities ADD COLUMN IF NOT EXISTS saved_at timestamptz;
ALTER TABLE opportunities ADD COLUMN IF NOT EXISTS next_action text;
ALTER TABLE opportunities ADD COLUMN IF NOT EXISTS next_action_due date;

CREATE TABLE IF NOT EXISTS opportunity_notes (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    opportunity_id uuid NOT NULL REFERENCES opportunities(id),
    body           text NOT NULL CHECK (length(trim(body)) >= 2),
    author_label   text,
    session_ref    text,
    created_at     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_opportunity_notes_opp ON opportunity_notes (opportunity_id, created_at);

ALTER TABLE opportunity_status_history DROP CONSTRAINT IF EXISTS opportunity_status_history_field_check;
ALTER TABLE opportunity_status_history ADD CONSTRAINT opportunity_status_history_field_check
    CHECK (field IN ('commercial_stage','qualification_status','deadline','tender_status','scope','owner','merge','eligibility_evidence','evidence',
                     'freight_scope','capability_area','progress','saved','next_action','record_type'));

-- A market signal the team decides to track becomes a commercial opportunity; the link keeps the signal's evidence.
ALTER TABLE opportunities ADD COLUMN IF NOT EXISTS tracked_from_signal_id uuid REFERENCES signals(id);

-- ------------------------------------------------------------------ people: research state facts
-- The state shown (research candidate, identity and role confirmed, existing relationship, introduction available) is DERIVED
-- from these facts and the relationship tables; it is never typed in directly.
ALTER TABLE people ADD COLUMN IF NOT EXISTS origin text NOT NULL DEFAULT 'manual';
ALTER TABLE people DROP CONSTRAINT IF EXISTS people_origin_check;
ALTER TABLE people ADD CONSTRAINT people_origin_check CHECK (origin IN ('manual','import','research','document'));
UPDATE people SET origin = 'import' WHERE external_id IS NOT NULL AND origin = 'manual';
ALTER TABLE people ADD COLUMN IF NOT EXISTS organisation_label text;          -- when the organisation is not yet a record
ALTER TABLE people ADD COLUMN IF NOT EXISTS remit_text text;                  -- geographic remit, as established
ALTER TABLE people ADD COLUMN IF NOT EXISTS remit_countries char(2)[];
ALTER TABLE people ADD COLUMN IF NOT EXISTS remit_basis text;
ALTER TABLE people ADD COLUMN IF NOT EXISTS identity_confirmed_at timestamptz;
ALTER TABLE people ADD COLUMN IF NOT EXISTS identity_basis text;
ALTER TABLE people ADD COLUMN IF NOT EXISTS last_verified_at timestamptz;
ALTER TABLE people ADD COLUMN IF NOT EXISTS linkedin_profile_url text;       -- only a profile a person confirmed
ALTER TABLE people ADD COLUMN IF NOT EXISTS linkedin_confirmed_at timestamptz;
ALTER TABLE people ADD COLUMN IF NOT EXISTS relationship_owner text;          -- descriptive, within the shared workspace
ALTER TABLE people ADD COLUMN IF NOT EXISTS notes text;
ALTER TABLE people ADD COLUMN IF NOT EXISTS next_action text;
ALTER TABLE people ADD COLUMN IF NOT EXISTS next_action_due date;
ALTER TABLE people ADD COLUMN IF NOT EXISTS updated_at timestamptz NOT NULL DEFAULT now();
ALTER TABLE people DROP CONSTRAINT IF EXISTS people_linkedin_profile_check;
ALTER TABLE people ADD CONSTRAINT people_linkedin_profile_check CHECK (
    linkedin_profile_url IS NULL OR (linkedin_profile_url ~ '^https://([a-z]{2,3}\.)?linkedin\.com/in/[^/?#]+/?$' AND linkedin_confirmed_at IS NOT NULL));
-- Contacts imported from WFC's own relationship records were identified by WFC: their identity is carried over as confirmed,
-- with that basis recorded. Research candidates are never created by this migration.
UPDATE people SET identity_confirmed_at = coalesce(identity_confirmed_at, created_at),
                  identity_basis = coalesce(identity_basis, 'Imported from WFC relationship records before the 28 Oct 2026 upgrade'),
                  last_verified_at = coalesce(last_verified_at, created_at)
 WHERE origin = 'import' AND is_internal = false;

-- Evidence for a person's identity, role, remit or relevance (a source passage, a public page, or a recorded note).
CREATE TABLE IF NOT EXISTS person_evidence (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    person_id     uuid NOT NULL REFERENCES people(id),
    supports      text NOT NULL CHECK (supports IN ('identity','role','remit','relevance','relationship','introduction')),
    source_kind   text NOT NULL CHECK (source_kind IN ('source_document','public_page','note')),
    document_id   uuid REFERENCES source_documents(id),
    url           text CHECK (url IS NULL OR url ~ '^https?://'),
    quote         text,
    note          text,
    observed_at   timestamptz NOT NULL DEFAULT now(),
    session_ref   text,
    CHECK (source_kind <> 'source_document' OR document_id IS NOT NULL),
    CHECK (source_kind <> 'public_page' OR url IS NOT NULL),
    CHECK (coalesce(quote, note) IS NOT NULL)
);
CREATE INDEX IF NOT EXISTS ix_person_evidence_person ON person_evidence (person_id);

-- People linked to an opportunity, with WHY they appear relevant. Being named in an announcement is evidence of involvement,
-- not of decision-making authority: `relevance_basis` records what the evidence actually shows.
CREATE TABLE IF NOT EXISTS opportunity_people (
    opportunity_id  uuid NOT NULL REFERENCES opportunities(id),
    person_id       uuid NOT NULL REFERENCES people(id),
    role_on_opportunity text NOT NULL DEFAULT 'unknown' CHECK (role_on_opportunity IN
        ('procurement_contact','commercial_leader','decision_maker','department_lead','regional_representative','partner',
         'named_in_source','unknown')),
    relevance_basis text NOT NULL,
    status          text NOT NULL DEFAULT 'candidate' CHECK (status IN ('candidate','relevant','not_relevant')),
    added_at        timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (opportunity_id, person_id)
);

-- An existing relationship: someone at WFC (described, not a login) who knows this person, and on what basis.
CREATE TABLE IF NOT EXISTS person_relationships (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    person_id     uuid NOT NULL REFERENCES people(id),
    holder_label  text NOT NULL CHECK (length(trim(holder_label)) >= 2),   -- who at WFC holds the relationship
    nature        text NOT NULL CHECK (nature IN ('works_with','former_colleague','client','supplier','partner','personal','other')),
    basis         text NOT NULL CHECK (length(trim(basis)) >= 10),          -- how it is known (meetings, contract, ...)
    status        text NOT NULL DEFAULT 'current' CHECK (status IN ('current','lapsed')),
    recorded_at   timestamptz NOT NULL DEFAULT now(),
    session_ref   text
);
CREATE INDEX IF NOT EXISTS ix_person_relationships_person ON person_relationships (person_id);

-- An introduction route to a target person. A public association (same board, same press release) is at most a POSSIBLE
-- route; it is "available" only when the introducer's relationship and willingness are confirmed and recorded.
CREATE TABLE IF NOT EXISTS introduction_routes (
    id                     uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    target_person_id       uuid NOT NULL REFERENCES people(id),
    opportunity_id         uuid REFERENCES opportunities(id),
    introducer_person_id   uuid REFERENCES people(id),
    introducer_label       text,                                     -- when the introducer is not a person record
    wfc_holder_label       text,                                     -- who at WFC would ask the introducer
    connection_basis       text NOT NULL CHECK (length(trim(connection_basis)) >= 10),
    evidence_url           text CHECK (evidence_url IS NULL OR evidence_url ~ '^https?://'),
    willingness_confirmed  boolean NOT NULL DEFAULT false,
    willingness_basis      text,
    status                 text NOT NULL DEFAULT 'possible' CHECK (status IN ('possible','available','requested','made','declined')),
    notes                  text,
    created_at             timestamptz NOT NULL DEFAULT now(),
    updated_at             timestamptz NOT NULL DEFAULT now(),
    session_ref            text,
    CHECK (introducer_person_id IS NOT NULL OR introducer_label IS NOT NULL),
    CHECK (status NOT IN ('available','requested','made') OR (willingness_confirmed AND length(trim(coalesce(willingness_basis,''))) >= 10))
);
CREATE INDEX IF NOT EXISTS ix_intro_routes_target ON introduction_routes (target_person_id);

-- Engagement history: keep the existing table; add who recorded it (descriptive), the outcome and the next step.
ALTER TABLE engagements ADD COLUMN IF NOT EXISTS owner_label text;
ALTER TABLE engagements ADD COLUMN IF NOT EXISTS outcome text CHECK (outcome IS NULL OR outcome IN ('positive','neutral','negative','pending'));
ALTER TABLE engagements ADD COLUMN IF NOT EXISTS next_step text;
ALTER TABLE engagements ADD COLUMN IF NOT EXISTS session_ref text;

-- Contacts with engagement history recorded before this upgrade: the history itself is the recorded relationship basis.
INSERT INTO person_relationships (person_id, holder_label, nature, basis, status, recorded_at)
SELECT p.id, 'WFC (recorded before the 28 Oct 2026 upgrade)', 'other',
       'Engagement history recorded in ATLAS before the upgrade: ' || count(e.id) || ' engagement(s), latest ' ||
       to_char(max(e.occurred_at) AT TIME ZONE 'UTC', 'YYYY-MM-DD'), 'current', now()
  FROM people p JOIN engagements e ON e.person_id = p.id
 WHERE p.is_internal = false
   AND NOT EXISTS (SELECT 1 FROM person_relationships r WHERE r.person_id = p.id)
 GROUP BY p.id;

-- Relationship research runs for an opportunity: what was searched, how, and what remains unknown.
CREATE TABLE IF NOT EXISTS relationship_research_runs (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    opportunity_id  uuid NOT NULL REFERENCES opportunities(id),
    methods         text[] NOT NULL,           -- source_documents, configured_extractor, web_research
    unavailable     jsonb NOT NULL DEFAULT '[]'::jsonb,   -- methods that could not run, with the reason
    organisations   jsonb NOT NULL DEFAULT '[]'::jsonb,
    target_roles    jsonb NOT NULL DEFAULT '[]'::jsonb,
    candidates_found int NOT NULL DEFAULT 0,
    gaps            jsonb NOT NULL DEFAULT '[]'::jsonb,
    cost_usd        numeric(12,6) NOT NULL DEFAULT 0,
    started_at      timestamptz NOT NULL DEFAULT now(),
    finished_at     timestamptz,
    session_ref     text
);
CREATE INDEX IF NOT EXISTS ix_research_runs_opp ON relationship_research_runs (opportunity_id, started_at DESC);

-- ------------------------------------------------------------------ derived views (recreated on every run)
-- A person's research state, derived from recorded facts (domain/relationships.derive_state applies the same order).
CREATE OR REPLACE VIEW person_state AS
SELECT p.id AS person_id,
       (SELECT count(*) FROM person_relationships r WHERE r.person_id = p.id AND r.status = 'current') AS current_relationships,
       (SELECT count(*) FROM introduction_routes i WHERE i.target_person_id = p.id AND i.status IN ('available','requested','made'))
           AS available_routes,
       (SELECT count(*) FROM introduction_routes i WHERE i.target_person_id = p.id AND i.status = 'possible') AS possible_routes,
       CASE WHEN EXISTS (SELECT 1 FROM person_relationships r WHERE r.person_id = p.id AND r.status = 'current') THEN 'existing_relationship'
            WHEN EXISTS (SELECT 1 FROM introduction_routes i WHERE i.target_person_id = p.id AND i.status IN ('available','requested','made'))
                 THEN 'introduction_available'
            WHEN p.identity_confirmed_at IS NOT NULL THEN 'identity_confirmed'
            ELSE 'research_candidate' END AS state
  FROM people p
 WHERE NOT p.is_internal;

-- Relationship coverage of an opportunity: people linked to it, plus people at its organisation (a relationship with
-- someone at the issuing airline counts for every opportunity that airline issues).
CREATE OR REPLACE VIEW opportunity_relationship_coverage AS
WITH linked AS (
    SELECT o.id AS opportunity_id, ps.person_id, ps.state
      FROM opportunities o
      JOIN opportunity_people op ON op.opportunity_id = o.id AND op.status <> 'not_relevant'
      JOIN person_state ps ON ps.person_id = op.person_id
    UNION
    SELECT o.id, ps.person_id, ps.state
      FROM opportunities o
      JOIN people p ON p.organisation_id = coalesce(o.airline_id, o.organisation_id) AND NOT p.is_internal
      JOIN person_state ps ON ps.person_id = p.id
     WHERE ps.state <> 'research_candidate'
)
SELECT o.id AS opportunity_id,
       count(l.person_id) AS people,
       count(l.person_id) FILTER (WHERE l.state = 'research_candidate') AS candidates,
       count(l.person_id) FILTER (WHERE l.state <> 'research_candidate') AS confirmed,
       count(l.person_id) FILTER (WHERE l.state = 'existing_relationship') AS with_relationship,
       count(l.person_id) FILTER (WHERE l.state = 'introduction_available') AS with_introduction,
       CASE WHEN count(l.person_id) FILTER (WHERE l.state = 'existing_relationship') > 0 THEN 'existing_relationship'
            WHEN count(l.person_id) FILTER (WHERE l.state = 'introduction_available') > 0 THEN 'introduction_available'
            WHEN count(l.person_id) FILTER (WHERE l.state <> 'research_candidate') > 0 THEN 'people_confirmed'
            WHEN count(l.person_id) > 0 THEN 'candidates_only'
            ELSE 'none' END AS level,
       (SELECT max(r.started_at) FROM relationship_research_runs r WHERE r.opportunity_id = o.id) AS last_researched_at
  FROM opportunities o LEFT JOIN linked l ON l.opportunity_id = o.id
 GROUP BY o.id;
