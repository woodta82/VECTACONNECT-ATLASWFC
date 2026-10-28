-- ATLAS by VECTA Sports — Commercial Intelligence System — reference schema
--
-- CLEAN-INSTALL SCHEMA. ATLAS is a private, single-login platform: there
-- is no users table, no roles, and no account relationships here. The
-- commercial owner of an opportunity is an informational free-text field
-- (owner_name), not an account. Existing production databases created
-- before v2.9 still carry a legacy `users` table and `owner_id` columns;
-- those are deprecated and inaccessible (no API, no UI) and are retained
-- only so the migration is non-destructive — see docs/PHASE2_MIGRATION.md.
--
-- This file documents the data model for reference and manual inspection.
-- The running application does NOT execute this file: SQLAlchemy's
-- Base.metadata.create_all() creates all tables automatically from
-- backend/app/models.py on first boot. Keep this file in sync with
-- models.py when the schema changes — it is documentation, not a migration.

CREATE TYPE orgtype AS ENUM ('federation', 'club', 'government', 'brand', 'venue', 'other');
CREATE TYPE region AS ENUM ('mena', 'uk_ireland', 'europe', 'africa', 'asia_india', 'americas', 'oceania');
CREATE TYPE vertical AS ENUM ('media', 'talent', 'connect', 'experiences', 'pathways');
CREATE TYPE stage AS ENUM ('discovered', 'qualified', 'engaged', 'proposal', 'won', 'lost');
CREATE TYPE scantype AS ENUM ('scheduled', 'on_demand', 'saved_search');
CREATE TYPE interactiontype AS ENUM ('note', 'message', 'meeting', 'task');

CREATE TABLE organisations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    org_type orgtype DEFAULT 'other',
    region region,
    market TEXT,
    website TEXT,
    linkedin_url TEXT,
    created_at TIMESTAMP DEFAULT now()
);
CREATE INDEX idx_organisations_region ON organisations(region);

CREATE TABLE scan_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    type scantype DEFAULT 'scheduled',
    vertical_scope vertical,
    region_scope region,
    query_text TEXT,
    started_at TIMESTAMP DEFAULT now(),
    completed_at TIMESTAMP,
    sources_checked INTEGER DEFAULT 0,
    new_items INTEGER DEFAULT 0,
    status TEXT DEFAULT 'running',
    error TEXT
);

CREATE TABLE opportunities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    scan_run_id UUID REFERENCES scan_runs(id),
    organisation_id UUID REFERENCES organisations(id),
    title TEXT NOT NULL,
    summary TEXT,
    vertical vertical,
    region region,
    market TEXT,
    value_estimate NUMERIC,
    currency TEXT DEFAULT 'GBP',
    deadline DATE,
    source_urls JSONB DEFAULT '[]',
    alignment_score INTEGER DEFAULT 0,
    score_breakdown JSONB DEFAULT '{}',
    priority BOOLEAN DEFAULT false,
    stage stage DEFAULT 'discovered',
    owner_name TEXT,  -- informational commercial owner (free text). NOT an account: ATLAS is single-login.
    alerted_14 BOOLEAN DEFAULT false,
    alerted_7 BOOLEAN DEFAULT false,
    alerted_2 BOOLEAN DEFAULT false,
    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now()
);
CREATE INDEX idx_opportunities_vertical ON opportunities(vertical);
CREATE INDEX idx_opportunities_region ON opportunities(region);

CREATE TABLE contacts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    role TEXT,
    organisation_id UUID REFERENCES organisations(id),
    opportunity_id UUID REFERENCES opportunities(id),
    region region,
    linkedin_search_url TEXT,
    linkedin_profile_url TEXT,
    relevance_score INTEGER DEFAULT 50,
    connection_path TEXT,
    source TEXT DEFAULT 'ai_research',
    last_interaction_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT now()
);

CREATE TABLE interactions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    contact_id UUID REFERENCES contacts(id) NOT NULL,
    opportunity_id UUID REFERENCES opportunities(id),
    type interactiontype DEFAULT 'note',
    content TEXT,
    owner_name TEXT,  -- informational commercial owner (free text). NOT an account: ATLAS is single-login.
    draft BOOLEAN DEFAULT false,
    sent BOOLEAN DEFAULT false,
    timestamp TIMESTAMP DEFAULT now()
);

CREATE TABLE saved_searches (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    region region NOT NULL,
    market TEXT,
    query_text TEXT NOT NULL,
    parsed_filters JSONB DEFAULT '{}',
    schedule_hours NUMERIC,
    last_run_at TIMESTAMP,
    owner_name TEXT,  -- informational commercial owner (free text). NOT an account: ATLAS is single-login.
    created_at TIMESTAMP DEFAULT now()
);

CREATE TABLE notifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    kind TEXT NOT NULL,
    title TEXT NOT NULL,
    body TEXT,
    opportunity_id UUID REFERENCES opportunities(id),
    contact_id UUID REFERENCES contacts(id),
    read BOOLEAN DEFAULT false,
    created_at TIMESTAMP DEFAULT now()
);
