"""wfc_0016 keeps every organisation, person, discovery and search (30 Oct 2026): new columns take safe defaults (freight scope unresolved,
empty research status, empty airport scopes), the directory and research tables are empty until loaded, re-running changes nothing."""
from tests.sql.pg import SCHEMA_FILES, apply_file, drop_db, fresh_db

F16 = next(f for f in SCHEMA_FILES if f.name == "wfc_0016_workspace_research.sql")


def test_wfc_0016_is_additive_with_safe_defaults():
    db = fresh_db(upto="wfc_0015_company_intelligence.sql")
    try:
        db.run("""
        INSERT INTO organisations (id, canonical_name, kind, country, origin) VALUES ('00000000-0000-0000-0000-0000000000b1', 'Example GSA', 'gssa', 'BE', 'supplied');
        INSERT INTO people (id, full_name) VALUES ('00000000-0000-0000-0000-0000000000c1', 'Example Person');
        INSERT INTO contact_discoveries (id, countries, brief, purpose) VALUES ('00000000-0000-0000-0000-0000000000d1', '{BE}', 'older', 'companies');
        INSERT INTO discovery_searches (id, geo_mode, countries, purpose) VALUES ('00000000-0000-0000-0000-0000000000e1', 'country', '{BE}', 'market');
        """)
        before = {t: db.val(f"SELECT count(*) FROM {t}") for t in ("organisations", "people", "contact_discoveries", "discovery_searches", "research_documents")}
        apply_file(db, F16)
        assert {t: db.val(f"SELECT count(*) FROM {t}") for t in before} == before
        assert db.rows("SELECT freight_scope, research_status::text, coalesce(contact_url, '') FROM organisations") == [["unresolved", "{}", ""]]
        assert db.rows("SELECT coalesce(published_email, ''), research_status::text FROM people") == [["", "{}"]]
        assert db.val("SELECT airports::text FROM contact_discoveries") == "{}" and db.val("SELECT airports::text FROM discovery_searches") == "{}"
        assert db.val("SELECT purpose FROM contact_discoveries") == "companies" and db.val("SELECT purpose FROM discovery_searches") == "market"
        for t in ("airport_directory", "reference_datasets", "organisation_airports", "opportunity_airports", "research_stages", "company_duplicates", "company_merge_log"):
            assert db.val(f"SELECT count(*) FROM {t}") == "0"
        for bad in ("UPDATE organisations SET freight_scope = 'space'",
                    "INSERT INTO research_stages (entity_type, entity_id, stage) VALUES ('opportunity', '00000000-0000-0000-0000-0000000000b1', 'guess')",
                    "INSERT INTO organisation_airports (organisation_id, airport_ident, role, basis) VALUES ('00000000-0000-0000-0000-0000000000b1', 'EBBR', 'somewhere', 'x')",
                    "INSERT INTO airport_directory (ident, name, country, source_key) VALUES ('EBBR', 'Brussels', 'BE', 'nobody')"):
            try:
                db.run(bad)
                raise AssertionError(f"accepted: {bad}")
            except Exception as exc:  # noqa: BLE001
                assert any(w in str(exc).lower() for w in ("check", "violates", "foreign key")), exc
        assert db.val("SELECT value FROM schema_meta WHERE key = 'revision'") == "wfc_0016"
        apply_file(db, F16)                                                                                   # idempotent
        assert db.val("SELECT count(*) FROM organisations") == "1"
    finally:
        drop_db(db)
