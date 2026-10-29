-- VECTA Connect | ATLAS | DYNAMIC MARKET INTELLIGENCE — wfc_0013 (29 Oct 2026: relationship intelligence to the ATLAS v1.0
-- parameters, with open-market contact discovery). Additive and idempotent: nothing is dropped and no existing person,
-- evidence, relationship, route, engagement or research row loses a value.
UPDATE schema_meta SET value = 'wfc_0013' WHERE key = 'revision';

-- ------------------------------------------------------------------ people: stakeholder judgements, recorded by a person with a basis
-- Stakeholder type, decision authority and posture are the ATLAS v1.0 parameters. They are judgements, so each carries who
-- recorded it (descriptive), when, and on what basis; "unknown" is the honest default and is never inferred from a title.
ALTER TABLE people ADD COLUMN IF NOT EXISTS stakeholder_type text NOT NULL DEFAULT 'unknown';
ALTER TABLE people DROP CONSTRAINT IF EXISTS people_stakeholder_type_check;
ALTER TABLE people ADD CONSTRAINT people_stakeholder_type_check CHECK (stakeholder_type IN
    ('economic_buyer','budget_holder','programme_sponsor','procurement_authority','political_sponsor','technical_evaluator',
     'technical_influencer','adviser','gatekeeper','introducer','delivery_partner','consultant','unknown'));
ALTER TABLE people ADD COLUMN IF NOT EXISTS decision_authority text NOT NULL DEFAULT 'unknown';
ALTER TABLE people DROP CONSTRAINT IF EXISTS people_decision_authority_check;
ALTER TABLE people ADD CONSTRAINT people_decision_authority_check CHECK (decision_authority IN ('final','shared','influence','none','unknown'));
ALTER TABLE people ADD COLUMN IF NOT EXISTS posture text NOT NULL DEFAULT 'unknown';
ALTER TABLE people DROP CONSTRAINT IF EXISTS people_posture_check;
ALTER TABLE people ADD CONSTRAINT people_posture_check CHECK (posture IN ('champion','supportive','neutral','sceptical','blocker','unknown'));
ALTER TABLE people ADD COLUMN IF NOT EXISTS judgement_basis text;          -- why the type, authority and posture were recorded
ALTER TABLE people ADD COLUMN IF NOT EXISTS judgement_by_label text;       -- who recorded them (descriptive, not a login)
ALTER TABLE people ADD COLUMN IF NOT EXISTS judgement_at timestamptz;
ALTER TABLE people ADD COLUMN IF NOT EXISTS key_interests text;
ALTER TABLE people ADD COLUMN IF NOT EXISTS strategic_account boolean NOT NULL DEFAULT false;   -- the team marks the account as strategic
ALTER TABLE people ADD COLUMN IF NOT EXISTS capability_area text;          -- the WFC capability area a discovered contact was found for
ALTER TABLE people DROP CONSTRAINT IF EXISTS people_capability_area_check;
ALTER TABLE people ADD CONSTRAINT people_capability_area_check CHECK (capability_area IS NULL OR capability_area IN
    ('airline_representation','account_growth','forwarder_sales','capacity_lanes','service_operations','trucking_gateways',
     'outsourcing_training','technology_solutions','network_development'));
ALTER TABLE people DROP CONSTRAINT IF EXISTS people_origin_check;
ALTER TABLE people ADD CONSTRAINT people_origin_check CHECK (origin IN ('manual','import','research','document','discovery'));

-- ------------------------------------------------------------------ engagements: outcome and direction, so health can be measured
-- Outcome gains 'no_response' (an unanswered approach is the most honest responsiveness signal). Direction records whether
-- WFC reached out or the person did. Existing rows keep their values; direction defaults to 'outbound' for them.
ALTER TABLE engagements DROP CONSTRAINT IF EXISTS engagements_outcome_check;
ALTER TABLE engagements ADD CONSTRAINT engagements_outcome_check
    CHECK (outcome IS NULL OR outcome IN ('positive','neutral','negative','no_response','pending'));
ALTER TABLE engagements DROP CONSTRAINT IF EXISTS engagements_kind_check;
ALTER TABLE engagements ADD CONSTRAINT engagements_kind_check
    CHECK (kind IN ('meeting','call','email','proposal','visit','introduction','event','message','note','other'));
ALTER TABLE engagements ADD COLUMN IF NOT EXISTS direction text NOT NULL DEFAULT 'outbound';
ALTER TABLE engagements DROP CONSTRAINT IF EXISTS engagements_direction_check;
ALTER TABLE engagements ADD CONSTRAINT engagements_direction_check CHECK (direction IN ('outbound','inbound','mutual'));
CREATE INDEX IF NOT EXISTS ix_engagements_person_at ON engagements (person_id, occurred_at DESC);

-- ------------------------------------------------------------------ open-market contact discovery
-- A standalone search for contacts (not tied to one tender): by organisation, country or region, WFC capability area and
-- role focus. Reads the organisation's own pages and the authorised web search's results through the same evidence rules
-- as opportunity research; every person it records carries the passage that names them.
CREATE TABLE IF NOT EXISTS contact_discoveries (
    id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organisation_id    uuid REFERENCES organisations(id),
    organisation_label text,
    countries          char(2)[] NOT NULL DEFAULT '{}',
    region_code        text,
    capability_area    text CHECK (capability_area IS NULL OR capability_area IN
        ('airline_representation','account_growth','forwarder_sales','capacity_lanes','service_operations','trucking_gateways',
         'outsourcing_training','technology_solutions','network_development')),
    role_focus         text,
    brief              text NOT NULL,                       -- the brief as run, in plain words
    status             text NOT NULL DEFAULT 'running' CHECK (status IN ('running','finished')),
    outcome            text CHECK (outcome IS NULL OR outcome IN ('people_found','no_people_found','incomplete','not_run')),
    methods            text[] NOT NULL DEFAULT '{}',
    unavailable        jsonb NOT NULL DEFAULT '[]'::jsonb,
    coverage           jsonb NOT NULL DEFAULT '{}'::jsonb,
    searches           jsonb NOT NULL DEFAULT '[]'::jsonb,
    people_found       int NOT NULL DEFAULT 0,
    runs               int NOT NULL DEFAULT 0,
    cost_usd           numeric(10,4) NOT NULL DEFAULT 0,
    started_at         timestamptz NOT NULL DEFAULT now(),
    finished_at        timestamptz,
    requested_by_label text,
    session_ref        text
);
CREATE INDEX IF NOT EXISTS ix_contact_discoveries_started ON contact_discoveries (started_at DESC);

-- People a discovery found, with the relevance to its brief (0–100, every point explained in `relevance`).
CREATE TABLE IF NOT EXISTS discovery_people (
    discovery_id    uuid NOT NULL REFERENCES contact_discoveries(id),
    person_id       uuid NOT NULL REFERENCES people(id),
    relevance_score int NOT NULL DEFAULT 0 CHECK (relevance_score BETWEEN 0 AND 100),
    relevance       jsonb NOT NULL DEFAULT '{}'::jsonb,
    new_record      boolean NOT NULL DEFAULT true,
    added_at        timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (discovery_id, person_id)
);
CREATE INDEX IF NOT EXISTS ix_discovery_people_person ON discovery_people (person_id);

-- Research documents can now belong to a discovery instead of an opportunity.
ALTER TABLE research_documents ALTER COLUMN opportunity_id DROP NOT NULL;
ALTER TABLE research_documents ADD COLUMN IF NOT EXISTS discovery_id uuid REFERENCES contact_discoveries(id);
ALTER TABLE research_documents DROP CONSTRAINT IF EXISTS research_documents_scope_check;
ALTER TABLE research_documents ADD CONSTRAINT research_documents_scope_check
    CHECK ((opportunity_id IS NOT NULL) <> (discovery_id IS NOT NULL));
CREATE UNIQUE INDEX IF NOT EXISTS ux_research_documents_disc_url ON research_documents (discovery_id, url)
    WHERE url IS NOT NULL AND discovery_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_research_documents_discovery ON research_documents (discovery_id, status) WHERE discovery_id IS NOT NULL;

-- ------------------------------------------------------------------ outreach drafts: written by ATLAS, reviewed and sent by a person
-- Nothing is sent by the system. A draft is text a person edits and sends themselves; "sent" is recorded by that person.
CREATE TABLE IF NOT EXISTS outreach_drafts (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    person_id      uuid NOT NULL REFERENCES people(id),
    opportunity_id uuid REFERENCES opportunities(id),
    channel        text NOT NULL DEFAULT 'email' CHECK (channel IN ('email','linkedin_message','call_notes')),
    subject        text,
    body           text NOT NULL,
    source         text NOT NULL CHECK (source IN ('template','ai')),
    basis          jsonb NOT NULL DEFAULT '[]'::jsonb,     -- the recorded facts the draft was written from
    status         text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','sent','discarded')),
    sent_at        timestamptz,
    sent_by_label  text,
    sent_note      text,
    cost_usd       numeric(10,4) NOT NULL DEFAULT 0,
    created_at     timestamptz NOT NULL DEFAULT now(),
    updated_at     timestamptz NOT NULL DEFAULT now(),
    session_ref    text
);
CREATE INDEX IF NOT EXISTS ix_outreach_drafts_person ON outreach_drafts (person_id, created_at DESC);

-- ------------------------------------------------------------------ audit: new actions
-- (audit_log.action is free text in this schema; nothing to alter.)
