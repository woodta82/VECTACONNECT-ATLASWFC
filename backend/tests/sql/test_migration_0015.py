"""wfc_0015 keeps every organisation, person and discovery (29 Oct 2026): existing organisations become origin 'manual' with nothing
supplied or verified, existing discoveries keep the 'people' purpose and existing searches the 'opportunities' purpose; the new
kinds, statuses and tables are in place; re-running changes nothing."""
from tests.sql.pg import SCHEMA_FILES, apply_file, drop_db, fresh_db

F15 = next(f for f in SCHEMA_FILES if f.name == "wfc_0015_company_intelligence.sql")


def test_wfc_0015_extends_organisations_and_research_purposes_without_touching_existing_rows():
    db = fresh_db(upto="wfc_0014_open_web_discovery.sql")
    try:
        db.run("""
        INSERT INTO organisations (id, canonical_name, kind, country) VALUES ('00000000-0000-0000-0000-0000000000b1', 'Example Air', 'airline', 'KE');
        INSERT INTO contact_discoveries (id, countries, brief) VALUES ('00000000-0000-0000-0000-0000000000c1', '{KE}', 'older discovery');
        INSERT INTO discovery_searches (id, geo_mode, countries) VALUES ('00000000-0000-0000-0000-0000000000d1', 'country', '{KE}');
        """)
        before = {t: db.val(f"SELECT count(*) FROM {t}") for t in ("organisations", "contact_discoveries", "discovery_searches", "people")}
        apply_file(db, F15)
        assert {t: db.val(f"SELECT count(*) FROM {t}") for t in before} == before
        assert db.rows("SELECT origin, coalesce(supplied_at::text, ''), coalesce(verified_at::text, ''), capability_areas::text FROM organisations") == \
            [["manual", "", "", "{}"]]
        assert db.val("SELECT purpose FROM contact_discoveries") == "people"
        assert db.val("SELECT purpose FROM discovery_searches") == "opportunities"
        # new kinds and statuses accepted; wrong ones refused
        db.run("INSERT INTO organisations (canonical_name, kind, origin, carrier_type) VALUES ('Thousand Hills Cargo Services Ltd', 'gssa', 'discovery', NULL)")
        db.run("INSERT INTO organisations (canonical_name, kind, origin, carrier_type, supplied_at) VALUES ('Belly Example Air', 'airline', 'supplied', 'passenger_belly', now())")
        for bad in ("INSERT INTO organisations (canonical_name, kind) VALUES ('x', 'spaceline')",
                    "INSERT INTO organisations (canonical_name, kind, origin) VALUES ('x', 'gssa', 'guessed')",
                    "INSERT INTO organisations (canonical_name, kind, carrier_type) VALUES ('x', 'airline', 'blimp')",
                    "UPDATE contact_discoveries SET purpose = 'everything'",
                    "UPDATE discovery_searches SET purpose = 'tenders'"):
            try:
                db.run(bad)
                raise AssertionError(f"accepted: {bad}")
            except Exception as exc:  # noqa: BLE001
                assert "check" in str(exc).lower() or "violates" in str(exc).lower(), exc
        for t in ("organisation_contacts", "organisation_evidence", "organisation_relationships", "supplied_imports", "supplied_rows", "discovery_organisations"):
            assert db.val(f"SELECT count(*) FROM {t}") == "0"
        assert db.val("SELECT value FROM schema_meta WHERE key = 'revision'") == "wfc_0015"
        apply_file(db, F15)                                                                                   # idempotent
        assert db.val("SELECT count(*) FROM organisations") == "3"
    finally:
        drop_db(db)
