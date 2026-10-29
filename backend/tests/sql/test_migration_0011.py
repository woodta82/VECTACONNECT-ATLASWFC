"""wfc_0011 carries every existing record over (28 Oct 2026 refocus): contacts, engagements, opportunities, stages, owners,
evidence and history are kept; new fields are filled from what was already recorded; re-running changes nothing."""
from tests.sql.pg import SCHEMA_FILES, apply_file, drop_db, fresh_db

LAST = next(f for f in SCHEMA_FILES if f.name == "wfc_0011_relationship_intelligence.sql")


def test_wfc_0011_carries_existing_records_over_without_loss():
    db = fresh_db(upto="wfc_0010_status_chronology_v7.sql")
    try:
        db.run("""
        INSERT INTO organisations (id, canonical_name, kind) VALUES ('00000000-0000-0000-0000-0000000000a1', 'Example Air', 'airline');
        INSERT INTO people (id, full_name, role_title, organisation_id, is_internal, external_id) VALUES
          ('00000000-0000-0000-0000-0000000000b1', 'Imported Contact', 'Cargo Director', '00000000-0000-0000-0000-0000000000a1', false, 'P-1'),
          ('00000000-0000-0000-0000-0000000000b2', 'Owner Person', 'Commercial lead', NULL, true, 'P-2'),
          ('00000000-0000-0000-0000-0000000000b3', 'Manual Person', NULL, NULL, false, NULL);
        INSERT INTO engagements (person_id, organisation_id, occurred_at, kind, summary) VALUES
          ('00000000-0000-0000-0000-0000000000b1', '00000000-0000-0000-0000-0000000000a1', '2026-05-01T09:00:00Z', 'meeting', 'Quarterly review'),
          ('00000000-0000-0000-0000-0000000000b1', '00000000-0000-0000-0000-0000000000a1', '2026-09-12T09:00:00Z', 'call', 'Follow-up');
        INSERT INTO opportunities (id, module, dedup_key, title, commercial_stage, owner_person_id) VALUES
          ('00000000-0000-0000-0000-0000000000c1', 'airline_representation', 'k1', 'Deferred tender', 'deferred', '00000000-0000-0000-0000-0000000000b2'),
          ('00000000-0000-0000-0000-0000000000c2', 'airline_representation', 'k2', 'Won tender', 'won', NULL),
          ('00000000-0000-0000-0000-0000000000c3', 'airline_representation', 'k3', 'Qualified tender', 'qualified', NULL),
          ('00000000-0000-0000-0000-0000000000c4', 'airline_representation', 'k4', 'Negotiation', 'negotiation', NULL);
        UPDATE opportunities SET origin_ref = 'fs|x|2026-09-01', module = 'forwarder_sales' WHERE id = '00000000-0000-0000-0000-0000000000c4';
        INSERT INTO opportunity_status_history (opportunity_id, field, from_value, to_value, reason)
          VALUES ('00000000-0000-0000-0000-0000000000c1', 'commercial_stage', 'reviewing', 'deferred', 'paused by the team');
        """)
        before = {t: db.val(f"SELECT count(*) FROM {t}") for t in ("people", "engagements", "opportunities", "opportunity_status_history")}
        apply_file(db, LAST)
        after = {t: db.val(f"SELECT count(*) FROM {t}") for t in before}
        assert before == after                                                       # nothing removed or duplicated
        prog = dict(db.rows("SELECT title, progress || '/' || coalesce(closed_reason, '') FROM opportunities"))
        assert prog == {"Deferred tender": "on_hold/", "Won tender": "closed/won", "Qualified tender": "reviewing/", "Negotiation": "pursuing/"}
        assert db.val("SELECT commercial_stage FROM opportunities WHERE title = 'Won tender'") == "won"          # the old stage is kept
        assert db.val("SELECT owner_label FROM opportunities WHERE title = 'Deferred tender'") == "Owner Person"
        assert db.val("SELECT record_type FROM opportunities WHERE title = 'Negotiation'") == "commercial"
        assert db.val("SELECT record_type FROM opportunities WHERE title = 'Won tender'") == "tender"
        imp = db.rows("SELECT origin, identity_confirmed_at IS NOT NULL, identity_basis FROM people WHERE external_id = 'P-1'")[0]
        assert imp[0] == "import" and imp[1] == "t" and "WFC relationship records" in imp[2]
        assert db.val("SELECT identity_confirmed_at IS NULL FROM people WHERE full_name = 'Manual Person'") == "t"   # never assumed
        basis = db.val("SELECT basis FROM person_relationships WHERE person_id = '00000000-0000-0000-0000-0000000000b1'")
        assert "2 engagement(s), latest 2026-09-12" in basis
        assert db.val("SELECT state FROM person_state WHERE person_id = '00000000-0000-0000-0000-0000000000b1'") == "existing_relationship"
        assert db.val("SELECT state FROM person_state WHERE person_id = '00000000-0000-0000-0000-0000000000b3'") == "research_candidate"
        assert db.val("SELECT count(*) FROM person_state WHERE person_id = '00000000-0000-0000-0000-0000000000b2'") == "0"   # internal
        assert db.val("SELECT to_value FROM opportunity_status_history WHERE reason = 'paused by the team'") == "deferred"
        apply_file(db, LAST)                                                         # idempotent
        assert db.val("SELECT count(*) FROM person_relationships") == "1"
        assert db.val("SELECT value FROM schema_meta WHERE key = 'revision'") == "wfc_0011"
    finally:
        drop_db(db)
