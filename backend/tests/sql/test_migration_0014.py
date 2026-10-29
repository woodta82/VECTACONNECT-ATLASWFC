"""wfc_0014 keeps every source, document and run (29 Oct 2026): the built-in open-web source appears once, enabled; documents of
registered sources keep their source's family and authority (NULL per document); re-running changes nothing."""
from tests.sql.pg import SCHEMA_FILES, apply_file, drop_db, fresh_db

F14 = next(f for f in SCHEMA_FILES if f.name == "wfc_0014_open_web_discovery.sql")


def test_wfc_0014_adds_the_open_web_source_once_and_keeps_everything_else():
    db = fresh_db(upto="wfc_0013_open_market_relationships.sql")
    try:
        db.run("""
        INSERT INTO sources (id, name, family, base_url, authority, enabled, source_type, country_coverage) VALUES
          ('00000000-0000-0000-0000-0000000000a1', 'Example portal', 'example', 'https://portal.example/', 'official_portal', true, 'listing', '{KE}');
        INSERT INTO source_documents (source_id, original_url, canonical_url, content_hash, title, retrieved_at, parser_version) VALUES
          ('00000000-0000-0000-0000-0000000000a1', 'https://portal.example/n/1', 'https://portal.example/n/1', 'h1', 'Notice', now(), 'test');
        """)
        before = {t: db.val(f"SELECT count(*) FROM {t}") for t in ("sources", "source_documents", "discovery_runs")}
        apply_file(db, F14)
        assert db.val("SELECT count(*) FROM sources") == str(int(before["sources"]) + 1)
        assert db.rows("SELECT name, enabled::text, global_coverage::text, builtin::text FROM sources WHERE source_type = 'web_search'") == \
            [["Open web (authorised search)", "true", "true", "true"]]
        assert db.val("SELECT count(*) FROM source_documents") == before["source_documents"]
        assert db.rows("SELECT coalesce(doc_family, ''), coalesce(doc_authority, '') FROM source_documents") == [["", ""]]
        assert db.val("SELECT value FROM schema_meta WHERE key = 'revision'") == "wfc_0014"
        apply_file(db, F14)                                                                                   # idempotent
        assert db.val("SELECT count(*) FROM sources WHERE source_type = 'web_search'") == "1"
    finally:
        drop_db(db)
