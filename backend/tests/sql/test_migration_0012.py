"""wfc_0012 keeps every existing record (28 Oct 2026, second continuation): titles become evidence-backed roles marked as
recorded before the evidence rules; same-name records become possible duplicates for review, never merged; earlier
research runs are marked incomplete (never "no people found"); re-running changes nothing."""
from tests.sql.pg import SCHEMA_FILES, apply_file, drop_db, fresh_db

F12 = next(f for f in SCHEMA_FILES if f.name == "wfc_0012_relationship_research.sql")


def test_wfc_0012_carries_existing_people_and_research_over_without_loss():
    db = fresh_db(upto="wfc_0011_relationship_intelligence.sql")
    try:
        db.run("""
        INSERT INTO organisations (id, canonical_name, kind) VALUES ('00000000-0000-0000-0000-0000000000a1', 'Example Air', 'airline');
        INSERT INTO people (id, full_name, role_title, organisation_id, organisation_label, is_internal, origin) VALUES
          ('00000000-0000-0000-0000-0000000000b1', 'Grace Achieng', 'Head of Cargo', '00000000-0000-0000-0000-0000000000a1', NULL, false, 'import'),
          ('00000000-0000-0000-0000-0000000000b2', 'Grace  Achieng', 'Procurement Manager', NULL, NULL, false, 'research'),
          ('00000000-0000-0000-0000-0000000000b3', 'Peter Otieno', NULL, NULL, NULL, false, 'manual'),
          ('00000000-0000-0000-0000-0000000000b4', 'Internal Lead', 'Commercial lead', NULL, NULL, true, 'manual');
        INSERT INTO opportunities (id, module, dedup_key, title) VALUES
          ('00000000-0000-0000-0000-0000000000c1', 'airline_representation', 'k1', 'Tender');
        INSERT INTO person_evidence (person_id, supports, source_kind, note) VALUES
          ('00000000-0000-0000-0000-0000000000b2', 'relevance', 'note', 'found earlier');
        INSERT INTO relationship_research_runs (opportunity_id, methods) VALUES ('00000000-0000-0000-0000-0000000000c1', '{source_documents}');
        """)
        before = {t: db.val(f"SELECT count(*) FROM {t}") for t in ("people", "person_evidence", "relationship_research_runs", "opportunities")}
        apply_file(db, F12)
        assert {t: db.val(f"SELECT count(*) FROM {t}") for t in before} == before                    # nothing removed or duplicated
        roles = db.rows("SELECT person_id, role_title, coalesce(organisation_id::text, ''), affiliation, source FROM person_roles ORDER BY role_title")
        assert roles == [["00000000-0000-0000-0000-0000000000b1", "Head of Cargo", "00000000-0000-0000-0000-0000000000a1", "employee", "before_upgrade"],
                         ["00000000-0000-0000-0000-0000000000b2", "Procurement Manager", "", "unknown", "before_upgrade"]]
        dup = db.rows("SELECT person_a, person_b, reason, status FROM person_duplicate_candidates")
        assert dup == [["00000000-0000-0000-0000-0000000000b1", "00000000-0000-0000-0000-0000000000b2",
                        "same name; organisation not established for one or both records", "open"]]
        assert db.val("SELECT count(*) FROM people WHERE merged_into_id IS NOT NULL") == "0"                 # nothing merged
        assert db.val("SELECT outcome FROM relationship_research_runs") == "incomplete"
        assert db.val("SELECT count(*) FROM person_state") == "3"                                            # internal excluded
        apply_file(db, F12)                                                                                   # idempotent
        assert db.val("SELECT count(*) FROM person_roles") == "2" and db.val("SELECT count(*) FROM person_duplicate_candidates") == "1"
        assert db.val("SELECT value FROM schema_meta WHERE key = 'revision'") == "wfc_0012"
    finally:
        drop_db(db)
