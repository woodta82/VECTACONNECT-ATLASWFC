"""The four research purposes without a tender, on PostgreSQL (29 Oct 2026): company discovery in a new country from public pages,
standalone people discovery with a brief, market research through Discover, a supplied station list preserved as data awaiting
verification, verification by a person, and a researched company leading to a commercial opportunity only with an interpretation.

SIMULATED: the fixture site's invented Rwanda pages are served through the synthetic fetcher (tests.integration.test_review3_regressions.Web),
a scripted search stand-in returns them, and the extractor is scripted. No real site, search provider or AI provider is used.
"""
from __future__ import annotations

import io
from pathlib import Path

import openpyxl

from app import config
from app.connectors.search import SearchResult
from app.services import company_intelligence as cmp
from app.services import contact_discovery as cd
from app.services import discovery as dsc
from app.services import relationship_service as rs
from tests.integration.sa import sadb  # noqa: F401
from tests.integration.test_relationship_journey import META, client_for
from tests.integration.test_review3_regressions import Web, model, rdb  # noqa: F811, F401

SITE = Path(__file__).resolve().parents[1] / "fixtures" / "site"
BASE = "http://127.0.0.1:8089"
SEARCH = config.load({"ENVIRONMENT": "test", "SEARCH_PROVIDER": "brave", "SEARCH_API_KEY": "search-key-not-real", "SEARCH_MAX_QUERIES": "6",
                      "ANTHROPIC_API_KEY": "key-not-real", "AI_MODEL": "fixture", "AI_PRICE_INPUT_PER_MTOK": "3", "AI_PRICE_OUTPUT_PER_MTOK": "15"})
NOAI = config.load({"ENVIRONMENT": "test", "SEARCH_PROVIDER": "brave", "SEARCH_API_KEY": "search-key-not-real", "SEARCH_MAX_QUERIES": "6"})
KGL_ROUTE = ("Savanna Example Air will operate a weekly Boeing 737 freighter service between Nairobi (NBO) and Kigali (KGL) from 12 January 2027, "
             "citing growing horticulture and pharmaceutical exports from Rwanda.")


def rw_site() -> Web:
    pages = {}
    for rel in ("kgl-directory/cargo-agents.html", "thousandhills/index.html", "thousandhills/airlines.html", "thousandhills/team.html",
                "thousandhills/contact.html", "rw-news/freighter.html"):
        pages[f"{BASE}/{rel}"] = (SITE / rel).read_bytes()
    pages[f"{BASE}/thousandhills/"] = pages[f"{BASE}/thousandhills/index.html"]
    return Web(pages)


def rw_search(log: list[str]):
    def search(_s, query, country, count):
        log.append(query)
        q = query.lower()
        hits = []
        if "gssa" in q or "forwarder" in q or "directory" in q:
            hits.append(SearchResult(f"{BASE}/kgl-directory/cargo-agents.html", "Kigali air cargo agents — directory", ""))
        if "represented airlines" in q:
            hits.append(SearchResult(f"{BASE}/thousandhills/airlines.html", "Airlines we represent — Thousand Hills Cargo Services", ""))
        if "head of cargo" in q or "leadership" in q:
            hits.append(SearchResult(f"{BASE}/thousandhills/team.html", "Our leadership — Thousand Hills Cargo Services", ""))
        if "new route" in q or "freighter" in q:
            hits.append(SearchResult(f"{BASE}/rw-news/freighter.html", "Savanna Example Air adds weekly freighter to Kigali", ""))
        return hits
    return search


def extractor(doc: str) -> dict:
    if KGL_ROUTE in doc:
        return {"language": "en", "claims": [{"claim_type": "route_launch", "stance": "supports", "quote": KGL_ROUTE, "fields": {
            "airline": {"value": "Savanna Example Air", "quote": KGL_ROUTE}, "origin": {"value": "Kenya", "quote": KGL_ROUTE},
            "destination": {"value": "Rwanda", "quote": KGL_ROUTE}}}]}
    return {"language": "en", "claims": []}


def test_company_discovery_in_a_new_country_without_a_tender_builds_company_people_and_representation_intelligence(rdb):  # noqa: F811
    db = rdb
    assert db.pg.val("SELECT count(*) FROM opportunities") == "0" and db.pg.val("SELECT count(*) FROM organisations WHERE country = 'RW'") == "0"
    asked: list[str] = []
    out = cd.start(db, NOAI, {"purpose": "companies", "brief": "Find cargo GSAs operating in Rwanda and the airlines they represent",
                                "countries": ["RW"], "airport_iata": "KGL", "capability_area": "airline_representation",
                                "requested_by_label": "WFC network development"}, META, fetch=rw_site(), search_transport=rw_search(asked))
    assert out["purpose"] == "companies" and out["outcome"] == "companies_found", out["coverage"]
    assert asked and all('"Rwanda"' in q for q in asked) and any("Kigali" in q for q in asked)
    orgs = {o["canonical_name"]: o for o in out["organisations"]}
    assert "Thousand Hills Cargo Services Ltd" in orgs, set(orgs)
    th = orgs["Thousand Hills Cargo Services Ltd"]
    assert th["kind"] == "gssa" and th["country"] == "RW" and th["origin"] == "discovery" and th["new_record"]
    assert th["website"] == f"{BASE}/thousandhills/"                                           # its own site, from the pages read
    assert {e["value"] for e in th["emails"]} >= {"cargo@thousandhills.example", "reservations@thousandhills.example"}
    assert all(e["status"] == "published" for e in th["emails"])
    reps = {(r["counterparty"], r["relationship"], r["status"]) for r in th["relationships"]}
    assert ("Savanna Example Air", "cargo_representation", "sourced") in reps and ("Kilimanjaro Example Cargo", "cargo_representation", "sourced") in reps
    assert not any(r["relationship"] == "passenger_representation" for r in th["relationships"])   # the ticket-sales agent is a different company
    lake = orgs.get("Lakeside Travel Agency Ltd")
    assert lake and any(r["relationship"] == "passenger_representation" and r["counterparty"] == "Savanna Example Air" for r in lake["relationships"])
    assert orgs["Virunga Freight Forwarders Ltd"]["kind"] == "forwarder" and orgs["Nyungwe Ground Handling Ltd"]["kind"] == "handler"
    assert th["relevance_score"] > orgs["Lakeside Travel Agency Ltd"]["relevance_score"]            # a GSSA fits the brief; a ticket agent does not
    assert sum(c["points"] for c in th["relevance"]["components"]) == th["relevance_score"]
    assert th["quote"] and th["source_url"]                                                           # evidence for the record
    # people bound to the company by its own leadership page
    people = {p["full_name"]: p for p in out["people"]}
    assert {"Alice Uwase", "Jean Bosco Habimana"} <= set(people), set(people)
    assert people["Alice Uwase"]["organisation"] == "Thousand Hills Cargo Services Ltd" and people["Alice Uwase"]["role_title"] == "Managing Director"
    assert all(p["state"] == "research_candidate" for p in out["people"]) and all(p["linkedin_search_url"] for p in out["people"])
    # the company profile: locations, parent group, services, evidence per fact, nothing verified yet, no opportunity created
    prof = cmp.profile(db, th["organisation_id"])
    assert prof["parent_group"] == "Umubano Logistics Group" and "Kigali" in (prof["locations_text"] or "")
    assert prof["services_text"] and "cargo sales" in prof["services_text"].lower()
    assert prof["state"] == "researched" and prof["verified_at"] is None and prof["opportunities"] == 0
    assert {e["supports"] for e in prof["evidence"]} >= {"identity", "kind", "website", "email", "representation"}
    assert all(e["quote"] or e["note"] for e in prof["evidence"])
    assert [p["full_name"] for p in prof["people"]] == ["Alice Uwase", "Jean Bosco Habimana"]
    assert db.pg.val("SELECT count(*) FROM opportunities") == "0"                                      # a relevant company is not an opportunity
    # the discovery is listed under its purpose; the companies directory filters to it
    assert cd.list_discoveries(db, purpose="companies")[0]["organisations_found"] == len(out["organisations"])
    listed = cmp.list_companies(db, kind=None, country="RW", airport=None, origin=None, carrier_type=None, state=None, discovery=out["id"], q=None,
                                sort="relevance", limit=50, offset=0)
    assert listed["items"][0]["canonical_name"] == "Thousand Hills Cargo Services Ltd" and listed["total"] >= 4
    # re-running the brief creates no duplicate company, address or relationship
    again = cd.start(db, NOAI, {"purpose": "companies", "brief": "cargo GSAs in Rwanda", "countries": ["RW"]}, META, fetch=rw_site(), search_transport=rw_search([]))
    assert db.pg.val("SELECT count(*) FROM organisations WHERE canonical_name = 'Thousand Hills Cargo Services Ltd' AND merged_into_id IS NULL") == "1"
    assert db.pg.val(f"SELECT count(*) FROM organisation_contacts WHERE organisation_id = '{th['organisation_id']}' AND value = 'cargo@thousandhills.example'") == "1"
    assert not any(o["new_record"] for o in again["organisations"] if o["canonical_name"] == "Thousand Hills Cargo Services Ltd")


def test_people_discovery_with_a_brief_and_market_research_work_without_any_tender(rdb):  # noqa: F811
    db = rdb
    asked: list[str] = []
    out = cd.start(db, NOAI, {"purpose": "people", "brief": "Identify cargo commercial leaders in Rwanda", "countries": ["RW"]}, META,
                   fetch=rw_site(), search_transport=rw_search(asked))
    assert out["purpose"] == "people" and "Identify cargo commercial leaders in Rwanda" in out["brief"]
    assert any("head of cargo" in q.lower() for q in asked)
    names = {p["full_name"] for p in out["people"]}
    assert {"Alice Uwase", "Jean Bosco Habimana"} <= names and out["outcome"] in ("people_found", "incomplete")
    # market intelligence through Discover: no tender, no deadline, no procurement reference — a market signal, never blocked
    db.run("flag_set", key="ai_kill_switch", value="false")
    sid = dsc.create_search(db, dsc.SearchSpec("country", ["RW"], [], [], purpose="market", brief="airline expansion that could create representation opportunities"))
    search = db.one("search_get", id=sid)
    assert search["purpose"] == "market" and search["brief"].startswith("airline expansion")
    plan = dsc.plan(db, search, None, SEARCH)
    assert plan["open_web"]["planned"] and all(s["type"] not in ("search_template", "listing") for s in plan["sources"])
    started = dsc.start_run(db, SEARCH, search_id=sid)
    res = dsc.execute_run(db, SEARCH, started["run_id"], None, fetch=rw_site(), transport=model(extractor), search_transport=rw_search(asked))
    assert res["outcome"] == "results", res
    assert db.pg.val("SELECT count(*) FROM signals WHERE merged_into_id IS NULL") == "1"
    assert db.pg.val("SELECT classification FROM signals WHERE merged_into_id IS NULL") == "market_signal"
    assert db.pg.val("SELECT count(*) FROM opportunities") == "0"                      # a press release is not buying demand
    # the control-panel summaries separate it from opportunities and tender deadlines
    c = client_for(db)
    try:
        s = c.get("/control-panel/summaries").json()["summaries"]
        by = {x["key"]: x for x in s}
        assert by["market"]["count"] >= 1 and by["market"]["items"][0]["link"].startswith("/signals/")
        assert by["deadlines"]["count"] == 0 and by["opportunities"]["count"] == 0
        assert by["people"]["count"] >= 2 and by["companies"]["link"].startswith("/companies")
        assert [x["key"] for x in s] == ["opportunities", "companies", "people", "gaps", "market", "deadlines"]
        # a person tracks the signal as a commercial opportunity: it is then counted, still never a tender
        sig_id = db.pg.val("SELECT id FROM signals WHERE merged_into_id IS NULL LIMIT 1")
        opp = rs.track_signal(db, sig_id, META)
        s2 = {x["key"]: x for x in c.get("/control-panel/summaries").json()["summaries"]}
        assert s2["opportunities"]["count"] == 1 and s2["deadlines"]["count"] == 0
        assert db.pg.val(f"SELECT record_type FROM opportunities WHERE id = '{opp}'") == "commercial"
    finally:
        c.__exit__(None, None, None)


def _workbook() -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "GSA l BRU"
    ws.append(["GSA", "Represented Airlines", "E-mail address"])
    ws.append(["Example GSA Services NV", "LO | M6 | FO", "cargo@example-gsa.example"])
    ws.append(["All-Carriers Cargo BV", "ALL", "ops@allcarriers.example"])
    ws2 = wb.create_sheet("AIRLINE | BRU")
    ws2.append(["Type", "Represented Airlines", "E-mail address"])
    ws2.append(["Passenger/Belly", "IB/VY", "bru.cargo@iberia.example"])
    ws2.append(["Cargo-only", "CV", "sales.bru@cargolux.example"])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_a_supplied_station_list_is_preserved_as_data_awaiting_verification_and_a_person_verifies_it(rdb):  # noqa: F811
    db = rdb
    res = cmp.import_supplied(db, SEARCH, data=_workbook(), filename="FF__GSA_List_BRU.xlsx", name=None, notes="benchmark example", meta=META, by="WFC ops")
    assert res["airport_iata"] == "BRU" and res["country"] == "BE" and res["rows"] == 4
    assert res["organisations"] == 8 and res["relationships"] == 3 and res["contacts"] == 5   # the IB/VY address is recorded for both carriers
    gsa = cmp.list_companies(db, kind="gssa", country="BE", airport="BRU", origin="supplied", carrier_type=None, state="awaiting_verification", discovery=None,
                             q=None, sort="name", limit=50, offset=0)
    assert [o["canonical_name"] for o in gsa["items"]] == ["All-Carriers Cargo BV", "Example GSA Services NV"]
    ex = next(o for o in gsa["items"] if o["canonical_name"] == "Example GSA Services NV")
    prof = cmp.profile(db, ex["id"])
    assert prof["state"] == "awaiting_verification" and prof["origin"] == "supplied" and prof["website"] is None
    assert [c["status"] for c in prof["contacts"]] == ["supplied"] and prof["contacts"][0]["value"] == "cargo@example-gsa.example"
    rels = {(r["counterparty_code"], r["status"], r["relationship"]) for r in prof["relationships"]}
    assert rels == {("LO", "supplied", "cargo_representation"), ("M6", "supplied", "cargo_representation"), ("FO", "supplied", "cargo_representation")}
    assert any(r["counterparty"] == "LOT Polish Airlines" for r in prof["relationships"])          # designator resolved as a reading aid
    assert any("not resolved" in (r["counterparty"] or "") for r in prof["relationships"])         # FO is kept as written
    assert any("not assumed current" in r["basis"] for r in prof["relationships"])
    assert "Research this company" in " ".join(prof["actions"]) and "Confirm or mark as lapsed" in " ".join(prof["actions"])
    allc = cmp.profile(db, next(o["id"] for o in gsa["items"] if o["canonical_name"] == "All-Carriers Cargo BV"))
    assert allc["relationships"] == [] and any("'ALL'" in (e["note"] or "") for e in allc["evidence"])
    # airlines from the second sheet: belly carriers kept apart from cargo-only, each marked supplied
    air = cmp.list_companies(db, kind="airline", country=None, airport=None, origin=None, carrier_type="passenger_belly", state=None, discovery=None, q=None,
                             sort="name", limit=50, offset=0)
    assert {o["canonical_name"] for o in air["items"]} == {"Iberia", "Vueling"}
    cv = cmp.list_companies(db, kind="airline", country=None, airport=None, origin=None, carrier_type="cargo_only", state=None, discovery=None, q=None,
                            sort="name", limit=50, offset=0)["items"]
    assert [o["canonical_name"] for o in cv] == ["Cargolux"] and cmp.profile(db, cv[0]["id"])["contacts"][0]["status"] == "supplied"
    # the rows are preserved exactly as supplied, and the same file is not imported twice
    imp = cmp.supplied_import_detail(db, res["id"])
    raws = [r["raw"] for r in imp["rows"]]
    assert {"GSA": "All-Carriers Cargo BV", "Represented Airlines": "ALL", "E-mail address": "ops@allcarriers.example"} in raws, raws
    try:
        cmp.import_supplied(db, SEARCH, data=_workbook(), filename="FF__GSA_List_BRU.xlsx", name=None, notes=None, meta=META)
        raise AssertionError("duplicate import accepted")
    except cmp.CompanyRejected as exc:
        assert exc.status == 409
    # a person verifies: the record, one address and one representation — each with a basis; nothing is verified without one
    try:
        cmp.verify(db, ex["id"], "short", None, META)
        raise AssertionError("verification without a basis accepted")
    except cmp.CompanyRejected:
        pass
    cmp.edit(db, ex["id"], {"website": "https://www.example-gsa.example/", "basis": "website confirmed on the company's own pages"}, META)
    cmp.verify(db, ex["id"], "Website, kind and Brussels office confirmed on the company's own pages on 29 Oct 2026", "https://www.example-gsa.example/about", META)
    cmp.set_contact_status(db, ex["id"], prof["contacts"][0]["id"], "verified", "shown on the contact page", META)
    lo = next(r for r in prof["relationships"] if r["counterparty_code"] == "LO")
    cmp.set_relationship_status(db, ex["id"], lo["id"], "confirmed", "listed on the airlines page of the company's site, 29 Oct 2026", "WFC ops", META)
    fo = next(r for r in prof["relationships"] if r["counterparty_code"] == "FO")
    cmp.set_relationship_status(db, ex["id"], fo["id"], "lapsed", "not listed on the company's current airlines page", "WFC ops", META)
    prof2 = cmp.profile(db, ex["id"])
    assert prof2["state"] == "verified" and prof2["contacts"][0]["status"] == "verified"
    assert {(r["counterparty_code"], r["status"]) for r in prof2["relationships"]} == {("LO", "confirmed"), ("M6", "supplied"), ("FO", "lapsed")}
    # a researched company leads to an opportunity only when a person records the interpretation
    try:
        cmp.create_opportunity(db, ex["id"], {"module": "airline_representation", "interpretation": "too short"}, META)
        raise AssertionError("opportunity without an interpretation accepted")
    except cmp.CompanyRejected:
        pass
    opp = cmp.create_opportunity(db, ex["id"], {"module": "airline_representation", "country": "BE",
                                                "interpretation": "The FO mandate has lapsed at this GSA: an opening for WFC to offer representation of FO at BRU"}, META)
    assert opp["new"] and db.pg.val(f"SELECT record_type FROM opportunities WHERE id = '{opp['id']}'") == "commercial"
    assert db.pg.val(f"SELECT origin_interpretation FROM opportunities WHERE id = '{opp['id']}'").startswith("The FO mandate")
    assert cmp.profile(db, ex["id"])["opportunities"] == 1
    assert db.pg.val(f"SELECT count(*) FROM opportunity_geography WHERE opportunity_id = '{opp['id']}' AND country_code = 'BE'") == "1"
    again = cmp.create_opportunity(db, ex["id"], {"module": "airline_representation", "country": "BE",
                                                  "interpretation": "The FO mandate has lapsed at this GSA: an opening for WFC to offer representation of FO at BRU"}, META)
    assert again["id"] == opp["id"] and not again["new"]
