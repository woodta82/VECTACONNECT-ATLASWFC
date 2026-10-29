-- VECTA Connect | ATLAS | DYNAMIC MARKET INTELLIGENCE — wfc_0012 (28 Oct 2026, second continuation: complete, evidence-backed
-- relationship research). Additive and idempotent: nothing is dropped and no existing person, evidence record, relationship,
-- route, engagement or history row is changed except as stated inline.
UPDATE schema_meta SET value = 'wfc_0012' WHERE key = 'revision';

-- ------------------------------------------------------------------ organisations: research pages
-- A newsroom or leadership page a person records for an organisation; research reads it and follows its links.
ALTER TABLE organisations ADD COLUMN IF NOT EXISTS newsroom_url text;
ALTER TABLE organisations ADD COLUMN IF NOT EXISTS leadership_url text;

-- ------------------------------------------------------------------ what research read, could not read, or has still to read
CREATE TABLE IF NOT EXISTS research_documents (
    id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    opportunity_id     uuid NOT NULL REFERENCES opportunities(id),
    organisation_id    uuid REFERENCES organisations(id),
    origin             text NOT NULL CHECK (origin IN ('opportunity_source','user_url','user_document','search_result',
                                                       'organisation_page','followed_link','guessed_page')),
    url                text CHECK (url IS NULL OR url ~ '^https?://'),
    source_document_id uuid REFERENCES source_documents(id),
    title              text,
    page_kind          text NOT NULL DEFAULT 'other' CHECK (page_kind IN ('leadership','news','other','document')),
    found_via          text,                                   -- the search query, the link text, or who added it
    status             text NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','read','partial','failed','skipped')),
    status_reason      text,
    body_text          text,                                   -- retained so reading can resume (public pages, supplied documents)
    content_sha256     text,
    sections_total     int NOT NULL DEFAULT 0,
    sections_read      int NOT NULL DEFAULT 0,                 -- read by the rules
    ai_status          text NOT NULL DEFAULT 'not_run' CHECK (ai_status IN ('not_run','not_connected','partial','complete',
                                                                             'budget_refused','failed')),
    ai_sections_read   int NOT NULL DEFAULT 0,                 -- read by the configured AI extractor
    people_found       int NOT NULL DEFAULT 0,
    added_at           timestamptz NOT NULL DEFAULT now(),
    fetched_at         timestamptz,
    updated_at         timestamptz NOT NULL DEFAULT now(),
    session_ref        text,
    CHECK (url IS NOT NULL OR source_document_id IS NOT NULL OR origin = 'user_document'),
    CHECK (origin <> 'user_document' OR body_text IS NOT NULL OR status IN ('failed','skipped')),
    CHECK (sections_read <= sections_total AND ai_sections_read <= sections_total)
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_research_documents_url ON research_documents (opportunity_id, url) WHERE url IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS ux_research_documents_source ON research_documents (opportunity_id, source_document_id)
    WHERE source_document_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS ux_research_documents_sha ON research_documents (opportunity_id, content_sha256)
    WHERE origin = 'user_document' AND content_sha256 IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_research_documents_status ON research_documents (opportunity_id, status);

-- Research runs: their outcome and the coverage they achieved. "No people found" (complete) is kept distinct from
-- "research incomplete" (remaining work, failed fetches, budget limits).
ALTER TABLE relationship_research_runs ADD COLUMN IF NOT EXISTS outcome text;
ALTER TABLE relationship_research_runs DROP CONSTRAINT IF EXISTS relationship_research_runs_outcome_check;
ALTER TABLE relationship_research_runs ADD CONSTRAINT relationship_research_runs_outcome_check
    CHECK (outcome IS NULL OR outcome IN ('people_found','no_people_found','incomplete'));
ALTER TABLE relationship_research_runs ADD COLUMN IF NOT EXISTS coverage jsonb NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE relationship_research_runs ADD COLUMN IF NOT EXISTS searches jsonb NOT NULL DEFAULT '[]'::jsonb;
-- Runs recorded before this upgrade covered only the opportunity's own documents and fixed company-page addresses: their
-- outcome is not knowable as complete, so it is recorded as incomplete (never as "no people found").
UPDATE relationship_research_runs SET outcome = 'incomplete' WHERE outcome IS NULL;

-- ------------------------------------------------------------------ evidence: organisation bindings and research documents
ALTER TABLE person_evidence ADD COLUMN IF NOT EXISTS research_document_id uuid REFERENCES research_documents(id);
ALTER TABLE person_evidence DROP CONSTRAINT IF EXISTS person_evidence_supports_check;
ALTER TABLE person_evidence ADD CONSTRAINT person_evidence_supports_check
    CHECK (supports IN ('identity','role','organisation','remit','relevance','relationship','introduction'));
ALTER TABLE person_evidence DROP CONSTRAINT IF EXISTS person_evidence_source_kind_check;
ALTER TABLE person_evidence ADD CONSTRAINT person_evidence_source_kind_check
    CHECK (source_kind IN ('source_document','public_page','note','research_document'));
ALTER TABLE person_evidence DROP CONSTRAINT IF EXISTS person_evidence_research_document_check;
ALTER TABLE person_evidence ADD CONSTRAINT person_evidence_research_document_check
    CHECK (source_kind <> 'research_document' OR research_document_id IS NOT NULL);
-- The same passage is recorded once per person and purpose (re-running research adds nothing twice).
CREATE UNIQUE INDEX IF NOT EXISTS ux_person_evidence_passage ON person_evidence
    (person_id, supports, source_kind, coalesce(document_id::text, ''), coalesce(research_document_id::text, ''),
     coalesce(url, ''), md5(coalesce(quote, '')))
    WHERE source_kind <> 'note';

-- ------------------------------------------------------------------ evidence-backed roles
-- Who holds which title, at which organisation, with the passage that binds them. A role mentioned elsewhere in a document
-- is never attached to a person; an organisation is recorded only when the text binds the person to it.
CREATE TABLE IF NOT EXISTS person_roles (
    id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    person_id          uuid NOT NULL REFERENCES people(id),
    role_title         text,
    organisation_id    uuid REFERENCES organisations(id),
    organisation_label text,
    role_status        text NOT NULL DEFAULT 'current' CHECK (role_status IN ('current','former','incoming')),
    affiliation        text NOT NULL DEFAULT 'unknown' CHECK (affiliation IN ('employee','board_member','partner','customer',
                                                                                'other_organisation','unknown')),
    binding            text NOT NULL,                    -- what links the person to the title / organisation
    evidence_id        uuid REFERENCES person_evidence(id),
    source             text NOT NULL CHECK (source IN ('rules','ai','reviewer','before_upgrade')),
    confirmed_at       timestamptz,                      -- a person checked it
    created_at         timestamptz NOT NULL DEFAULT now(),
    CHECK (role_title IS NOT NULL OR organisation_id IS NOT NULL OR organisation_label IS NOT NULL)
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_person_roles ON person_roles
    (person_id, lower(coalesce(role_title, '')), coalesce(organisation_id::text, lower(organisation_label), ''), role_status);
-- Titles recorded before this upgrade are kept as they were, marked as recorded before the evidence rules.
INSERT INTO person_roles (person_id, role_title, organisation_id, organisation_label, role_status, affiliation, binding, source)
SELECT p.id, p.role_title, p.organisation_id, CASE WHEN p.organisation_id IS NULL THEN p.organisation_label END, 'current',
       CASE WHEN p.organisation_id IS NOT NULL OR p.organisation_label IS NOT NULL THEN 'employee' ELSE 'unknown' END,
       'recorded before the 28 Oct 2026 evidence rules (' || p.origin || ')', 'before_upgrade'
  FROM people p
 WHERE NOT p.is_internal AND p.role_title IS NOT NULL
ON CONFLICT DO NOTHING;

-- ------------------------------------------------------------------ identity: possible duplicates and reversible merges
ALTER TABLE people ADD COLUMN IF NOT EXISTS merged_into_id uuid REFERENCES people(id);
CREATE INDEX IF NOT EXISTS ix_people_name_norm ON people (lower(regexp_replace(full_name, '\s+', ' ', 'g')));

CREATE TABLE IF NOT EXISTS person_duplicate_candidates (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    person_a      uuid NOT NULL REFERENCES people(id),
    person_b      uuid NOT NULL REFERENCES people(id),
    reason        text NOT NULL,
    status        text NOT NULL DEFAULT 'open' CHECK (status IN ('open','merged','dismissed')),
    decided_at    timestamptz,
    decision_note text,
    created_at    timestamptz NOT NULL DEFAULT now(),
    session_ref   text,
    CHECK (person_a <> person_b)
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_person_duplicate_pair ON person_duplicate_candidates (least(person_a, person_b), greatest(person_a, person_b));

-- A merge moves the merged record's evidence, roles, opportunity links, relationships, routes and engagements to the kept
-- record and lists every moved row in `moved`, so it can be undone exactly. Nothing is deleted.
CREATE TABLE IF NOT EXISTS person_merges (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    kept_person_id   uuid NOT NULL REFERENCES people(id),
    merged_person_id uuid NOT NULL REFERENCES people(id),
    duplicate_id     uuid REFERENCES person_duplicate_candidates(id),
    moved            jsonb NOT NULL,
    kept_before      jsonb NOT NULL,                      -- the kept record's fields before the merge
    note             text,
    merged_at        timestamptz NOT NULL DEFAULT now(),
    undone_at        timestamptz,
    session_ref      text,
    CHECK (kept_person_id <> merged_person_id)
);
CREATE INDEX IF NOT EXISTS ix_person_merges_merged ON person_merges (merged_person_id) WHERE undone_at IS NULL;

-- Existing records that share a name but whose organisation is unknown on at least one side become possible duplicates for
-- review; nothing is merged automatically.
INSERT INTO person_duplicate_candidates (person_a, person_b, reason)
SELECT a.id, b.id,
       CASE WHEN a.organisation_id IS NULL AND a.organisation_label IS NULL OR b.organisation_id IS NULL AND b.organisation_label IS NULL
            THEN 'same name; organisation not established for one or both records'
            ELSE 'same name; different organisations recorded' END
  FROM people a JOIN people b ON a.id < b.id
       AND lower(regexp_replace(a.full_name, '\s+', ' ', 'g')) = lower(regexp_replace(b.full_name, '\s+', ' ', 'g'))
 WHERE NOT a.is_internal AND NOT b.is_internal AND a.merged_into_id IS NULL AND b.merged_into_id IS NULL
ON CONFLICT DO NOTHING;

-- ------------------------------------------------------------------ derived views: merged records are no longer counted
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
 WHERE NOT p.is_internal AND p.merged_into_id IS NULL;

CREATE OR REPLACE VIEW opportunity_relationship_coverage AS
WITH linked AS (
    SELECT o.id AS opportunity_id, ps.person_id, ps.state
      FROM opportunities o
      JOIN opportunity_people op ON op.opportunity_id = o.id AND op.status <> 'not_relevant'
      JOIN person_state ps ON ps.person_id = op.person_id
    UNION
    SELECT o.id, ps.person_id, ps.state
      FROM opportunities o
      JOIN people p ON p.organisation_id = coalesce(o.airline_id, o.organisation_id) AND NOT p.is_internal AND p.merged_into_id IS NULL
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
