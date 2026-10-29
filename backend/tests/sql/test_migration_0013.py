"""wfc_0013 keeps every existing record (29 Oct 2026): people gain unjudged stakeholder fields, engagements keep their outcomes
and default to outbound, research documents keep their opportunity scope; re-running changes nothing."""
from tests.sql.pg import SCHEMA_FILES, apply_file, drop_db, fresh_db

F13 = next(f for f in SCHEMA_FILES if f.name == "wfc_0013_open_market_relationships.sql")


def test_wfc_0013_carries_existing_people_engagements_and_research_over_without_loss():
    db = fresh_db(upto="wfc_0012_relationship_research.sql")
    try:
        db.run("""
        INSERT INTO organisations (id, canonical_name, kind) VALUES ('00000000-0000-0000-0000-0000000000a1', 'Example Air', 'airline');
        INSERT INTO people (id, full_name, role_title, organisation_id, is_internal, origin) VALUES
          ('00000000-0000-0000-0000-0000000000b1', 'Grace Achieng', 'Head of Cargo', '00000000-0000-0000-0000-0000000000a1', false, 'research');
        INSERT INTO opportunities (id, module, dedup_key, title) VALUES ('00000000-0000-0000-0000-0000000000c1', 'airline_representation', 'k1', 'Tender');
        INSERT INTO engagements (person_id, opportunity_id, occurred_at, kind, summary, outcome) VALUES
          ('00000000-0000-0000-0000-0000000000b1', '00000000-0000-0000-0000-0000000000c1', now() - interval '10 days', 'call', 'intro call', 'positive');
        INSERT INTO research_documents (opportunity_id, origin, url, status) VALUES
          ('00000000-0000-0000-0000-0000000000c1', 'user_url', 'https://x.example/page', 'read');
        """)
        before = {t: db.val(f"SELECT count(*) FROM {t}") for t in ("people", "engagements", "research_documents", "person_roles")}
        apply_file(db, F13)
        assert {t: db.val(f"SELECT count(*) FROM {t}") for t in before} == before
        assert db.rows("SELECT stakeholder_type, decision_authority, posture, strategic_account::text FROM people") == [["unknown", "unknown", "unknown", "false"]]
        assert db.rows("SELECT outcome, direction FROM engagements") == [["positive", "outbound"]]
        assert db.val("SELECT count(*) FROM research_documents WHERE opportunity_id IS NOT NULL AND discovery_id IS NULL") == "1"
        assert db.val("SELECT value FROM schema_meta WHERE key = 'revision'") == "wfc_0013"
        apply_file(db, F13)                                                                                   # idempotent
        assert db.val("SELECT count(*) FROM people") == "1" and db.val("SELECT value FROM schema_meta WHERE key = 'revision'") == "wfc_0013"
        # the new constraints hold
        db.run("INSERT INTO engagements (person_id, occurred_at, kind, summary, outcome, direction) VALUES "
               "('00000000-0000-0000-0000-0000000000b1', now(), 'message', 'LinkedIn note', 'no_response', 'outbound')")
        assert db.val("SELECT count(*) FROM engagements") == "2"
    finally:
        drop_db(db)
