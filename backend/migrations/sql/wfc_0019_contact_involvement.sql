-- wfc_0019 — a person's evidenced involvement (30 Oct 2026, release 4.9.0). Additive, idempotent.
--
-- * people.involvement: employee | appointed_representative | external_adviser | press_contact | unresolved, with the basis and the
--   outside organisation. Press contacts and external advisers are kept with their actual role, as external contacts.
-- * opportunity_people.status gains 'external_contact': the person is kept on the opportunity (with their role) but is not a commercial
--   contact — never counted in relationship coverage or ranking.
-- * opportunity_relationship_coverage counts only candidate and relevant links, and never a press contact or external adviser.

UPDATE schema_meta SET value = 'wfc_0019' WHERE key = 'revision';

ALTER TABLE people ADD COLUMN IF NOT EXISTS involvement text NOT NULL DEFAULT 'unresolved';
ALTER TABLE people DROP CONSTRAINT IF EXISTS people_involvement_check;
ALTER TABLE people ADD CONSTRAINT people_involvement_check
    CHECK (involvement IN ('employee','appointed_representative','external_adviser','press_contact','unresolved'));
ALTER TABLE people ADD COLUMN IF NOT EXISTS involvement_basis text;
ALTER TABLE people ADD COLUMN IF NOT EXISTS involvement_org text;
ALTER TABLE people ADD COLUMN IF NOT EXISTS involvement_set_by text NOT NULL DEFAULT 'research' ;
ALTER TABLE people DROP CONSTRAINT IF EXISTS people_involvement_set_by_check;
ALTER TABLE people ADD CONSTRAINT people_involvement_set_by_check CHECK (involvement_set_by IN ('research','person'));

ALTER TABLE opportunity_people DROP CONSTRAINT IF EXISTS opportunity_people_status_check;
ALTER TABLE opportunity_people ADD CONSTRAINT opportunity_people_status_check
    CHECK (status IN ('candidate','relevant','not_relevant','external_contact'));

CREATE OR REPLACE VIEW opportunity_relationship_coverage AS
WITH linked AS (
    SELECT o.id AS opportunity_id, ps.person_id, ps.state
      FROM opportunities o
      JOIN opportunity_people op ON op.opportunity_id = o.id AND op.status IN ('candidate','relevant')
      JOIN people p ON p.id = op.person_id AND p.involvement NOT IN ('press_contact','external_adviser')
      JOIN person_state ps ON ps.person_id = op.person_id
    UNION
    SELECT o.id, ps.person_id, ps.state
      FROM opportunities o
      JOIN people p ON p.organisation_id = coalesce(o.airline_id, o.organisation_id) AND NOT p.is_internal AND p.merged_into_id IS NULL
                   AND p.involvement NOT IN ('press_contact','external_adviser')
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
