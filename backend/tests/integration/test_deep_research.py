"""Staged, resumable research and the research file, on PostgreSQL (30 Oct 2026): a country and an airport outside the old shortlist
(Lithuania, Kaunas KUN), no tender; a commercial opportunity found from a public announcement and tracked by a person; the six stages
enrich the canonical company and person records; continuation duplicates nothing; honest gaps where the public information is not
there; belly-cargo carriers kept, passenger-only sales excluded; the Dashboard shows the result and the next action.

SIMULATED: the fixture site's invented Lithuanian pages through the synthetic fetcher, a scripted search stand-in and a scripted extractor.
"""
from __future__ import annotations

from pathlib import Path

from app import config
from app.connectors.search import SearchResult
from app.services import airport_directory as ad
from app.services import company_intelligence as cmp
from app.services import contact_discovery as cd
from app.services import deep_research as dr
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
QLT = ("Amber Example Air invites expressions of interest from cargo GSSA providers for Lithuania and Latvia from April 2027, as its current cargo "
       "representation agreement ends.")


def lt_site(*, sales_team: bool = False, notices: bool = False) -> Web:
    pages = {}
    for rel in ("lt-cargo/directory.html", "nemunascargo/index.html", "nemunascargo/airlines.html", "nemunascargo/team.html", "nemunascargo/contact.html",
                "lt-news/amber-gssa.html") + (("nemunascargo/sales-team.html",) if sales_team else ()) + (("nemunascargo/notices.html",) if notices else ()):
        pages[f"{BASE}/{rel}"] = (SITE / rel).read_bytes()
    pages[f"{BASE}/nemunascargo/"] = pages[f"{BASE}/nemunascargo/index.html"]
    return Web(pages)


def lt_search(log: list[str], *, sales_team: bool = False, notices: bool = False):
    def search(_s, query, country, count):
        log.append(query)
        q = query.lower()
        hits = []
        if ("gssa" in q or "forwarder" in q or "directory" in q) and ("lithuania" in q or "kaunas" in q):
            hits.append(SearchResult(f"{BASE}/lt-cargo/directory.html", "Air cargo service providers at Kaunas Airport — directory", ""))
        if ("tender" in q or "appoint" in q or "expressions of interest" in q or "amber example air" in q) and "lithuania" in q:
            hits.append(SearchResult(f"{BASE}/lt-news/amber-gssa.html", "Amber Example Air seeks cargo GSSA partners for Lithuania and Latvia", ""))
        if "nemunas cargo services" in q and "official website" in q:
            hits.append(SearchResult(f"{BASE}/nemunascargo/index.html", "Nemunas Cargo Services", ""))
        if "nemunas cargo services" in q and "contact" in q:
            hits.append(SearchResult(f"{BASE}/nemunascargo/contact.html", "Contact — Nemunas Cargo Services", ""))
            if notices:
                hits.append(SearchResult(f"{BASE}/nemunascargo/notices.html", "Contact changes — Nemunas Cargo Services", ""))
        if "nemunas cargo services" in q and ("head of cargo" in q or "leadership" in q):
            hits.append(SearchResult(f"{BASE}/nemunascargo/team.html", "Our leadership — Nemunas Cargo Services", ""))
            if sales_team:
                hits.append(SearchResult(f"{BASE}/nemunascargo/sales-team.html", "Cargo sales team — Nemunas Cargo Services", ""))
        return hits
    return search


def extractor(doc: str) -> dict:
    if QLT in doc:
        return {"language": "en", "claims": [{"claim_type": "gssa_tender", "stance": "supports", "quote": QLT, "fields": {
            "airline": {"value": "Amber Example Air", "quote": QLT}, "country": {"value": "Lithuania", "quote": QLT},
            "service": {"value": "GSSA", "quote": QLT}, "status": {"value": "announced", "quote": QLT}}}]}
    return {"language": "en", "claims": []}


def test_airport_directory_search_and_scope_outside_the_old_shortlist(rdb):  # noqa: F811
    db = rdb
    st = ad.status(db)
    assert st["airports"] >= 400 and not st["maintained"] and st["using"] == "seed" and "bundled seed" in st["note"]
    kun = ad.resolve(db, "KUN")
    assert kun and kun["icao"] == "EYKA" and kun["country"] == "LT"
    assert [a["iata"] for a in ad.search(db, "kaunas")][0] == "KUN" and ad.search(db, "EYKA")[0]["iata"] == "KUN"
    assert {a["iata"] for a in ad.search(db, None, country="LT")} >= {"VNO", "KUN", "PLQ"}
    # the maintained dataset: airports without an IATA code are selectable, closed ones labelled, provenance recorded
    csv = ("id,ident,type,name,latitude_deg,longitude_deg,elevation_ft,continent,iso_country,iso_region,municipality,scheduled_service,gps_code,iata_code,local_code,home_link,wikipedia_link,keywords\n"
           "1,EYKA,medium_airport,Kaunas International Airport,54.96,24.08,256,EU,LT,LT-KU,Kaunas,yes,EYKA,KUN,,,,Karmelava\n"
           "3,EYRU,small_airport,Rukla Airfield,55.05,24.3,300,EU,LT,LT-KU,Rukla,no,EYRU,,,,,\n"
           "4,EYKL,closed,Klaipeda Airport,55.70,21.24,10,EU,LT,LT-KL,Klaipeda,no,,,,,,\n")
    out = ad.load_ourairports(db, csv, version="2026-10-01")
    assert out["rows"] == 3 and out["dataset"]["source"].startswith("OurAirports") and out["dataset"]["version"] == "2026-10-01"
    assert ad.resolve(db, "KUN")["source_key"] == "ourairports" and ad.resolve(db, "KUN")["name"] == "Kaunas International Airport"
    assert ad.search(db, "rukla")[0]["iata"] is None and "no IATA code" in ad.search(db, "rukla")[0]["label"]
    assert ad.search(db, "karmelava")[0]["iata"] == "KUN"                                            # keyword alias from the dataset
    assert ad.resolve(db, "EYKL")["status"] == "closed" and all(a["status"] != "closed" for a in ad.search(db, None, country="LT"))
    assert ad.status(db)["maintained"] and ad.status(db)["using"] == "partial"                        # a 3-row file is never called the full directory


def lt_opportunity(db, asked: list[str]) -> str:
    """A commercial opportunity from the public announcement (no tender platform), tracked by a person."""
    db.run("flag_set", key="ai_kill_switch", value="false")
    sid = dsc.create_search(db, dsc.SearchSpec("country", ["LT"], [], ["airline_representation"], airports=["KUN"]))
    started = dsc.start_run(db, SEARCH, search_id=sid)
    res = dsc.execute_run(db, SEARCH, started["run_id"], None, fetch=lt_site(), transport=model(extractor), search_transport=lt_search(asked))
    assert res["outcome"] == "results", res
    assert any("Kaunas" in w["query"] for w in res["counts"]["web_searches"])                        # the airport scope reaches the queries
    sig_id = db.pg.val("SELECT id FROM signals WHERE merged_into_id IS NULL AND title ILIKE '%Amber%' LIMIT 1")
    assert sig_id and db.pg.val("SELECT count(*) FROM opportunities") == "0"                         # not an opportunity until a person decides
    opp_id = rs.track_signal(db, sig_id, META)
    assert db.pg.val(f"SELECT record_type FROM opportunities WHERE id = '{opp_id}'") == "commercial"
    return str(opp_id)


def test_staged_research_builds_the_file_from_canonical_records_and_resumes_without_duplicates(rdb):  # noqa: F811
    db = rdb
    asked: list[str] = []
    # 1-2. a company search for Lithuania at Kaunas (KUN): cargo companies without any tender; belly carrier kept, ticket agent out of scope
    disc = cd.start(db, NOAI, {"purpose": "companies", "brief": "Find cargo GSAs and forwarders at Kaunas and the airlines they represent", "countries": ["LT"],
                               "airports": ["KUN"], "capability_area": "airline_representation"}, META, fetch=lt_site(), search_transport=lt_search(asked))
    assert disc["outcome"] == "companies_found" and disc["airport_labels"] and "Kaunas" in disc["airport_labels"][0]
    assert all('"Lithuania"' in q for q in asked) and any("Kaunas" in q and "KUN" in q for q in asked)
    orgs = {o["canonical_name"]: o for o in disc["organisations"]}
    assert {"Nemunas Cargo Services UAB", "Baltic Ticket Centre UAB", "Amber Example Air", "Vilnius Freight Hub UAB"} <= set(orgs)
    assert orgs["Amber Example Air"]["relevance"]["freight_scope"] == "belly" and orgs["Amber Example Air"]["relevance_score"] > 0
    assert orgs["Baltic Ticket Centre UAB"]["relevance"]["freight_scope"] == "passenger_only" and orgs["Baltic Ticket Centre UAB"]["relevance_score"] == 0
    cargo = cmp.list_companies(db, kind=None, country="LT", airport="KUN", origin=None, carrier_type=None, state=None, discovery=None, q=None, sort="name", scope="cargo", limit=50, offset=0)
    assert "Baltic Ticket Centre UAB" not in {o["canonical_name"] for o in cargo["items"]} and "Nemunas Cargo Services UAB" in {o["canonical_name"] for o in cargo["items"]}
    nem_id = orgs["Nemunas Cargo Services UAB"]["organisation_id"]
    assert orgs["Nemunas Cargo Services UAB"]["website"] is None                                      # the directory entry is not its site: not guessed
    # the airport scope is recorded as a station, not a guess about an office
    prof = cmp.profile(db, nem_id)
    assert [(a["iata"], a["role"]) for a in prof["airports"]] == [("KUN", "station")]
    # 3. a commercial opportunity from a public announcement (no tender platform), tracked by a person
    opp_id = lt_opportunity(db, asked)
    # 4. deep research of the opportunity: six stages, each enriching the canonical records
    out = dr.run(db, NOAI, "opportunity", opp_id, META, fetch=lt_site(), search_transport=lt_search(asked))
    st = {s["stage"]: s for s in out["stages"]}
    assert [s["stage"] for s in out["stages"]] == ["identify", "identity", "company", "people", "relationships", "relevance"]
    assert st["identify"]["status"] == "done" and st["identify"]["counts"]["organisations"] >= 2, st["identify"]
    # the counterparty found on the GSSA's airlines page (Kilimanjaro Example Cargo) came to light after the identity stage: it sits PENDING in
    # that stage's persisted queue, the stage is left incomplete with its counts, and a continuation researches it instead of leaving its fields empty
    assert st["identity"]["status"] == "incomplete" and "found later" in st["identity"]["detail"], st["identity"]
    assert st["identity"]["counts"]["pending"] == 1 and ", 1 pending of " in st["identity"]["progress"], st["identity"]
    assert st["company"]["status"] == "done" and st["people"]["status"] == "done" and st["relationships"]["status"] == "done" and st["relevance"]["status"] == "done"
    queue = {(q["stage"], q["organisation"]): q["status"] for q in out["queue"]}
    assert queue[("identity", "Kilimanjaro Example Cargo")] == "pending" and queue[("company", "Nemunas Cargo Services UAB")] == "done"
    assert out["resumable"]
    f = out["research_file"]
    names = {o["name"]: o for o in f["companies"]}
    assert "Nemunas Cargo Services UAB" in names and "Amber Example Air" in names
    nem = names["Nemunas Cargo Services UAB"]
    assert nem["website"] == f"{BASE}/nemunascargo/" and "names the organisation" in nem["website_basis"]      # found by the targeted follow-up search
    assert nem["contact_url"] == f"{BASE}/nemunascargo/contact.html"
    assert {e["value"] for e in nem["emails"]} >= {"sales@nemunascargo.example", "ops@nemunascargo.example", "cargo@nemunascargo.example"}
    assert {(a["label"].split(" (")[1].rstrip(")"), a["role"]) for a in nem["airports"]} >= {("KUN", "Station (operates here)"), ("VNO", "Served (from elsewhere)")}
    assert ("KUN", "Served (from elsewhere)") not in {(a["label"].split(" (")[1].rstrip(")"), a["role"]) for a in nem["airports"]}   # never beside its station
    depts = {e["value"]: e["department"] for e in nem["emails"]}
    assert depts.get("ruta.kazlauskiene@nemunascargo.example") in (None, "personal") and depts["sales@nemunascargo.example"] == "sales"   # a person's address is never a department
    assert depts["ops@nemunascargo.example"] == "operations"
    assert nem["parent_group"] == "Baltic Example Logistics Group" and "Kaunas" in nem["offices"]
    assert {(r["counterparty"], r["relationship"]) for r in nem["representation"]} >= {("Amber Example Air", "Cargo representation (GSA/GSSA)")}
    assert nem["freight_scope"] == "cargo_services" and nem["in_cargo_scope"]
    assert all(x["status"] == "found" for x in nem["research"]["fields"] if x["field"] in ("website", "contact_page", "emails", "services", "locations", "airports", "representation", "people"))
    amber = names["Amber Example Air"]
    assert amber["website"] is None
    assert next(x for x in amber["research"]["fields"] if x["field"] == "website")["status"] == "not_found_after_research"   # searched, honestly missing
    assert amber["freight_scope"] == "belly"
    people = {p["full_name"]: p for p in f["summary"]["people"]}
    assert {"Ruta Kazlauskiene", "Tomas Petrauskas"} <= set(people), set(people)
    assert people["Ruta Kazlauskiene"]["published_email"] == "ruta.kazlauskiene@nemunascargo.example" and people["Ruta Kazlauskiene"]["email_status"] == "found"
    assert people["Tomas Petrauskas"]["published_email"] is None and people["Tomas Petrauskas"]["email_status"] == "not_found_after_research"
    assert people["Tomas Petrauskas"]["remit_countries"] == [] or isinstance(people["Tomas Petrauskas"]["remit_countries"], list)
    assert f["summary"]["why"]["label"] and f["summary"]["geography"]["countries"] == ["Lithuania"]
    assert any(a["label"].endswith("(KUN)") for a in f["summary"]["geography"]["airports"])
    assert any("Amber Example Air: official website" in u for u in f["summary"]["uncertain"])
    assert any("Tomas Petrauskas: no published e-mail found after research" in u for u in f["summary"]["uncertain"])
    assert f["summary"]["next_action"] and "probability" in f["rule"]
    # 5. the same canonical records serve the Companies directory and Relationships: no second profile anywhere
    assert db.pg.val("SELECT count(*) FROM organisations WHERE canonical_name = 'Nemunas Cargo Services UAB' AND merged_into_id IS NULL") == "1"
    assert db.pg.val("SELECT count(*) FROM people WHERE full_name = 'Ruta Kazlauskiene' AND merged_into_id IS NULL") == "1"
    assert cmp.profile(db, nem_id)["opportunities"] == 0 and str(nem["id"]) == nem_id
    # 6. continuation duplicates nothing and keeps every stage done
    before = {t: db.pg.val(f"SELECT count(*) FROM {t}") for t in ("organisations", "people", "organisation_contacts", "organisation_relationships", "organisation_airports")}
    again = dr.run(db, NOAI, "opportunity", opp_id, META, fetch=lt_site(), search_transport=lt_search(asked))
    assert {t: db.pg.val(f"SELECT count(*) FROM {t}") for t in before} == before
    assert all(s["status"] in ("done", "not_applicable") for s in again["stages"]) and not again["resumable"]
    kili = db.pg.val("SELECT id FROM organisations WHERE canonical_name = 'Kilimanjaro Example Cargo' AND merged_into_id IS NULL")
    assert {x["field"]: x["status"] for x in cmp.profile(db, kili)["research"]["fields"]}["website"] == "not_found_after_research"
    # company research on its own, for the GSSA (its pages found through the targeted search) and for a company whose public information is thin
    ba = orgs["Baltic Ticket Centre UAB"]["organisation_id"]
    own = dr.run(db, NOAI, "organisation", nem_id, META, fetch=lt_site(), search_transport=lt_search(asked))
    assert own["profile"]["website"] == f"{BASE}/nemunascargo/"
    # the counterparties named on its pages joined the run's queues after the identity stage: the stage says so and a continuation finishes them
    ost = {s["stage"]: s for s in own["stages"]}
    assert ost["identity"]["status"] == "incomplete" and ost["identity"]["counts"]["pending"] >= 1, ost["identity"]
    own2 = dr.run(db, NOAI, "organisation", nem_id, META, fetch=lt_site(), search_transport=lt_search(asked))
    assert {s["stage"]: s["status"] for s in own2["stages"]}["identity"] == "done" and not own2["resumable"]
    assert all(q["status"] in ("done", "failed") for q in own2["queue"]), own2["queue"]
    assert db.pg.val(f"SELECT count(*) FROM research_documents WHERE research_organisation_id = '{nem_id}'") >= "1"
    # company research on its own for a company whose public information is thin: honest statuses, nothing invented
    vfh = orgs["Vilnius Freight Hub UAB"]["organisation_id"]
    c = dr.run(db, NOAI, "organisation", vfh, META, fetch=lt_site(), search_transport=lt_search(asked))
    cst = {s["stage"]: s for s in c["stages"]}
    assert cst["identify"]["status"] == "not_applicable" and cst["identity"]["status"] == "done" and cst["company"]["status"] == "not_run"
    fields = {x["field"]: x["status"] for x in c["profile"]["research"]["fields"]}
    assert fields["website"] == "not_found_after_research" and fields["emails"] == "not_searched" and fields["people"] == "not_found_after_research"
    assert c["profile"]["website"] is None and c["profile"]["contacts"] == []
    # without a search connector the statuses say "not searched", never "not found"
    nos = dr.run(db, config.load({"ENVIRONMENT": "test"}), "organisation", ba, META, fetch=lt_site())
    assert {s["stage"]: s["status"] for s in nos["stages"]}["identity"] == "not_run"
    assert {x["field"]: x["status"] for x in nos["profile"]["research"]["fields"]}["website"] == "not_searched"
    # 7. the Dashboard: the opportunity with its company, country/airport, status, relationship position and next action; signals apart
    cl = client_for(db)
    try:
        d = cl.get("/dashboard").json()
        assert [s["key"] for s in d["summaries"]] == ["priority", "deadlines", "researched", "gaps"]
        row = next(r for r in d["priority"] if r["id"] == str(opp_id))
        assert row["organisation"] == "Amber Example Air" and row["countries_named"] == ["Lithuania"] and "KUN" in row["airports"]
        assert row["record_type"] == "commercial" and row["coverage_label"] and row["next_action"]
        assert d["summaries"][2]["count"] == cl.get("/companies", params={"state": "researched", "scope": "all"}).json()["total"] >= 3 and d["summaries"][3]["count"] >= 1
        assert all(r["record_type"] == "market_signal" for r in d["signals"]) and d["detail"]["score_bands"]
        filtered = cl.get("/dashboard?airports=KUN").json()
        assert any(r["id"] == str(opp_id) for r in filtered["priority"]) and "Kaunas" in filtered["scope"]
        assert cl.get("/dashboard?airports=NBO").json()["priority"] == []
        # the research file through the API, and the airport directory search
        rf = cl.get(f"/opportunities/{opp_id}/research-file").json()
        assert rf["summary"]["what"]["source_count"] >= 1 and [s["stage"] for s in rf["stages"]][0] == "identify"
        assert cl.get("/airports?q=kaun").json()["items"][0]["iata"] == "KUN"
        assert cl.get("/airports/EYKA").json()["iata"] == "KUN"
    finally:
        cl.__exit__(None, None, None)


def test_company_duplicates_are_reviewed_and_merges_are_reversible(rdb):  # noqa: F811
    db = rdb
    a = str(db.scalar("org_insert_profile", name="Nemunas Cargo Services UAB", kind="gssa", country="LT", website=None, origin="discovery", airport=None, carrier_type=None))
    b = str(db.scalar("org_insert_profile", name="Nemunas Cargo Services", kind="other", country=None, website="https://www.nemunascargo.example/", origin="supplied", airport=None, carrier_type=None))
    db.one("org_contact_upsert", org=b, kind="email", value="cargo@nemunascargo.example", purpose=None, status="supplied", url=None, note="supplied", evidence=None, session_ref=None)
    assert cmp.flag_duplicates(db, b, META) == 1
    dups = cmp.duplicates(db)
    assert len(dups) == 1 and "common core" in dups[0]["reason"] or "same name" in dups[0]["reason"]
    mid = cmp.merge(db, a, b, "same company: the supplied row lacks the legal suffix", META, duplicate_id=str(dups[0]["id"]))
    assert db.pg.val(f"SELECT merged_into_id FROM organisations WHERE id = '{b}'") == a
    prof = cmp.profile(db, a)
    assert [c["value"] for c in prof["contacts"]] == ["cargo@nemunascargo.example"] and prof["website"] == "https://www.nemunascargo.example/"
    assert "Nemunas Cargo Services" in prof["aliases"] and prof["merges"] and cmp.duplicates(db) == []
    cmp.undo_merge(db, mid, META)
    assert db.pg.val(f"SELECT merged_into_id FROM organisations WHERE id = '{b}'") in (None, "")
    assert cmp.profile(db, b)["contacts"][0]["value"] == "cargo@nemunascargo.example" and cmp.profile(db, a)["contacts"] == []
    assert len(cmp.duplicates(db)) == 1


def test_more_than_six_organisations_are_queued_and_finished_across_runs_never_silently_omitted(rdb):  # noqa: F811
    """Amendment item 2: a per-run limit is acceptable; omitting organisations is not. Nine organisations without a website: run 1 researches
    six and says three are pending; run 2 continues with the three (not the first six again); run 3 has nothing left. Every stage records
    total / attempted / completed / failed / pending, and no stage is 'done' while an organisation is pending."""
    db = rdb
    asked: list[str] = []
    opp_id = lt_opportunity(db, asked)
    names = [f"Queue Example {i} UAB" for i in range(1, 9)]
    for i, n in enumerate(names, start=1):
        oid = str(db.scalar("org_insert_profile", name=n, kind="forwarder", country="LT", website=None, origin="discovery", airport=None, carrier_type=None))
        rid = db.scalar("rdoc_add", opp=opp_id, disc=None, org=None, org_research=None, origin="user_url", url=f"{BASE}/lt-cargo/list-{i}.html", source_doc=None,
                        title=f"List {i}", page_kind="document", found_via="added by a person", status="read", reason=None,
                        body=f"{n} is a freight forwarder at Kaunas Airport (KUN).", sha=None, session_ref="t")
        db.scalar("org_evidence_add", org=oid, supports="identity", source_kind="research_document", rdoc=str(rid), url=f"{BASE}/lt-cargo/list-{i}.html",
                  quote=f"{n} is a freight forwarder at Kaunas Airport (KUN).", note=None, import_id=None, session_ref="t")
    one = dr.run(db, NOAI, "opportunity", opp_id, META, fetch=lt_site(), search_transport=lt_search(asked))
    st = {s["stage"]: s for s in one["stages"]}
    ident = st["identity"]
    assert ident["status"] == "incomplete" and ident["counts"]["total"] == 9 and ident["counts"]["completed"] == 6 and ident["counts"]["pending"] == 3, ident
    assert ident["counts"]["attempted"] == 6 and ident["counts"]["failed"] == 0 and "3 pending" in ident["detail"] and ident["progress"] == "6 completed, 0 failed, 3 pending of 9"
    assert st["people"]["status"] == "incomplete" and st["people"]["counts"]["total"] == 9 and st["people"]["counts"]["pending"] == 3
    assert st["relevance"]["status"] == "done" and st["relevance"]["counts"]["assessed"] == 9           # assessment is cheap: never sliced
    pending_after_1 = sorted(q["organisation"] for q in one["queue"] if q["stage"] == "identity" and q["status"] == "pending")
    done_after_1 = sorted(q["organisation"] for q in one["queue"] if q["stage"] == "identity" and q["status"] == "done")
    assert len(pending_after_1) == 3 and len(done_after_1) == 6 and "Amber Example Air" in done_after_1
    searched_1 = [q for q in asked if "official website" in q]
    assert all(any(n in q for q in searched_1) for n in done_after_1) and not any(any(n in q for q in searched_1) for n in pending_after_1)
    # run 2 continues with the three pending organisations, not with the first six again
    before = len(asked)
    two = dr.run(db, NOAI, "opportunity", opp_id, META, fetch=lt_site(), search_transport=lt_search(asked))
    searched_2 = [q for q in asked[before:] if "official website" in q]
    assert sorted({n for n in pending_after_1 if any(n in q for q in searched_2)}) == pending_after_1
    assert not any(any(n in q for q in searched_2) for n in done_after_1)
    st2 = {s["stage"]: s for s in two["stages"]}
    assert st2["identity"]["counts"]["completed"] >= 9 and all(q["status"] == "done" for q in two["queue"] if q["organisation"] in names + ["Amber Example Air"])
    # an organisation that came to light during run 2 (named on a page read) is queued, said to be pending, and finished by the next run
    late = [q["organisation"] for q in two["queue"] if q["stage"] == "identity" and q["status"] == "pending"]
    assert (st2["identity"]["status"] == "done") == (not late), (st2["identity"], late)
    runs = 0
    while two["resumable"] and runs < 3:
        two = dr.run(db, NOAI, "opportunity", opp_id, META, fetch=lt_site(), search_transport=lt_search(asked))
        runs += 1
    st2 = {s["stage"]: s for s in two["stages"]}
    assert st2["identity"]["status"] == "done" and st2["identity"]["counts"]["pending"] == 0 and st2["identity"]["counts"]["completed"] == st2["identity"]["counts"]["total"]
    assert st2["people"]["status"] == "done" and st2["people"]["counts"]["pending"] == 0 and not two["resumable"]
    assert all(q["status"] == "done" for q in two["queue"] if q["stage"] in ("identity", "people", "relevance")), two["queue"]
    for n in names:                                                                                      # every one carries an honest status
        oid = db.pg.val(f"SELECT id FROM organisations WHERE canonical_name = '{n}'")
        assert {x["field"]: x["status"] for x in cmp.profile(db, oid)["research"]["fields"]}["website"] == "not_found_after_research"
    # run 3: nothing left; the queue is stable and no organisation is searched again
    before = len(asked)
    three = dr.run(db, NOAI, "opportunity", opp_id, META, fetch=lt_site(), search_transport=lt_search(asked))
    assert not [q for q in asked[before:] if "official website" in q] and not three["resumable"]
    assert int(db.pg.val("SELECT count(*) FROM research_stage_items WHERE stage = 'identity'")) == st2["identity"]["counts"]["total"] >= 9


def test_email_attribution_recheck_changed_evidence_and_corrections_that_survive(rdb):  # noqa: F811
    """Amendment items 1 and 6 on PostgreSQL: addresses assigned under the earlier rule are re-checked (confirmed or flagged, evidence kept);
    research never assigns John Brown's address to Jane Smith; a later page stating a different address flags the record for re-checking
    instead of overwriting it; an address a person verified survives further research; the same person record serves Relationships, the
    company page and the opportunity's research file."""
    db = rdb
    nem = str(db.scalar("org_insert_profile", name="Nemunas Cargo Services UAB", kind="gssa", country="LT", website=f"{BASE}/nemunascargo/", origin="discovery", airport=None, carrier_type=None))
    quote_jane = ("Jane Smith is Head of Cargo at Nemunas Cargo Services UAB. For sales enquiries please contact John Brown, Sales Manager at "
                  "Nemunas Cargo Services UAB, at john.brown@nemunascargo.example.")
    quote_ruta = "Ruta Kazlauskiene, Managing Director, Nemunas Cargo Services UAB. E-mail: ruta.kazlauskiene@nemunascargo.example."
    old_note = "published e-mail address beside the person's name on a page read"

    def person(name, role, email=None, status=None, quote=None, url=None):
        pid = str(db.scalar("rel_person_insert", name=name, role=role, org=nem, org_label=None, origin="research", remit=None, remit_countries=None, notes=None))
        if email:
            db.scalar("person_email_set", id=pid, email=email, status=status, url=url)
        if quote:
            db.scalar("rel_evidence_add2", person=pid, supports="relevance", kind="public_page", doc=None, rdoc=None, url=url, quote=quote, note=old_note, session_ref="t")
        return pid
    jane = person("Jane Smith", "Head of Cargo", "john.brown@nemunascargo.example", "published", quote_jane, f"{BASE}/nemunascargo/sales-team.html")    # the defective rule's result
    ruta = person("Ruta Kazlauskiene", "Managing Director", "r.k@nemunascargo.example", "published", None, f"{BASE}/nemunascargo/team.html")          # recorded earlier; the page now states another
    db.run("person_research_status_set", id=ruta, status={"email": {"status": "found", "basis": "explicit_statement"}})
    tomas = person("Tomas Petrauskas", "Head of Cargo Sales", "tomas@verified.example", "verified", None, None)                                  # verified by a person
    rita = person("Rita Example", "Operations Manager", "ruta.kazlauskiene@nemunascargo.example", "published", quote_ruta, f"{BASE}/nemunascargo/team.html")  # wrong person, old rule
    # 1. the re-check of earlier assignments
    out = dr.recheck_published_emails(db, META)
    assert out == {"examined": 2, "confirmed": 0, "flagged": 2, "historical": 0, "verified_kept": 0}, out
    row = db.one("rel_person_get", id=jane)
    assert row["published_email"] == "john.brown@nemunascargo.example" and row["published_email_status"] == "under_review"       # value and evidence kept, flagged
    assert row["research_status"]["email"]["status"] == "candidate" and "John Brown" in row["research_status"]["email"]["detail"]
    assert db.pg.val(f"SELECT count(*) FROM person_evidence WHERE person_id = '{jane}'") == "2"
    assert db.one("rel_person_get", id=rita)["published_email_status"] == "under_review"
    assert dr.recheck_published_emails(db, META)["examined"] == 0                                                            # idempotent
    # 2. research on the company's pages: the attribution rule, changed evidence, a verified address kept
    asked: list[str] = []
    res = dr.run(db, NOAI, "organisation", nem, META, fetch=lt_site(sales_team=True), search_transport=lt_search(asked, sales_team=True))
    people = {p["full_name"]: p for p in res["profile"]["people"]}
    assert "John Brown" in people and people["John Brown"]["published_email"] == "john.brown@nemunascargo.example"
    assert people["Jane Smith"]["published_email_status"] == "under_review" and people["Jane Smith"]["published_email"] == "john.brown@nemunascargo.example"
    assert not any(p["published_email"] == "maria.lopez@examplepr.example" for p in people.values())                              # third-party press contact
    assert db.pg.val(f"SELECT count(*) FROM people WHERE full_name = 'Maria Lopez' AND organisation_id = '{nem}'") == "0"
    r = db.one("rel_person_get", id=ruta)
    assert r["published_email"] == "r.k@nemunascargo.example" and r["published_email_status"] == "under_review"                      # not overwritten: flagged
    assert r["research_status"]["email"]["status"] == "recheck" and r["research_status"]["email"]["value"] == "ruta.kazlauskiene@nemunascargo.example"
    t = db.one("rel_person_get", id=tomas)
    assert t["published_email"] == "tomas@verified.example" and t["published_email_status"] == "verified"                            # a person's verification survives
    assert t["research_status"]["email"]["status"] == "recheck" and "kept" in t["research_status"]["email"]["detail"]
    assert db.pg.val("SELECT count(*) FROM people WHERE full_name = 'Ruta Kazlauskiene' AND merged_into_id IS NULL") == "1"           # no duplicate person
    # 3. a confirmed identity and role survive another research pass; the same record is read everywhere
    rs.confirm_identity(db, tomas, "Confirmed by the account manager from the company's team page", f"{BASE}/nemunascargo/team.html", META)
    dr.run(db, NOAI, "organisation", nem, META, fetch=lt_site(sales_team=True), search_transport=lt_search(asked, sales_team=True))
    t2 = db.one("rel_person_get", id=tomas)
    assert t2["identity_confirmed_at"] and t2["role_title"] == "Head of Cargo Sales" and t2["published_email"] == "tomas@verified.example"
    detail = rs.person_detail(db, tomas)["person"]
    prof_people = {str(p["id"]): p for p in cmp.profile(db, nem)["people"]}
    assert prof_people[tomas]["role_title"] == detail["role_title"] == "Head of Cargo Sales" and prof_people[tomas]["published_email"] == detail["published_email"]
    assert db.pg.val(f"SELECT count(*) FROM people WHERE organisation_id = '{nem}' AND merged_into_id IS NULL") == db.pg.val(f"SELECT count(DISTINCT full_name) FROM people WHERE organisation_id = '{nem}' AND merged_into_id IS NULL")


def test_dashboard_summaries_open_exactly_their_records_and_research_never_raises_priority(rdb):  # noqa: F811
    """Amendment item 5: every summary's link opens the records it counts (with the Dashboard's filters carried over); every opportunity has a
    next action; research completeness is shown apart and never moves an opportunity up — a fuller profile or a published e-mail is not a
    stronger opportunity."""
    from urllib.parse import parse_qsl, urlsplit
    db = rdb
    asked: list[str] = []
    opp_a = lt_opportunity(db, asked)                                              # created first
    cdisc = cd.start(db, NOAI, {"purpose": "companies", "brief": "cargo GSAs at Kaunas", "countries": ["LT"], "airports": ["KUN"],
                                "capability_area": "airline_representation"}, META, fetch=lt_site(), search_transport=lt_search(asked))
    vfh = next(o for o in cdisc["organisations"] if o["canonical_name"] == "Vilnius Freight Hub UAB")["organisation_id"]
    opp_b = cmp.create_opportunity(db, vfh, {"module": "forwarder_sales", "interpretation": "A forwarder at Vilnius that could book cargo on airlines WFC represents.",
                                             "country": "LT", "title": "Vilnius Freight Hub: forwarder sales"}, META)["id"]
    cl = client_for(db)
    try:
        def order():
            return [r["id"] for r in cl.get("/dashboard").json()["priority"]]
        before = order()
        assert before.index(str(opp_b)) < before.index(str(opp_a))                 # both commercial, no relationship: the newer first
        # deep research of the OLDER opportunity: people, a published e-mail, a fuller company profile, research complete or continuing
        dr.run(db, NOAI, "opportunity", opp_a, META, fetch=lt_site(), search_transport=lt_search(asked))
        dr.run(db, NOAI, "opportunity", opp_a, META, fetch=lt_site(), search_transport=lt_search(asked))
        d = cl.get("/dashboard").json()
        row_a = next(r for r in d["priority"] if r["id"] == str(opp_a))
        assert row_a["research"] in ("complete", "incomplete") and row_a["research_label"].startswith("Research")
        assert next(r for r in d["priority"] if r["id"] == str(opp_b))["research"] == "not_started"
        assert db.pg.val("SELECT count(*) FROM people WHERE published_email IS NOT NULL") >= "1"
        assert order() == before                                                   # research completeness never raises priority
        assert all(r["next_action"] for r in d["priority"]) and all(r["next_action"] for r in d["signals"])
        assert "never moves an opportunity up" in d["rule"]
        # every summary's link opens exactly the records it counts — also with a filter carried over from the Dashboard
        for qd in ({}, {"countries": "LT"}, {"airports": "KUN"}):
            dd = cl.get("/dashboard", params=qd).json()
            for sm in dd["summaries"]:
                u = urlsplit(sm["link"])
                params = dict(parse_qsl(u.query))
                if u.path == "/opportunities":
                    got = cl.get("/records", params={**params, "limit": 200}).json()
                    assert got["total"] == sm["count"], (sm["key"], qd, got["total"], sm["count"])
                    for k, v in qd.items():
                        assert params.get(k) == v, (sm["key"], sm["link"])
                else:
                    assert u.path == "/companies" and cl.get("/companies", params={**params, "limit": 200}).json()["total"] == sm["count"], sm
        gaps = cl.get("/records", params={"types": "tender,commercial", "live": "true", "needs": "attention"}).json()["items"]
        assert {r["id"] for r in gaps} >= {str(opp_b)}                              # no relationship recorded
    finally:
        cl.__exit__(None, None, None)


def test_company_correction_survives_research_and_contradicting_pages_prompt_a_recheck(rdb):  # noqa: F811
    """Amendment item 6: discovery and deep research update the same company; a person's correction survives further research; a page that
    presents a different official site flags the record for re-checking instead of overwriting it; the company, its people and the
    opportunity's research file read the same record."""
    db = rdb
    asked: list[str] = []
    opp_id = lt_opportunity(db, asked)
    disc = cd.start(db, NOAI, {"purpose": "companies", "brief": "cargo GSAs at Kaunas", "countries": ["LT"], "airports": ["KUN"],
                               "capability_area": "airline_representation"}, META, fetch=lt_site(), search_transport=lt_search(asked))
    nem = next(o for o in disc["organisations"] if o["canonical_name"] == "Nemunas Cargo Services UAB")["organisation_id"]
    # a person corrects the official site before any deep research (the team knows the group's own domain)
    cmp.edit(db, nem, {"website": "https://www.nemunas-group.example/", "basis": "Confirmed by phone with the company's office"}, META)
    # a colleague adds the company's other home page to the opportunity: it names the company on a matching site
    from app.services import relationship_research as rr
    rr.add_user_source(db, opp_id, url=f"{BASE}/nemunascargo/index.html", title=None, text=None, meta=META)
    dr.run(db, NOAI, "opportunity", opp_id, META, fetch=lt_site(), search_transport=lt_search(asked))
    dr.run(db, NOAI, "organisation", nem, META, fetch=lt_site(), search_transport=lt_search(asked))
    prof = cmp.profile(db, nem)
    assert prof["website"] == "https://www.nemunas-group.example/" and prof["website_basis"].startswith("corrected by a person")
    # the research found pages naming the company on another site: that is changed evidence, flagged — never written over the correction
    assert db.pg.val(f"SELECT count(*) FROM research_documents WHERE url = '{BASE}/nemunascargo/index.html' AND status = 'read'") >= "1"
    f = {x["field"]: x for x in prof["research"]["fields"]}
    assert f["website"]["status"] == "recheck" and "nemunas-group.example" in f["website"]["detail"], f["website"]
    assert any("changed evidence" in (e.get("note") or "") for e in prof["evidence"])
    # one canonical company: discovery, opportunity research and company research all point at it
    assert db.pg.val("SELECT count(*) FROM organisations WHERE canonical_name ILIKE 'Nemunas Cargo Services%' AND merged_into_id IS NULL") == "1"
    # a person decides: the correction is re-confirmed and the flag clears
    cmp.edit(db, nem, {"website": "https://www.nemunas-group.example/", "basis": "Re-checked: the group site is the official one"}, META)
    assert {x["field"]: x["status"] for x in cmp.profile(db, nem)["research"]["fields"]}["website"] == "found"
    # the same person record in Relationships, on the company page and in the opportunity's research file
    rf = dr.research_file(db, opp_id)
    cl = client_for(db)
    try:
        for p in rf["summary"]["people"]:
            rel_view = cl.get(f"/people/{p['id']}").json()["person"]
            assert (rel_view["full_name"], rel_view["role_title"], rel_view["published_email"]) == (p["full_name"], p["role_title"], p["published_email"])
            if rel_view.get("organisation_id"):
                on_company = {str(x["id"]): x for x in cmp.profile(db, rel_view["organisation_id"])["people"]}
                assert on_company[p["id"]]["role_title"] == p["role_title"] and on_company[p["id"]]["published_email"] == p["published_email"]
        company_view = cl.get(f"/companies/{nem}").json()
        file_view = next(c for c in rf["companies"] if c["id"] == nem)
        assert (company_view["website"], company_view["contact_url"]) == (file_view["website"], file_view["contact_url"])
    finally:
        cl.__exit__(None, None, None)


def test_withdrawn_and_conflicting_contact_details_are_historical_or_reviewed_never_current_routes(rdb):  # noqa: F811
    """4.8.0 item 2 on PostgreSQL. A page says "Do not use tomas.petrauskas@… — this address is no longer valid. Please write to tp@… instead"
    while another page still lists the old address: the old one is historical evidence (conflict shown), the replacement is current. A company
    mailbox one page lists and another says is no longer monitored goes to review with the conflict recorded. Nothing is claimed deliverable."""
    db = rdb
    asked: list[str] = []
    disc = cd.start(db, NOAI, {"purpose": "companies", "brief": "cargo GSAs at Kaunas", "countries": ["LT"], "airports": ["KUN"],
                               "capability_area": "airline_representation"}, META, fetch=lt_site(), search_transport=lt_search(asked))
    nem = next(o for o in disc["organisations"] if o["canonical_name"] == "Nemunas Cargo Services UAB")["organisation_id"]
    for _ in range(3):
        res = dr.run(db, NOAI, "organisation", nem, META, fetch=lt_site(sales_team=True, notices=True), search_transport=lt_search(asked, sales_team=True, notices=True))
        if not res["resumable"]:
            break
    assert db.pg.val(f"SELECT count(*) FROM research_documents WHERE url = '{BASE}/nemunascargo/notices.html' AND status = 'read'") >= "1"
    tomas = db.one("rel_person_get", id=db.pg.val("SELECT id FROM people WHERE full_name = 'Tomas Petrauskas' AND merged_into_id IS NULL"))
    assert tomas["published_email"] == "tp@nemunascargo.example" and tomas["published_email_status"] == "published"          # the replacement
    assert "tomas.petrauskas@nemunascargo.example" in tomas["research_status"]["email_history"]
    notes = [r[0] for r in db.pg.rows(f"SELECT note FROM person_evidence WHERE person_id = '{tomas['id']}'")]
    assert any(n.startswith("historical e-mail address tomas.petrauskas@nemunascargo.example") and "Do not use" in n for n in notes), notes
    prof = cmp.profile(db, nem)
    ops = next(c for c in prof["contacts"] if c["value"] == "ops@nemunascargo.example")
    assert ops["status"] == "under_review" and "conflict" in (ops["source_note"] or "") and ops["status_label"].startswith("Sources conflict")
    assert all("deliverability not verified" in c["status_label"] for c in prof["contacts"] if c["status"] == "published")
    # the research file never offers a historical or conflicting address as a route
    f = {x["field"]: x["status"] for x in prof["research"]["fields"]}
    assert f["emails"] == "found"                                                        # sales@ and cargo@ remain current
    # a person whose only recorded address a page now withdraws: historical, not a current route; a verified one is kept and flagged
    rid = db.pg.val(f"SELECT id FROM research_documents WHERE url = '{BASE}/nemunascargo/notices.html' LIMIT 1")
    quote = "Tomas Petrauskas, Head of Cargo Sales, Nemunas Cargo Services UAB. Do not use tomas.petrauskas@nemunascargo.example — this address is no longer valid."

    def person(name, email, status):
        pid = str(db.scalar("rel_person_insert", name=name, role="Head of Cargo Sales", org=nem, org_label=None, origin="research", remit=None, remit_countries=None, notes=None))
        db.scalar("person_email_set", id=pid, email=email, status=status, url=f"{BASE}/nemunascargo/notices.html")
        db.scalar("rel_evidence_add2", person=pid, supports="relevance", kind="research_document", doc=None, rdoc=rid, url=f"{BASE}/nemunascargo/notices.html",
                  quote=quote.replace("Tomas Petrauskas", name), note="published e-mail address: stated in the same sentence as the person, nobody else between", session_ref="t")
        return pid
    a = person("Tomas Example", "tomas.petrauskas@nemunascargo.example", "published")      # assigned before 4.8.0 from a withdrawn passage
    out = dr.recheck_published_emails(db, META)
    assert out["examined"] >= 1
    ra = db.one("rel_person_get", id=a)
    assert ra["published_email_status"] in ("historical", "under_review") and ra["published_email"] == "tomas.petrauskas@nemunascargo.example"
    assert any("re-check 4.8.0" in (r[0] or "") for r in db.pg.rows(f"SELECT note FROM person_evidence WHERE person_id = '{a}'"))
    assert db.pg.val("SELECT count(*) FROM audit_events WHERE event_type = 'person_email_recheck'") >= "1"
    assert dr.recheck_published_emails(db, META)["examined"] == 0                         # idempotent per version


def test_failures_are_never_reported_as_plain_done_and_retry_handles_only_the_failed_organisations(rdb):  # noqa: F811
    """4.8.0 item 3: the official site of one organisation cannot be read. The stage finishes as "complete with unresolved failures" (never a
    plain "done"); research file, company page and Dashboard show the same completed / failed / pending counts; Continue does not touch the
    failure; the explicit retry re-queues only the failed organisation, reads the page again and repeats no completed work."""
    db = rdb
    asked: list[str] = []
    opp_id = lt_opportunity(db, asked)
    broken = lt_site()
    broken.pages[f"{BASE}/nemunascargo/index.html"] = ConnectionResetError("connection reset by peer")
    broken.pages[f"{BASE}/nemunascargo/"] = ConnectionResetError("connection reset by peer")
    out = None
    for _ in range(4):
        out = dr.run(db, NOAI, "opportunity", opp_id, META, fetch=broken, search_transport=lt_search(asked))
        if not out["resumable"]:
            break
    st = {s["stage"]: s for s in out["stages"]}
    ident = st["identity"]
    assert ident["status"] == "done_with_failures" and ident["status_label"].startswith("Complete with unresolved failures"), (ident["status"], ident["detail"])
    assert ident["counts"]["failed"] == 1 and ident["counts"]["pending"] == 0 and "1 failed" in ident["progress"]
    failed_q = [q for q in out["queue"] if q["status"] == "failed"]
    assert [(q["stage"], q["organisation"]) for q in failed_q] == [("identity", "Nemunas Cargo Services UAB")]
    nem = db.pg.val("SELECT id FROM organisations WHERE canonical_name = 'Nemunas Cargo Services UAB' AND merged_into_id IS NULL")
    f = {x["field"]: x for x in cmp.profile(db, nem)["research"]["fields"]}
    assert f["website"]["status"] == "inaccessible" and "could not be read" in f["website"]["detail"]       # never "not found after research"
    assert out["progress"]["state"] == "complete_with_failures" and out["retryable"] and not out["resumable"]
    rf = out["research_file"]
    assert rf["progress"]["failed"] == out["progress"]["failed"] >= 1 and any("failed and are unresolved" in u for u in rf["summary"]["uncertain"])
    assert rf["summary"]["next_action"] == "Retry the failed organisations" or rf["opportunity"]["next_action"]
    cl = client_for(db)
    try:
        row = next(r for r in cl.get("/dashboard").json()["priority"] if r["id"] == str(opp_id))
        assert row["research"] == "complete_with_failures" and row["research_tally"] == out["progress"]["tally"]
        assert row["next_action"].startswith("Retry") or not row["next_action_is_recommendation"]
        gaps = cl.get("/records", params={"types": "tender,commercial", "live": "true", "needs": "attention"}).json()["items"]
        assert str(opp_id) in {r["id"] for r in gaps}
        # Continue does not retry the failure
        before_attempts = {(q["stage"], q["organisation"]): q["attempts"] for q in out["queue"]}
        cont = dr.run(db, NOAI, "opportunity", opp_id, META, fetch=broken, search_transport=lt_search(asked))
        assert {s["stage"]: s["status"] for s in cont["stages"]}["identity"] == "done_with_failures"
        assert {(q["stage"], q["organisation"]): q["attempts"] for q in cont["queue"]} == before_attempts
        # the explicit retry, with the site reachable again: only the failed organisation is attempted; nothing completed is repeated
        docs_before = {r[0] for r in db.pg.rows(f"SELECT url FROM research_documents WHERE opportunity_id = '{opp_id}'")}
        cl.app.state.fetch, cl.app.state.search_transport, cl.app.state.settings = lt_site(), lt_search(asked), NOAI
        res = cl.post(f"/opportunities/{opp_id}/deep-research/retry-failed")
        assert res.status_code == 200, res.text
        r = res.json()
        assert r["retried"]["organisations"] == 1 and "identity" in r["retried"]["stages"] and r["retried"]["pages"] >= 1
        after = {(q["stage"], q["organisation"]): q for q in r["queue"]}
        changed = {k for k, q in after.items() if k in before_attempts and q["attempts"] != before_attempts[k]}
        assert changed == {("identity", "Nemunas Cargo Services UAB")}, changed                 # only the failed organisation was attempted again
        assert after[("identity", "Nemunas Cargo Services UAB")]["status"] == "done"
        assert {s["stage"]: s["status"] for s in r["stages"]}["identity"] in ("done", "incomplete")       # incomplete only if new organisations came to light
        urls = [x[0] for x in db.pg.rows(f"SELECT url FROM research_documents WHERE opportunity_id = '{opp_id}'")]
        assert len(urls) == len(set(urls)) and docs_before <= set(urls)                           # no page recorded twice
        assert cmp.profile(db, nem)["website"] == f"{BASE}/nemunascargo/"
        # once resolved there is nothing to retry
        while r["resumable"]:
            r = dr.run(db, NOAI, "opportunity", opp_id, META, fetch=lt_site(), search_transport=lt_search(asked))
        assert r["progress"]["failed"] == 0 and r["progress"]["state"] == "complete" and not r["retryable"]
        assert cl.post(f"/opportunities/{opp_id}/deep-research/retry-failed").status_code == 409
    finally:
        cl.__exit__(None, None, None)


def test_a_page_added_after_research_is_complete_is_pending_work_and_continue_reads_it(rdb):  # noqa: F811
    """Found in the 4.8.0 smoke run: pages a person added after the research was complete were never read, while the state said
    "complete". They are pending work now: the state says so, Continue reads them, and the person's current address (the replacement of a
    withdrawn one) is attributed from them."""
    from app.services import relationship_research as rr
    db = rdb
    asked: list[str] = []
    opp_id = lt_opportunity(db, asked)
    out = dr.run(db, NOAI, "opportunity", opp_id, META, fetch=lt_site(), search_transport=lt_search(asked))
    while out["resumable"]:
        out = dr.run(db, NOAI, "opportunity", opp_id, META, fetch=lt_site(), search_transport=lt_search(asked))
    assert out["progress"]["state"] == "complete"
    for page in ("sales-team.html", "notices.html"):
        rr.add_user_source(db, opp_id, url=f"{BASE}/nemunascargo/{page}", title=None, text=None, meta=META)
    pr = dr.progress(db, "opportunity", opp_id)
    assert pr["state"] == "incomplete" and pr["pages_queued"] == 2 and "2 page(s) queued to read" in pr["tally"]
    cl = client_for(db)
    try:
        row = next(r for r in cl.get("/dashboard").json()["priority"] if r["id"] == str(opp_id))
        assert row["research"] == "incomplete" and "queued to read" in row["research_tally"]
    finally:
        cl.__exit__(None, None, None)
    out = dr.run(db, NOAI, "opportunity", opp_id, META, fetch=lt_site(sales_team=True, notices=True), search_transport=lt_search(asked))
    assert db.pg.val(f"SELECT count(*) FROM research_documents WHERE opportunity_id = '{opp_id}' AND status = 'queued'") == "0"
    tomas = db.one("rel_person_get", id=db.pg.val("SELECT id FROM people WHERE full_name = 'Tomas Petrauskas' AND merged_into_id IS NULL"))
    assert tomas["published_email"] == "tp@nemunascargo.example" and "tomas.petrauskas@nemunascargo.example" in tomas["research_status"]["email_history"]
    assert out["progress"]["pages_queued"] == 0


def test_two_people_of_the_same_name_at_different_organisations(rdb):  # noqa: F811
    """4.8.0 item 1: Jane Smith at Nemunas Cargo Services and Jane Smith at Amber Example Air. A passage that names only "Jane Smith" assigns
    the address to neither; a passage that also names the organisation assigns it to that organisation's Jane Smith only."""
    from app.services import relationship_research as rr
    db = rdb
    asked: list[str] = []
    opp_id = lt_opportunity(db, asked)
    out = dr.run(db, NOAI, "opportunity", opp_id, META, fetch=lt_site(), search_transport=lt_search(asked))
    nem = db.pg.val("SELECT id FROM organisations WHERE canonical_name = 'Nemunas Cargo Services UAB' AND merged_into_id IS NULL")
    amber = db.pg.val("SELECT id FROM organisations WHERE canonical_name = 'Amber Example Air' AND merged_into_id IS NULL")
    assert nem and amber and {str(o["id"]) for o in out["research_file"]["companies"]} >= {nem, amber}
    j_nem = str(db.scalar("rel_person_insert", name="Jane Smith", role="Head of Cargo", org=nem, org_label=None, origin="research", remit=None, remit_countries=None, notes=None))
    j_amb = str(db.scalar("rel_person_insert", name="Jane Smith", role="Cargo Manager", org=amber, org_label=None, origin="research", remit=None, remit_countries=None, notes=None))
    rr.add_user_source(db, opp_id, url=None, title="Note 1", text="Jane Smith, Head of Cargo: write to jsmith@nemunascargo.example for bookings.", meta=META)
    dr.run(db, NOAI, "opportunity", opp_id, META, fetch=lt_site(), search_transport=lt_search(asked))
    for pid in (j_nem, j_amb):
        r = db.one("rel_person_get", id=pid)
        assert r["published_email"] is None and r["research_status"]["email"]["status"] == "candidate", r["research_status"]
        assert "another person named Jane Smith" in r["research_status"]["email"]["detail"]
    rr.add_user_source(db, opp_id, url=None, title="Note 2",
                       text="Jane Smith, Head of Cargo at Nemunas Cargo Services UAB, can be reached at jsmith@nemunascargo.example.", meta=META)
    dr.run(db, NOAI, "opportunity", opp_id, META, fetch=lt_site(), search_transport=lt_search(asked))
    assert db.one("rel_person_get", id=j_nem)["published_email"] == "jsmith@nemunascargo.example"
    assert db.one("rel_person_get", id=j_amb)["published_email"] is None


def test_a_third_party_press_contact_is_kept_as_an_external_contact_never_a_commercial_one(rdb):  # noqa: F811
    """4.9.0 item 1. The company's sales-team page ends "Press contact: Maria Lopez, Example PR Agency, maria.lopez@examplepr.example".
    She is recorded as a press / media contact of Example PR Agency — kept, with her actual role — but never counted in the opportunity's
    relationship coverage, never listed among its commercial people, never ranked. A re-check fixes candidates recorded before 4.9.0; a
    person's own correction survives later research."""
    from app.services import relationship_research as rr
    db = rdb
    asked: list[str] = []
    opp_id = lt_opportunity(db, asked)
    rr.add_user_source(db, opp_id, url=f"{BASE}/nemunascargo/sales-team.html", title=None, text=None, meta=META)
    out = dr.run(db, NOAI, "opportunity", opp_id, META, fetch=lt_site(sales_team=True), search_transport=lt_search(asked, sales_team=True))
    maria_id = db.pg.val("SELECT id FROM people WHERE full_name = 'Maria Lopez' AND merged_into_id IS NULL")
    assert maria_id, "the press contact is still recorded (kept, with her role)"
    maria = db.one("rel_person_get", id=maria_id)
    assert maria["involvement"] == "press_contact" and "press" in maria["involvement_basis"]
    assert db.pg.val(f"SELECT status FROM opportunity_people WHERE person_id = '{maria_id}' AND opportunity_id = '{opp_id}'") == "external_contact"
    rf = out["research_file"]
    assert "Maria Lopez" not in {p["full_name"] for p in rf["summary"]["people"]}
    ext = {p["full_name"]: p for p in rf["summary"]["external_contacts"]}
    assert ext["Maria Lopez"]["involvement_label"] == "Press / media contact"
    assert not any("Maria Lopez" in u for u in rf["summary"]["uncertain"])                         # not a gap to chase either
    commercial = {p["full_name"]: p["involvement"] for p in rf["summary"]["people"]}
    assert commercial.get("John Brown") == "employee" and commercial.get("Tomas Petrauskas") == "employee"
    # coverage never counts her: with only her linked, the opportunity would have no relationship coverage at all
    db.pg.run(f"UPDATE opportunity_people SET status = 'not_relevant' WHERE opportunity_id = '{opp_id}' AND person_id <> '{maria_id}'")
    assert db.pg.val(f"SELECT level FROM opportunity_relationship_coverage WHERE opportunity_id = '{opp_id}'") == "none"
    from app.services import relationship_service as rs2
    assert rs2.opportunity_relationships(db, opp_id)["coverage"] == "none"
    # 4.8.0 data: a press contact recorded as a plain candidate is fixed by the one-time re-check (evidence note, audit, idempotent)
    old = str(db.scalar("rel_person_insert", name="Laura Kim", role="Account Director", org=None, org_label="Bright Comms Ltd", origin="research",
                        remit=None, remit_countries=None, notes=None))
    rid = db.pg.val(f"SELECT id FROM research_documents WHERE opportunity_id = '{opp_id}' LIMIT 1")
    db.scalar("rel_evidence_add2", person=old, supports="relevance", kind="research_document", doc=None, rdoc=rid, url=None,
              quote="For media enquiries contact Laura Kim, Account Director, Bright Comms Ltd.", note="found by reading", session_ref="t")
    db.run("rel_link_upsert", opp=opp_id, person=old, role="named_in_source", basis="named in the source", status="candidate")
    db.pg.run(f"UPDATE opportunity_people SET status = 'candidate' WHERE person_id = '{old}'")
    rc = dr.recheck_involvement(db, META)
    assert rc["examined"] >= 1 and rc["changed"] >= 1 and rc["links_moved"] >= 1
    assert db.one("rel_person_get", id=old)["involvement"] == "press_contact"
    assert db.pg.val(f"SELECT status FROM opportunity_people WHERE person_id = '{old}'") == "external_contact"
    assert any("involvement re-check 4.9.0" in (r[0] or "") for r in db.pg.rows(f"SELECT note FROM person_evidence WHERE person_id = '{old}'"))
    assert db.pg.val("SELECT count(*) FROM audit_events WHERE event_type = 'person_involvement_recheck'") >= "1"
    assert dr.recheck_involvement(db, META)["examined"] == 0
    # a person's correction survives later research
    cl = client_for(db)
    try:
        r = cl.post(f"/people/{maria_id}/involvement", json={"involvement": "appointed_representative",
                                                             "basis": "Confirmed by phone: Example PR Agency is the airline's appointed sales agent in Lithuania"})
        assert r.status_code == 200, r.text
    finally:
        cl.__exit__(None, None, None)
    dr.run(db, NOAI, "opportunity", opp_id, META, fetch=lt_site(sales_team=True), search_transport=lt_search(asked, sales_team=True))
    dr.recheck_involvement(db, META)
    m2 = db.one("rel_person_get", id=maria_id)
    assert m2["involvement"] == "appointed_representative" and m2["involvement_set_by"] == "person"
