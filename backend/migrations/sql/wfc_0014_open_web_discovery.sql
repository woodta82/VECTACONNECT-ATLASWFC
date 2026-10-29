-- VECTA Connect | ATLAS | DYNAMIC MARKET INTELLIGENCE — wfc_0014 (29 Oct 2026: open-web discovery as the default). Additive and
-- idempotent: nothing is dropped; configured sources keep working as optional monitoring inputs.
UPDATE schema_meta SET value = 'wfc_0014' WHERE key = 'revision';

-- A new source type: the authorised web search itself. One built-in record ("Open web") is planned for every search, covers
-- every country and every capability area, and needs no website registered. Its documents are the pages the search finds.
ALTER TABLE sources DROP CONSTRAINT IF EXISTS sources_source_type_check;
ALTER TABLE sources ADD CONSTRAINT sources_source_type_check
    CHECK (source_type IN ('web_page','listing','rss','search_template','file_import','web_search'));
ALTER TABLE sources ADD COLUMN IF NOT EXISTS builtin boolean NOT NULL DEFAULT false;   -- cannot be deleted; configured in Settings
INSERT INTO sources (name, family, base_url, authority, authorisation_note, retention_permitted, enabled, source_type, country_coverage,
                     global_coverage, language, local_language_permitted, modules, max_items, notes, builtin)
SELECT 'Open web (authorised search)', 'open_web', 'search://open-web', 'unverified',
       'Public pages found by the configured search connector (SEARCH_PROVIDER). Each page is fetched and read itself; search snippets are never used as evidence.',
       false, true, 'web_search', '{}', true, NULL, true, '{}', 25,
       'Built in. Runs for every search unless disabled. Searches run only when a search connector is configured on the server (Settings → Service status).',
       true
 WHERE NOT EXISTS (SELECT 1 FROM sources WHERE source_type = 'web_search' AND deleted_at IS NULL);

-- Per-document publisher family and authority, for pages found on the open web: an official portal found by search is an official
-- portal, and two different sites are two publishers. Configured sources keep their own family and authority (NULL here).
ALTER TABLE source_documents ADD COLUMN IF NOT EXISTS doc_family text;
ALTER TABLE source_documents ADD COLUMN IF NOT EXISTS doc_authority text;
ALTER TABLE source_documents DROP CONSTRAINT IF EXISTS source_documents_doc_authority_check;
ALTER TABLE source_documents ADD CONSTRAINT source_documents_doc_authority_check
    CHECK (doc_authority IS NULL OR doc_authority IN ('unverified','trade_press','company_release','official_portal','internal_record'));
-- Access restrictions met while reading (login, registration or payment required): labelled, never read, never bypassed.
ALTER TABLE source_documents ADD COLUMN IF NOT EXISTS access_restriction text;

-- Run outcomes that keep "nothing relevant found" apart from a search that could not run: no connector configured, every public
-- web search failed.
ALTER TABLE discovery_runs DROP CONSTRAINT IF EXISTS discovery_runs_outcome_check;
ALTER TABLE discovery_runs ADD CONSTRAINT discovery_runs_outcome_check CHECK (outcome IS NULL OR outcome IN
    ('results','no_relevant_results','partial_coverage','source_failure','incomplete','no_sources','cancelled','search_not_configured','search_failure'));
