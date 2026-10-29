"""Relationship intelligence to the ATLAS v1.0 parameters, on PostgreSQL (29 Oct 2026): open-market contact discovery from the
organisation's pages and the authorised search; relevance to the brief; stakeholder judgements; engagement outcomes; health
with its breakdown and the at-risk cap; the five questions; the relationship share of an opportunity's score; outreach
drafted by ATLAS and sent only by a person.

SIMULATED: synthetic pages (tests.integration.test_review3_regressions.Web) and a scripted search stand-in; no real site,
search provider or AI provider is used.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app import config
from app.connectors.search import SearchResult
from app.services import contact_discovery as cd
from app.services import relationship_intelligence as ri
from app.services import relationship_service as rs
from tests.integration.sa import sadb  # noqa: F401
from tests.integration.test_relationship_journey import META, client_for
from tests.integration.test_relationship_research import NO_AI, SITE, _html, _opp, _org, company_site
from tests.integration.test_review3_regressions import Web, rdb  # noqa: F401

UTC = timezone.utc
SEARCH = config.load({"ENVIRONMENT": "test", "SEARCH_PROVIDER": "brave", "SEARCH_API_KEY": "search-key-not-real", "SEARCH_MAX_QUERIES": "4"})


def _press_site() -> Web:
    pages = dict(company_site().pages)
    pages["https://press.example/example-air-cco"] = _html("Example Air names Chief Commercial Officer",
                                                           "<p>Example Air has appointed Amina Yusuf as Chief Commercial Officer, effective 1 January 2027.</p>")
    return Web(pages)


def test_discovery_reads_the_organisations_pages_and_the_search_and_scores_relevance_to_the_brief(rdb):  # noqa: F811
    db = rdb
    opp = _opp(db)
    org = _org(db, opp)
    rs.set_research_pages(db, org, website=f"{SITE}/", newsroom=None, leadership=None, meta=META)
    asked: list[str] = []

    def search(_s, query, country, count):
        asked.append(query)
        return [SearchResult("https://press.example/example-air-cco", "Example Air names CCO", "")] if "appoint" in query else []
    out = cd.start(db, SEARCH, {"organisation_name": "Example Air", "countries": ["KE"], "capability_area": "airline_representation",
                                "requested_by_label": "WFC Kenya commercial lead"}, META, fetch=_press_site(), search_transport=search)
    assert out["outcome"] in ("people_found", "incomplete"), out["coverage"]
    assert "organisation_pages" in out["methods"] and "web_search" in out["methods"]
    assert "Example Air" in out["brief"] and "Airline representation" in out["brief"] and "Kenya" in out["brief"]
    assert asked and all('"Example Air"' in q for q in asked)
    people = {p["full_name"]: p for p in out["people"]}
    assert {"Maria Lopez", "Peter Otieno", "Daniel Kiprop", "Amina Yusuf"} <= set(people), set(people)
    assert "John Lee" in people and people["John Lee"]["organisation"] == "Blue Ridge Handling"     # a partner, found but not of Example Air
    # relevance: every point explained; the leadership-page head of cargo at the named organisation in the brief's country scores highest
    maria = people["Maria Lopez"]
    assert maria["relevance_score"] >= 85 and sum(c["points"] for c in maria["relevance"]["components"]) == maria["relevance_score"]
    assert {c["key"] for c in maria["relevance"]["components"]} == {"role_fit", "seniority", "organisation", "geography", "evidence"}
    assert people["John Lee"]["relevance_score"] < maria["relevance_score"]
    assert all(p["state"] == "research_candidate" for p in out["people"])                             # nobody is confirmed by discovery
    assert all(p["linkedin_search_url"].startswith("https://www.linkedin.com/search/") for p in out["people"])
    assert all(p["source_url"] for p in out["people"]) and all(p["quote"] for p in out["people"])     # evidence for every contact
    assert any(u["method"] == "linkedin_profiles" for u in out["unavailable"])
    assert db.pg.val(f"SELECT capability_area FROM people WHERE id = '{maria['person_id']}'") == "airline_representation"
    assert db.pg.val(f"SELECT origin FROM people WHERE id = '{maria['person_id']}'") == "discovery"
    # the discovery is listed, with its documents and what was and was not searched
    listed = cd.list_discoveries(db)
    assert listed[0]["id"] == out["id"] and listed[0]["people_found"] == len(out["people"]) and listed[0]["runs"] == 1
    assert any(d["origin"] == "search_result" for d in out["documents"]) and any(d["origin"] == "followed_link" for d in out["documents"])
    # re-running the same brief creates no second record for the same passage
    again = cd.start(db, SEARCH, {"organisation_name": "Example Air", "countries": ["KE"], "capability_area": "airline_representation"}, META,
                     fetch=_press_site(), search_transport=search)
    assert db.pg.val("SELECT count(*) FROM people WHERE full_name = 'Maria Lopez' AND merged_into_id IS NULL") == "1"
    assert not any(p["new_record"] for p in again["people"] if p["full_name"] == "Maria Lopez")


def test_without_a_search_connector_or_a_known_organisation_the_discovery_is_not_run_and_says_what_to_do(rdb):  # noqa: F811
    db = rdb
    out = cd.start(db, NO_AI, {"organisation_name": "Unknown Cargo Ltd", "countries": ["TZ"], "capability_area": "forwarder_sales",
                               "role_focus": "head of sales"}, META, fetch=Web({}))
    assert out["outcome"] == "not_run" and out["people"] == []
    assert all(s["status"] == "not_run" and s["link"].startswith("https://www.google.com/search?q=") for s in out["searches"])
    assert any("not a known organisation record" in u["reason"] for u in out["unavailable"])
    assert any("search connector" in a for a in out["actions"])
    assert out["searches"][0]["query"].startswith('"Unknown Cargo Ltd" "head of sales"')


def test_judgements_engagements_health_questions_impact_and_outreach(rdb):  # noqa: F811
    db = rdb
    opp = _opp(db)
    c = client_for(db)
    res = c.post(f"/opportunities/{opp}/research").json()
    jane = next(f for f in res["found"] if f["name"] == "Jane Wanjiru")
    pid = jane["person_id"]
    # health is not assessed until something is recorded; the judgement needs a basis
    h0 = c.get(f"/people/{pid}/health").json()
    assert h0["health"]["assessed"] is False and h0["health"]["band_label"] == "Not assessed"
    refused = c.post(f"/people/{pid}/judgement", json={"stakeholder_type": "procurement_authority", "basis": "short"})
    assert refused.status_code == 422
    assert c.post(f"/people/{pid}/judgement", json={"stakeholder_type": "procurement_authority", "decision_authority": "shared", "posture": "neutral",
                                                     "basis": "Named as the procurement contact in the RFP; the tender board decides",
                                                     "by_label": "WFC Kenya commercial lead", "strategic_account": True}).status_code == 200
    # a quiet procurement authority: outbound approaches unanswered, last contact 120 days ago -> at risk, capped at 40
    old = (datetime.now(UTC) - timedelta(days=120)).isoformat()
    for i in range(2):
        assert c.post(f"/people/{pid}/engagements", json={"kind": "email", "summary": f"Introduction email {i + 1}", "occurred_at": old,
                                                           "outcome": "no_response", "direction": "outbound", "opportunity_id": opp}).status_code == 200
    h1 = c.get(f"/people/{pid}/health").json()
    assert h1["health"]["assessed"] and h1["health"]["at_risk"] and h1["health"]["score"] <= 40
    assert {x["factor"] for x in h1["health"]["contributions"]} == {"recency", "frequency", "responsiveness", "meeting_outcomes", "influence",
                                                                    "opportunity_alignment", "strategic_value"}
    assert h1["stakeholder"]["type_label"] == "Procurement authority" and h1["momentum"]["state"] == "declining"
    assert "this week" in h1["recommended_action"]
    # a positive meeting today lifts it out of the at-risk cap
    assert c.post(f"/people/{pid}/engagements", json={"kind": "meeting", "summary": "Met at the airline's office; agreed next steps",
                                                       "outcome": "positive", "direction": "mutual", "opportunity_id": opp}).status_code == 200
    h2 = c.get(f"/people/{pid}/health").json()
    assert not h2["health"]["at_risk"] and h2["health"]["score"] > h1["health"]["score"]
    # the five questions
    q = c.get("/relationships/questions").json()
    assert q["who_matters_most"][0]["person_id"] == pid and q["who_matters_most"][0]["importance"] > 0
    assert any(g["opportunity_id"] == opp and g["missing"] == "economic_buyer" for g in q["who_are_we_missing"])
    assert any(r["person_id"] == pid for r in q["where_to_invest_time"]) and "not a probability" in q["rule"].lower()
    assert q["totals"]["assessed"] >= 1
    # the relationship share of the opportunity's score
    imp = c.get(f"/relationships/impact/{opp}").json()
    assert imp["scored"] and imp["relationship_max"] == 25 and imp["headroom"] == 25 - imp["relationship_points"]
    # the directory carries health and can be sorted by attention and exported
    page = c.get("/people", params={"sort": "attention"}).json()
    assert page["items"][0]["id"] == pid and page["items"][0]["health_score"] == h2["health"]["score"]
    assert page["items"][0]["stakeholder_label"] == "Procurement authority"
    csv = c.get("/people/export.csv").text
    assert "Jane Wanjiru" in csv and "Health (0-100)" in csv and "not a probability" in csv
    # outreach: drafted from the record (AI not connected -> template), edited, then sent by a person -> an outbound engagement
    d = c.post(f"/people/{pid}/outreach-drafts", json={"channel": "email", "opportunity_id": opp, "sender_label": "WFC Kenya commercial lead"}).json()
    assert d["source"] == "template" and d["status"] == "draft" and "Jane Wanjiru" in d["body"] and "EXA-GSSA-2026-301" in d["body"]
    assert any("AI rewording not available" in b for b in d["basis"])
    assert c.post(f"/outreach-drafts/{d['id']}", json={"body": d["body"] + "\n\nP.S. Happy to meet at the airline's office."}).status_code == 200
    assert c.post(f"/outreach-drafts/{d['id']}/status", json={"status": "sent"}).status_code == 422          # who sent it?
    before = db.pg.val(f"SELECT count(*) FROM engagements WHERE person_id = '{pid}'")
    assert c.post(f"/outreach-drafts/{d['id']}/status", json={"status": "sent", "by_label": "WFC Kenya commercial lead"}).status_code == 200
    assert int(db.pg.val(f"SELECT count(*) FROM engagements WHERE person_id = '{pid}'")) == int(before) + 1
    assert db.pg.val(f"SELECT outcome FROM engagements WHERE person_id = '{pid}' ORDER BY created_at DESC LIMIT 1") == "pending"
    assert c.post(f"/outreach-drafts/{d['id']}", json={"body": "changed after sending"}).status_code == 409
    detail = c.get(f"/people/{pid}").json()
    assert detail["intelligence"]["health"]["assessed"] and detail["outreach"][0]["status"] == "sent"
    assert db.pg.val("SELECT count(*) FROM audit_events WHERE event_type IN ('stakeholder_judgement','outreach_drafted','outreach_sent')") == "3"
    c.__exit__(None, None, None)
