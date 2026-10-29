"""The intended journey of the 28 Oct 2026 refocus, end to end on PostgreSQL, WITHOUT any WFC import:

 1. a country search finds a relevant opportunity;           6. candidates carry sources and targeted LinkedIn searches;
 2. a regional search returns results with clear geography;   7. a person is confirmed; a relationship and an introduction are
 3. worldwide discovery shows its actual coverage;               recorded (an introduction needs confirmed willingness);
 4. duplicate announcements resolve to one opportunity;       8. the Overview reflects the opportunity and relationship updates;
 5. relationship research runs from the opportunity;          9. a cancellation updates the opportunity and keeps its
                                                                 relationship history;  10. no booking or financial import exists.

SIMULATED: the public sites are synthetic pages and the extractor is scripted (tests/integration/test_review3_regressions.model);
the AI people reader is exercised with a scripted transport in its own test. No real provider or public site is used here.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app import config
from app.domain import relationships as rel
from app.main import create_app
from app.services import discovery as dsc
from app.services import relationship_service as rs
from app.services.audit import RequestMeta
from tests.integration.sa import sadb  # noqa: F401
from tests.integration.test_review3_regressions import BASE, SETTINGS, Web, _listing, _page, _source, model, rdb  # noqa: F401

UTC = timezone.utc
META = RequestMeta(ip="203.0.113.40", request_id="req-rj", session_ref="sessjourney001")
PASSWORD = "Journey-Verify-Pass-2026!"
PUBLISHED = (datetime.now(UTC) - timedelta(days=2)).isoformat()
DUE = datetime.now(UTC) + timedelta(days=45)
DUE_TXT = f"{DUE.day} {DUE.strftime('%B %Y')}"

KE = (f"Example Air invites proposals from GSSA providers for cargo sales representation in Kenya. Tender reference EXA-GSSA-2026-301. "
      f"Proposals are due on {DUE_TXT}. Contact: Jane Wanjiru, Procurement Manager.")
UG = f"Example Air invites proposals from GSSA providers for cargo sales representation in Uganda. Tender reference EXA-GSSA-2026-302. Proposals are due on {DUE_TXT}."
ROUTE = ("Example Air will operate a twice-weekly Boeing 777F service between Dubai (DXB) and Nairobi (NBO) from 3 December 2026, "
         "said Head of Cargo Maria Lopez.")
CANCEL = "Tender EXA-GSSA-2026-301 for cargo GSSA representation in Kenya, issued by Example Air, has been cancelled."


def reply(doc: str) -> dict:
    claims = []
    for text, ref, country in ((KE, "EXA-GSSA-2026-301", "Kenya"), (UG, "EXA-GSSA-2026-302", "Uganda")):
        if text in doc:
            claims.append({"claim_type": "gssa_tender", "stance": "supports", "quote": text, "fields": {
                "airline": {"value": "Example Air", "quote": text}, "country": {"value": country, "quote": text},
                "service": {"value": "GSSA", "quote": text}, "status": {"value": "open", "quote": text},
                "tender_ref": {"value": ref, "quote": text}, "deadline": {"value": DUE.date().isoformat(), "quote": text}}})
    if ROUTE in doc:
        claims.append({"claim_type": "route_launch", "stance": "supports", "quote": ROUTE, "fields": {
            "airline": {"value": "Example Air", "quote": ROUTE}, "origin": {"value": "DXB", "quote": "between Dubai (DXB) and Nairobi (NBO)"},
            "destination": {"value": "NBO", "quote": "between Dubai (DXB) and Nairobi (NBO)"}}})
    if CANCEL in doc:
        claims.append({"claim_type": "tender_status", "stance": "supports", "quote": CANCEL, "fields": {
            "airline": {"value": "Example Air", "quote": CANCEL}, "tender_ref": {"value": "EXA-GSSA-2026-301", "quote": CANCEL},
            "status": {"value": "cancelled", "quote": CANCEL}}})
    return {"language": "en", "claims": claims}


def site(cancelled: bool = False) -> Web:
    links = [f"{BASE}/n/ke", f"{BASE}/n/ke-copy", f"{BASE}/n/ug", f"{BASE}/n/route"] + ([f"{BASE}/n/cancel"] if cancelled else [])
    pages = {BASE + "/n/": _listing(links),
             links[0]: _page("RFP EXA-GSSA-2026-301", KE, published=PUBLISHED),
             links[1]: _page("Syndicated: RFP EXA-GSSA-2026-301", KE, published=PUBLISHED),
             links[2]: _page("RFP EXA-GSSA-2026-302", UG, published=PUBLISHED),
             links[3]: _page("Example Air freighter launch", ROUTE, published=PUBLISHED)}
    if cancelled:
        pages[links[4]] = _page("Cancellation EXA-GSSA-2026-301", CANCEL, published=datetime.now(UTC).isoformat())
    return Web(pages)


def run(db, spec: dsc.SearchSpec, web: Web) -> dict:
    sid = dsc.create_search(db, spec)
    started = dsc.start_run(db, SETTINGS, search_id=sid)
    dsc.execute_run(db, SETTINGS, started["run_id"], None, fetch=web, transport=model(reply))
    return db.one("run_get", id=started["run_id"])


def client_for(db) -> TestClient:
    settings = config.load({"ENVIRONMENT": "test", "LOGIN_USERNAME": "ops@wfc.example", "LOGIN_BOOTSTRAP_PASSWORD": PASSWORD,
                            "BUILD_ID": "journey"})
    c = TestClient(create_app(settings, lambda: db))
    c.__enter__()
    r = c.post("/auth/login", json={"username": "ops@wfc.example", "password": PASSWORD})
    assert r.status_code == 200, r.text
    c.headers["x-csrf-token"] = r.json()["csrf_token"]
    return c


def test_the_intended_journey_without_wfc_operational_data(rdb):  # noqa: F811
    db = rdb
    _source(db, "Example Air procurement and news", "listing", BASE + "/n/", country_coverage=["KE", "UG"], max_items=10)

    # 1. country search
    r1 = run(db, dsc.SearchSpec("country", ["KE"], [], []), site())
    assert r1["status"] in ("completed", "partial"), r1
    opp = db.pg.val("SELECT o.id FROM opportunities o JOIN signals s ON s.id = o.signal_id WHERE s.tender_ref = 'EXA-GSSA-2026-301' "
                    "AND o.merged_into_id IS NULL")
    assert opp and db.pg.val(f"SELECT tender_status FROM opportunities WHERE id = '{opp}'") == "open"

    # 4. duplicate announcements (the notice and its syndicated copy) resolve to one opportunity with two evidence links
    assert db.pg.val("SELECT count(*) FROM opportunities o JOIN signals s ON s.id = o.signal_id "
                     "WHERE s.tender_ref = 'EXA-GSSA-2026-301' AND o.merged_into_id IS NULL") == "1"
    assert int(db.pg.val(f"SELECT count(DISTINCT ce.source_document_id) FROM opportunities o JOIN signal_claims sc ON sc.signal_id = o.signal_id "
                         f"JOIN claim_evidence ce ON ce.claim_id = sc.claim_id WHERE o.id = '{opp}'")) == 2

    # 2. regional search with clear geography
    run(db, dsc.SearchSpec("region", [], ["EAC"], []), site())
    c = client_for(db)
    eac = c.get("/records", params={"region": "EAC"}).json()["items"]
    by_title = {r["title"]: r for r in eac}
    ug = next(r for r in eac if "EXA-GSSA-2026-302" in r["title"] or r.get("tender_ref") == "EXA-GSSA-2026-302")
    assert ug["countries"] == ["UG"] and ug["countries_named"] == ["Uganda"] and ug["record_type"] == "tender"
    assert all(set(r["countries"]) & {"KE", "UG", "TZ", "RW", "BI", "SS", "CD", "SO"} for r in by_title.values())

    # 3. worldwide discovery shows its actual coverage, never a complete view
    rw = run(db, dsc.SearchSpec("worldwide", [], [], []), site())
    note = rw["plan"].get("coverage_note") or ""
    assert "not a complete worldwide view" in note and rw["counts"]["coverage"]["planned"] == ["KE", "UG"]

    # record types: the route launch is a market signal, distinct from tenders, with what is unconfirmed stated
    signals = c.get("/records", params={"types": "market_signal"}).json()["items"]
    route = next(s for s in signals if "777F" in s["title"] or "Example Air" in s["title"])
    detail = c.get(f"/records/signals/{route['id']}").json()
    assert detail["interpretation"]["label"] == "ATLAS interpretation (not a source fact)"
    assert any("No open tender" in u for u in detail["interpretation"]["unconfirmed"])

    # 5. research relationships from the opportunity (source documents; AI reader not connected in this app's settings)
    res = c.post(f"/opportunities/{opp}/research").json()
    assert "source_documents" in res["methods"]
    assert any(u["method"] == "configured_extractor" and "not connected" in u["reason"] for u in res["unavailable"])
    assert any(u["method"] == "linkedin_profiles" for u in res["unavailable"])
    jane = next(f for f in res["found"] if f["name"] == "Jane Wanjiru")
    assert jane["role"] == "Procurement Manager"

    # 6. the candidate carries its source and a targeted LinkedIn search; searches are labelled as searches
    p = c.get(f"/people/{jane['person_id']}").json()
    assert p["person"]["state"] == "research_candidate" and p["person"]["linkedin_profile_url"] is None
    assert p["person"]["linkedin_search_url"].startswith(rel.LINKEDIN_PEOPLE_SEARCH) and "Jane%20Wanjiru" in p["person"]["linkedin_search_url"]
    ev = [e for e in p["evidence"] if e["source_kind"] == "source_document"]
    assert ev and "Contact: Jane Wanjiru, Procurement Manager" in ev[0]["quote"] and ev[0]["document_id"]
    intel = c.get(f"/opportunities/{opp}/intelligence").json()
    link = next(x for x in intel["relationships"]["people"] if x["id"] == jane["person_id"])
    assert link["role_on_opportunity"] == "procurement_contact" and "not established" in link["relevance_basis"]
    assert all(s["kind"] == "linkedin_search" and s["url"].startswith(rel.LINKEDIN_PEOPLE_SEARCH) for s in res["searches"])
    assert any("Example Air" in s["organisation"] for s in res["searches"])
    assert intel["relationships"]["coverage"] == "candidates_only"

    # 7. confirm the person, save the correct profile, record an existing relationship and an introduction route
    assert c.post(f"/people/{jane['person_id']}/linkedin", json={"url": "https://www.linkedin.com/search/results/people/?keywords=x"}).status_code == 422
    assert c.post(f"/people/{jane['person_id']}/confirm",
                  json={"basis": "Named as procurement contact in the RFP; role matches the airline's procurement page"}).status_code == 200
    saved = c.post(f"/people/{jane['person_id']}/linkedin", json={"url": "https://www.linkedin.com/in/jane-wanjiru-example/?trk=x"}).json()
    assert saved["linkedin_profile_url"] == "https://www.linkedin.com/in/jane-wanjiru-example/"
    maria = next(f for f in c.post(f"/opportunities/{opp}/people", json={
        "full_name": "Maria Lopez", "role_title": "Head of Cargo", "role_on_opportunity": "commercial_leader",
        "relevance_basis": "Quoted as Head of Cargo in the airline's route announcement",
        "source_note": "Example Air freighter launch announcement"}).json().items())
    maria_id = maria[1]
    route_id = c.post(f"/people/{maria_id}/routes", json={"introducer_label": "Former colleague at another carrier",
                                                          "connection_basis": "Both listed on the same industry panel in 2025",
                                                          "opportunity_id": opp}).json()["id"]
    refused = c.post(f"/routes/{route_id}/status", json={"status": "available"})
    assert refused.status_code == 422 and "willingness" in refused.json()["detail"]   # a public association is not an introduction
    assert c.post(f"/routes/{route_id}/status", json={"status": "available",
                                                       "willingness_basis": "Introducer confirmed by phone on 28 Oct that they will introduce us"}).status_code == 200
    assert c.post(f"/people/{jane['person_id']}/relationships", json={"holder": "WFC Kenya commercial lead", "nature": "works_with",
                                                                        "basis": "Met at two procurement briefings in 2025 and exchanged email"}).status_code == 200
    assert c.post(f"/people/{jane['person_id']}/engagements", json={"kind": "call", "summary": "Introductory call about the RFP timetable",
                                                                      "opportunity_id": opp, "owner_label": "WFC Kenya commercial lead"}).status_code == 200
    assert c.get(f"/people/{jane['person_id']}").json()["person"]["relationship_owner"] == "WFC Kenya commercial lead"
    states = {x["id"]: x["state"] for x in c.get(f"/opportunities/{opp}/intelligence").json()["relationships"]["people"]}
    assert states[jane["person_id"]] == "existing_relationship" and states[maria_id] == "introduction_available"

    # workspace: progress, owner, next action, note, saved
    assert c.post(f"/opportunities/{opp}/progress", json={"to": "pursuing", "reason": "relationship in place"}).status_code == 200
    c.post(f"/opportunities/{opp}/owner-label", json={"owner": "WFC Kenya commercial lead"})
    c.post(f"/opportunities/{opp}/next-action", json={"action": "Ask Jane for the clarification deadline", "due": DUE.date().isoformat()})
    c.post(f"/opportunities/{opp}/notes", json={"body": "Jane prefers email; panel contact willing to introduce Maria."})
    c.post(f"/opportunities/{opp}/saved", json={"saved": True})

    # 8. the Overview reflects it
    ov = c.get("/overview").json()
    assert any(r["id"] == opp for r in ov["with_relationships"])
    assert ov["priority"][0]["id"] == opp and "Open tender, deadline in" in ov["priority"][0]["priority_reason"]
    assert any(r["id"] == opp for r in ov["upcoming_deadlines"])
    assert any(p["id"] == jane["person_id"] for p in ov["people_recent"])
    assert any(ch["field"] == "progress" and ch["opportunity_id"] == opp for ch in ov["recent_changes"])
    assert ov["counts"]["market_signal"] >= 1 and ov["counts"]["tender"] >= 2
    filtered = c.get("/overview", params={"coverage": "existing_relationship"}).json()
    assert [r["id"] for r in filtered["priority"]] == [opp]
    panel = c.get("/control-panel").json()
    mine = next(r for r in panel["scored"] if r["id"] == opp)
    assert 0 <= mine["score"] <= 100 and mine["score"] == sum(x["points"] for x in mine["components"])
    assert next(x for x in mine["components"] if x["key"] == "relationships")["points"] == 25     # existing relationship
    assert any(m["country"] == "Kenya" and m["live"] >= 1 for m in panel["by_country"])
    assert any(m["market"] == "Eastern Africa" for m in panel["by_market"]) and "not a probability" in panel["rule"].lower()
    brief = c.get(f"/opportunities/{opp}/export.md").text
    assert "Jane Wanjiru" in brief and "Existing relationship" in brief and "Relationship gaps" in brief and "has been sent" in brief

    # 9. a cancellation updates the opportunity and keeps every relationship record
    run(db, dsc.SearchSpec("country", ["KE"], [], []), site(cancelled=True))
    assert db.pg.val(f"SELECT tender_status FROM opportunities WHERE id = '{opp}'") == "cancelled"
    assert db.pg.val(f"SELECT progress FROM opportunities WHERE id = '{opp}'") == "pursuing"      # the team decides when to close it
    assert db.pg.val(f"SELECT count(*) FROM opportunity_people WHERE opportunity_id = '{opp}'") == "2"
    assert db.pg.val(f"SELECT count(*) FROM person_relationships WHERE person_id = '{jane['person_id']}'") == "1"
    assert db.pg.val(f"SELECT count(*) FROM engagements WHERE opportunity_id = '{opp}'") == "1"
    assert db.pg.val(f"SELECT count(*) FROM opportunity_notes WHERE opportunity_id = '{opp}'") == "1"
    after = c.get("/overview").json()
    assert all(r["id"] != opp for r in after["priority"][:1]) and not any(r["id"] == opp for r in after["upcoming_deadlines"])
    assert any(ch["field"] == "tender_status" and ch["to_value"] == "cancelled" for ch in after["recent_changes"])
    assert all(r["id"] != opp for r in c.get("/control-panel").json()["scored"])        # cancelled: no longer scored
    rec = c.get("/records", params={"q": "EXA-GSSA-2026-301"}).json()["items"][0]
    assert rec["tender_status"] == "cancelled" and rec["coverage"] == "existing_relationship"
    gone = c.get(f"/opportunities/{opp}/intelligence").json()["interpretation"]["text"]
    assert gone.startswith("The source states this tender is cancelled: it cannot be bid for"), gone

    # 10. no booking, quote, capacity, finance or other operational import exists
    assert db.pg.val("SELECT count(*) FROM import_jobs") == "0"
    assert db.pg.val("SELECT count(*) FROM bookings") == "0" and db.pg.val("SELECT count(*) FROM financial_aggregates") == "0"
    c.__exit__(None, None, None)


def test_ai_people_reader_requires_a_verbatim_quote_and_never_assigns_authority(rdb):  # noqa: F811
    """SIMULATED transport: the configured AI path with a scripted provider reply."""
    db = rdb
    _source(db, "Example Air procurement and news", "listing", BASE + "/n/", country_coverage=["KE", "UG"], max_items=10)
    run(db, dsc.SearchSpec("country", ["KE"], [], []), site())
    opp = db.pg.val("SELECT o.id FROM opportunities o JOIN signals s ON s.id = o.signal_id WHERE s.tender_ref = 'EXA-GSSA-2026-301'")
    import json as _json

    def transport(_settings, _system, user):
        return _json.dumps({"people": [
            {"name": "Jane Wanjiru", "role": "Procurement Manager", "organisation": "Example Air", "quote": "Contact: Jane Wanjiru, Procurement Manager."},
            {"name": "Ahmed Invented", "role": "Chief Executive Officer", "organisation": "Example Air", "quote": "Ahmed Invented leads the airline."},
            {"name": "Jane Wanjiru", "role": "decision maker", "organisation": None, "quote": "Proposals are due on"}]}), 900, 120
    out = rs.research(db, SETTINGS, opp, META, transport=transport)
    assert "configured_extractor" in out["methods"]
    names = {f["name"] for f in out["found"]}
    assert "Ahmed Invented" not in names and "Jane Wanjiru" in names
    assert db.pg.val("SELECT count(*) FROM people WHERE full_name = 'Ahmed Invented'") == "0"
    assert db.pg.val("SELECT count(*) FROM opportunity_people WHERE role_on_opportunity = 'decision_maker'") == "0"
    assert db.pg.val("SELECT count(*) FROM ai_calls WHERE prompt_version = 'people-in-document-2'") == "2"   # one call per section: notice + copy
    assert db.pg.val("SELECT count(*) FROM people WHERE full_name = 'Jane Wanjiru'") == "1"            # rule and AI findings merge


def test_organisation_website_research_and_profile_rules(rdb):  # noqa: F811
    db = rdb
    _source(db, "Example Air procurement and news", "listing", BASE + "/n/", country_coverage=["KE", "UG"], max_items=10)
    run(db, dsc.SearchSpec("country", ["KE"], [], []), site())
    opp = db.pg.val("SELECT o.id FROM opportunities o JOIN signals s ON s.id = o.signal_id WHERE s.tender_ref = 'EXA-GSSA-2026-301'")
    org = db.pg.val(f"SELECT coalesce(airline_id, organisation_id) FROM opportunities WHERE id = '{opp}'")
    no_site = rs.research(db, config.load({"ENVIRONMENT": "test"}), opp, META)
    assert any(u["method"] == "organisation_website" and "no website, newsroom or leadership page recorded" in u["reason"]
               for u in no_site["unavailable"])
    db.run("org_set_website", id=org, website="https://www.example-air.example")
    web = Web({"https://www.example-air.example/": _page("Example Air", "Welcome."),
               "https://www.example-air.example/leadership": _page("Leadership", "Peter Otieno, Country Manager Kenya, leads our Nairobi office.")})
    out = rs.research(db, config.load({"ENVIRONMENT": "test"}), opp, META, fetch=web)
    assert "organisation_pages" in out["methods"], out
    peter = next((f for f in out["found"] if f["name"] == "Peter Otieno"), None)
    assert peter, (out["found"], out["unavailable"], web.fetched)
    # the homepage offers no links, so the guessed address was tried and is labelled as guessed
    assert peter["source"] == "https://www.example-air.example/leadership" and "guessed address" in peter["method"]
    d = rs.person_detail(db, peter["person_id"])
    # a sentence on the company's site does not by itself establish who employs the person: the organisation stays open
    assert d["person"]["organisation_id"] is None and d["roles"][0]["role_title"] == "Country Manager Kenya"
    assert d["evidence"][0]["source_kind"] == "research_document"
    # derived state agrees with the domain rule in every combination
    for ident, rels, routes in ((False, 0, 0), (True, 0, 0), (True, 0, 1), (False, 1, 0), (True, 1, 1)):
        assert rel.derive_state(identity_confirmed=ident, current_relationships=rels, available_routes=routes) == (
            "existing_relationship" if rels else "introduction_available" if routes else "identity_confirmed" if ident else "research_candidate")
    with pytest.raises(rs.RelationshipRejected):
        rs.set_linkedin_profile(db, peter["person_id"], "https://www.linkedin.com/company/example-air/", META)
    with pytest.raises(rs.RelationshipRejected):
        rs.add_route(db, peter["person_id"], {"introducer_person_id": peter["person_id"], "connection_basis": "self introduction, invalid"}, META)
    # a reviewer can record the organisation of a person research could not place (it is never assumed from the document)
    rs.update_person(db, peter["person_id"], {"organisation_id": None, "organisation_label": "Example Air Kenya branch"}, META)
    after = rs.person_detail(db, peter["person_id"])["person"]
    assert after["organisation_id"] is None and after["organisation"] == "Example Air Kenya branch"
    rs.update_person(db, peter["person_id"], {"notes": "unchanged organisation"}, META)
    assert rs.person_detail(db, peter["person_id"])["person"]["organisation"] == "Example Air Kenya branch"
