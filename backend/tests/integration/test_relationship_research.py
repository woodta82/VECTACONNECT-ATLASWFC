"""Opportunity-led relationship research on PostgreSQL (instruction of 28 Oct 2026, second continuation, items 1–5).

SIMULATED: every web page is synthetic (tests.integration.test_review3_regressions.Web), the search provider is a scripted
stand-in, and the AI people reader uses a scripted transport. No real site, search provider or AI provider is used here.
"""
from __future__ import annotations

import json

import pytest

from app import config
from app.connectors.search import SearchResult
from app.domain import retrieval
from app.services import discovery as dsc
from app.services import relationship_research as rr
from app.services import relationship_service as rs
from tests.integration.sa import sadb  # noqa: F401
from tests.integration.test_relationship_journey import META, run, site
from tests.integration.test_review3_regressions import BASE, SETTINGS, Web, _page, _source, rdb  # noqa: F401

NO_AI = config.load({"ENVIRONMENT": "test"})
SITE = "https://www.example-air.example"


def _opp(db) -> str:
    _source(db, "Example Air procurement and news", "listing", BASE + "/n/", country_coverage=["KE", "UG"], max_items=10)
    run(db, dsc.SearchSpec("country", ["KE"], [], []), site())
    return db.pg.val("SELECT o.id FROM opportunities o JOIN signals s ON s.id = o.signal_id WHERE s.tender_ref = 'EXA-GSSA-2026-301' "
                     "AND o.merged_into_id IS NULL")


def _org(db, opp: str) -> str:
    return db.pg.val(f"SELECT coalesce(airline_id, organisation_id) FROM opportunities WHERE id = '{opp}'")


def _html(title: str, body_html: str) -> bytes:
    return f"<!doctype html><html lang='en'><head><title>{title}</title></head><body><main><h1>{title}</h1>{body_html}</main></body></html>".encode()


def company_site(*, broken_news: bool = False) -> Web:
    pages: dict = {
        f"{SITE}/": _html("Example Air", '<p>Welcome to Example Air.</p><nav><a href="/about/leadership">Our leadership</a> '
                                         '<a href="/media-centre">Media centre</a> <a href="/careers">Careers</a> <a href="/about/team">Our team</a> '
                                         '<a href="https://other.example/x">Partner site</a></nav>'),
        f"{SITE}/about/leadership": _html("Leadership", "<ul><li>Maria Lopez – Head of Cargo</li><li>Peter Otieno – Country Manager Kenya</li></ul>"),
        f"{SITE}/media-centre": _html("Media centre", '<ul><li><a href="/media-centre/2026/example-air-appoints-cargo-sales-director">'
                                                      'Example Air appoints new Cargo Sales Director</a></li>'
                                                      '<li><a href="/media-centre/2026/blue-ridge-partnership">Partnership with Blue Ridge '
                                                      'Handling expands Nairobi handling</a></li></ul>'),
        f"{SITE}/media-centre/2026/example-air-appoints-cargo-sales-director": _html(
            "Example Air appoints new Cargo Sales Director",
            "<p>Example Air has appointed Daniel Kiprop as Cargo Sales Director Africa, succeeding Ruth Achola.</p>"),
        f"{SITE}/media-centre/2026/blue-ridge-partnership": (
            RuntimeError("connection reset") if broken_news else _html(
                "Partnership with Blue Ridge Handling",
                '<p>"We are proud to support Example Air in Nairobi," said John Lee, Chief Executive Officer of Blue Ridge Handling, '
                "Example Air's ground handling partner.</p>")),
        f"{SITE}/about/team": _html("Team", "<p>Sam Kirui – Cargo Sales Manager</p>"),
        f"{SITE}/robots.txt": (b"User-agent: *\nDisallow: /about/team\n", "text/plain"),
    }
    return Web(pages)


def _person(db, name: str) -> list[tuple]:
    return db.pg.rows(f"SELECT id, organisation_id, organisation_label, role_title FROM people WHERE full_name = '{name}' AND merged_into_id IS NULL")


def test_research_follows_the_organisations_own_links_binds_roles_and_reports_coverage(rdb):  # noqa: F811
    db = rdb
    opp = _opp(db)
    org = _org(db, opp)
    rs.set_research_pages(db, org, website=SITE + "/", newsroom=None, leadership=None, meta=META)
    web = company_site(broken_news=True)
    out = rs.research(db, NO_AI, opp, META, fetch=web)
    # links on the homepage were followed (leadership page, newsroom, news items); no fixed address was guessed
    origins = {d["url"]: (d["origin"], d["status"]) for d in out["documents"] if d["url"]}
    assert origins[f"{SITE}/about/leadership"] == ("followed_link", "read")
    assert origins[f"{SITE}/media-centre"] == ("followed_link", "read")
    assert not any(o == "guessed_page" for o, _s in origins.values())
    assert f"{SITE}/careers" not in web.fetched and "https://other.example/x" not in web.fetched     # not relevant; other sites
    assert f"{SITE}/about/team" not in web.fetched                                                 # robots.txt disallows it
    team = next(d for d in out["documents"] if d["url"] == f"{SITE}/about/team")
    assert team["status"] == "skipped" and "robots.txt" in team["status_reason"]
    # people and their bindings
    found = {f["name"]: f for f in out["found"]}
    assert (found["Maria Lopez"]["role"], found["Maria Lopez"]["organisation"], found["Maria Lopez"]["affiliation"]) == (
        "Head of Cargo", "Example Air", "employee")
    assert (found["Daniel Kiprop"]["role"], found["Daniel Kiprop"]["role_status"]) == ("Cargo Sales Director Africa", "current")
    assert found["Ruth Achola"]["role_status"] == "former"
    # the failed news item makes research INCOMPLETE, never "no people found"
    assert out["outcome"] == "incomplete"
    assert out["coverage"]["failed"] == 1 and any("could not be fetched" in r for r in out["coverage"]["remaining"])
    assert any("not a complete search" in n for n in out["coverage"]["not_searched"])
    # a former holder is recorded with the evidence but not linked to the opportunity as a current contact
    ruth = _person(db, "Ruth Achola")[0][0]
    assert db.pg.val(f"SELECT count(*) FROM opportunity_people WHERE person_id = '{ruth}'") == "0"
    assert db.pg.val(f"SELECT role_status FROM person_roles WHERE person_id = '{ruth}'") == "former"
    # continue: the page is back; the run completes and the partner is recorded as a partner, not an employee
    out2 = rs.research(db, NO_AI, opp, META, fetch=company_site(), mode="continue")
    assert out2["outcome"] == "people_found", out2["coverage"]
    lee = next(f for f in out2["found"] if f["name"] == "John Lee")
    assert (lee["organisation"], lee["affiliation"]) == ("Blue Ridge Handling", "partner")
    lee_id = _person(db, "John Lee")[0][0]
    assert db.pg.val(f"SELECT organisation_label FROM people WHERE id = '{lee_id}'") == "Blue Ridge Handling"
    ev = rs.person_detail(db, lee_id)
    assert {e["supports"] for e in ev["evidence"]} >= {"relevance", "role", "organisation"}
    assert ev["roles"][0]["affiliation"] == "partner" and "Blue Ridge Handling" in ev["roles"][0]["quote"]
    # running again adds nothing twice
    before = db.pg.val("SELECT count(*) FROM person_evidence")
    rs.research(db, NO_AI, opp, META, fetch=company_site())
    assert db.pg.val("SELECT count(*) FROM person_evidence") == before
    assert len(_person(db, "Maria Lopez")) == 1


def test_guessed_addresses_only_when_a_site_offers_no_links_and_they_are_labelled(rdb):  # noqa: F811
    db = rdb
    opp = _opp(db)
    rs.set_research_pages(db, _org(db, opp), website=SITE + "/", newsroom=None, leadership=None, meta=META)
    web = Web({f"{SITE}/": _html("Example Air", "<p>Welcome.</p>"),
               f"{SITE}/leadership": _html("Leadership", "<p>Peter Otieno, Country Manager Kenya, leads our Nairobi office.</p>")})
    out = rs.research(db, NO_AI, opp, META, fetch=web)
    docs = {d["url"]: d for d in out["documents"] if d["url"]}
    assert docs[f"{SITE}/leadership"]["origin"] == "guessed_page" and "guessed address" in docs[f"{SITE}/leadership"]["found_via"]
    assert docs[f"{SITE}/about"]["status"] == "skipped" and docs[f"{SITE}/about"]["status_reason"] == "guessed address not found"
    assert out["outcome"] == "people_found"          # a guessed address that does not exist is not a failure


def test_reviewer_added_url_and_document_are_read_with_their_own_evidence(rdb):  # noqa: F811
    db = rdb
    opp = _opp(db)
    url = "https://news.example/aviation/example-air-cargo-team"
    rs.add_research_source(db, opp, url=url, title=None, text=None, meta=META)
    doc = ("Market report: East Africa air cargo 2026.\n\nKenya Civil Aviation Authority figures show growth. "
           "Grace Achieng, Head of Cargo Sales at Example Air, expects capacity to double.")
    rid = rs.add_research_source(db, opp, url=None, title="Market report (PDF)", text=doc, meta=META)
    with pytest.raises(rs.RelationshipRejected) as dup:
        rs.add_research_source(db, opp, url=None, title="same", text=doc, meta=META)
    assert dup.value.status == 409
    web = Web({url: _html("Example Air cargo team", "<p>Example Air's Head of Cargo Maria Lopez said the team will grow.</p>")})
    out = rs.research(db, NO_AI, opp, META, fetch=web)
    assert "reviewer_sources" in out["methods"]
    g = next(f for f in out["found"] if f["name"] == "Grace Achieng")
    assert (g["role"], g["organisation"]) == ("Head of Cargo Sales", "Example Air")
    gid = _person(db, "Grace Achieng")[0][0]
    ev = rs.person_detail(db, gid)["evidence"]
    assert any(e["source_kind"] == "research_document" and str(e["research_document_id"]) == rid for e in ev)
    assert any(f["name"] == "Maria Lopez" and f["source"] == url for f in out["found"])


def test_without_a_search_connector_nothing_is_searched_and_the_searches_are_offered_as_links(rdb):  # noqa: F811
    db = rdb
    opp = _opp(db)
    out = rs.research(db, NO_AI, opp, META)
    assert out["web_searches"] and all(s["status"] == "not_run" for s in out["web_searches"])
    assert all(s["link"].startswith("https://www.google.com/search?q=") for s in out["web_searches"])
    assert any(u["method"] == "web_search" and "no authorised search connector" in u["reason"] for u in out["unavailable"])
    assert any("web search(es) not run" in n for n in out["coverage"]["not_searched"])
    assert "web_search" not in out["methods"]


def test_with_a_search_connector_results_are_fetched_and_read(rdb):  # noqa: F811
    db = rdb
    opp = _opp(db)
    settings = config.load({"ENVIRONMENT": "test", "SEARCH_PROVIDER": "brave", "SEARCH_API_KEY": "search-key-not-real",
                            "SEARCH_MAX_QUERIES": "3"})
    asked: list[str] = []

    def search(_settings, query, country, count):
        asked.append(query)
        return [SearchResult("https://press.example/example-air-appoints", "Example Air appoints", "")] if len(asked) == 1 else []
    web = Web({"https://press.example/example-air-appoints": _html(
        "Example Air appoints", "<p>Example Air has appointed Samuel Mwangi as Country Manager Kenya.</p>")})
    out = rs.research(db, settings, opp, META, fetch=web, search_transport=search)
    assert len(asked) == 3 and [s["status"] for s in out["web_searches"]] == ["run", "run", "run"]
    s = next(f for f in out["found"] if f["name"] == "Samuel Mwangi")
    assert (s["role"], s["organisation"]) == ("Country Manager Kenya", "Example Air")
    assert "web_search" in out["methods"]
    doc = next(d for d in out["documents"] if d["url"] == "https://press.example/example-air-appoints")
    assert doc["origin"] == "search_result" and doc["found_via"].startswith("search: ")


def test_long_documents_are_read_in_sections_under_budget_and_resume(rdb):  # noqa: F811
    db = rdb
    opp = _opp(db)
    paras = [f"Section {i}. " + ("Cargo volumes grew in Nairobi and Mombasa. " * 130) for i in range(9)]
    paras[7] += "Lucy Wairimu, Cargo Development Manager at Example Air, presented the plan."
    rs.add_research_source(db, opp, url=None, title="Annual report", text="\n\n".join(paras), meta=META)
    calls: list[str] = []

    def transport(_settings, _system, user):
        calls.append(user)
        doc = user.split("<document>\n", 1)[-1]
        people = []
        if "Lucy Wairimu" in doc:
            people.append({"name": "Lucy Wairimu", "role": "Cargo Development Manager", "organisation": "Example Air", "role_status": "current",
                           "quote": "Lucy Wairimu, Cargo Development Manager at Example Air, presented the plan."})
        return json.dumps({"people": people}), 1000, 50
    first = rs.research(db, SETTINGS, opp, META, transport=transport)
    annual = next(d for d in first["documents"] if d["title"] == "Annual report")
    assert annual["sections_total"] >= 9 and annual["sections_read"] == annual["sections_total"]      # the rules read everything
    assert annual["ai_status"] == "partial" and annual["ai_sections_read"] < annual["sections_total"]
    assert first["outcome"] == "incomplete" and any("still to be read by the configured AI extractor" in r for r in first["coverage"]["remaining"])
    assert len(calls) == rr.MAX_AI_SECTIONS_PER_RUN
    second = rs.research(db, SETTINGS, opp, META, transport=transport, mode="continue")
    annual2 = next(d for d in second["documents"] if d["title"] == "Annual report")
    total_ai = sum(int(d["ai_sections_read"]) for d in second["documents"])
    assert annual2["ai_sections_read"] == annual2["sections_total"] or total_ai >= annual2["sections_total"]
    third = rs.research(db, SETTINGS, opp, META, transport=transport, mode="continue")
    assert third["outcome"] == "people_found", third["coverage"]
    lucy = rs.person_detail(db, _person(db, "Lucy Wairimu")[0][0])
    assert lucy["roles"][0]["role_title"] == "Cargo Development Manager" and lucy["roles"][0]["organisation"] == "Example Air"


def test_budget_refusal_leaves_research_incomplete_with_the_reason(rdb):  # noqa: F811
    db = rdb
    opp = _opp(db)
    db.run("flag_set", key="ai_kill_switch", value="true")
    out = rs.research(db, SETTINGS, opp, META, transport=lambda *_a: (json.dumps({"people": []}), 10, 10))
    assert out["outcome"] == "incomplete"
    assert any("budget" in x for x in out["coverage"]["limits_hit"])
    assert any(d["ai_status"] == "budget_refused" for d in out["documents"])


def test_no_people_found_is_distinct_from_incomplete(rdb):  # noqa: F811
    db = rdb
    opp = _opp(db)
    db.pg.run(f"DELETE FROM opportunity_people WHERE opportunity_id = '{opp}'")
    # the opportunity's documents name a contact; replace with a document set that names nobody by adding nothing and
    # reading a fresh opportunity: use the Uganda notice, which names no one
    ug = db.pg.val("SELECT o.id FROM opportunities o JOIN signals s ON s.id = o.signal_id WHERE s.tender_ref = 'EXA-GSSA-2026-302'")
    out = rs.research(db, NO_AI, ug, META)
    assert out["outcome"] == "no_people_found" and not out["found"]
    assert out["coverage"]["remaining"] == []
    rs.add_research_source(db, ug, url="https://unreachable.example/page", title=None, text=None, meta=META)
    out2 = rs.research(db, NO_AI, ug, META, fetch=Web({"https://unreachable.example/page": retrieval.RetrievalFailed("timed out")}))
    assert out2["outcome"] == "incomplete"


def test_same_name_without_a_known_organisation_is_never_merged_and_review_is_reversible(rdb):  # noqa: F811
    db = rdb
    opp = _opp(db)
    rs.add_research_source(db, opp, url=None, title="Conference notes", text="Speakers included Grace Achieng, Procurement Manager.", meta=META)
    rs.add_research_source(db, opp, url=None, title="Panel list", text="Panel: Grace Achieng, Logistics Consultant.", meta=META)
    rs.add_research_source(db, opp, url=None, title="Airline note", text="Grace Achieng, Head of Cargo at Example Air, will attend.", meta=META)
    rs.research(db, NO_AI, opp, META)
    graces = _person(db, "Grace Achieng")
    assert len(graces) == 3                                     # same name, organisation unknown on two of them: not merged
    dups = rs.duplicates(db)
    pairs = [d for d in dups if d["a"]["full_name"] == "Grace Achieng"]
    assert len(pairs) == 3 and all("same name" in d["reason"] for d in pairs)
    # merge one pair, then undo it exactly
    known = next(g[0] for g in graces if g[1])                  # the record bound to Example Air
    d = next(p for p in pairs if str(known) in (str(p["a"]["id"]), str(p["b"]["id"])))
    other = str(d["b"]["id"]) if str(d["a"]["id"]) == str(known) else str(d["a"]["id"])
    ev_other = db.pg.val(f"SELECT count(*) FROM person_evidence WHERE person_id = '{other}'")
    ev_known = db.pg.val(f"SELECT count(*) FROM person_evidence WHERE person_id = '{known}'")
    mid = rs.merge_duplicate(db, str(d["id"]), str(known), "same person: confirmed by phone", META)
    assert db.pg.val(f"SELECT merged_into_id FROM people WHERE id = '{other}'") == str(known)
    assert int(db.pg.val(f"SELECT count(*) FROM person_evidence WHERE person_id = '{known}'")) == int(ev_known) + int(ev_other)
    assert db.pg.val(f"SELECT count(*) FROM opportunity_people WHERE person_id = '{other}'") == "0"
    assert db.pg.val(f"SELECT status FROM person_duplicate_candidates WHERE id = '{d['id']}'") == "merged"
    merged_view = rs.person_detail(db, other)
    assert merged_view["person"]["state"] == "merged" and merged_view["person"]["merged_into_id"] == known
    with pytest.raises(rs.RelationshipRejected):
        rs.update_person(db, other, {"notes": "x"}, META)         # a merged record cannot be changed
    rs.undo_merge(db, mid, META)
    assert db.pg.val(f"SELECT merged_into_id FROM people WHERE id = '{other}'") in ("", None)
    assert db.pg.val(f"SELECT count(*) FROM person_evidence WHERE person_id = '{other}'") == ev_other
    assert db.pg.val(f"SELECT count(*) FROM person_evidence WHERE person_id = '{known}'") == ev_known
    assert db.pg.val(f"SELECT count(*) FROM opportunity_people WHERE person_id = '{other}'") == "1"
    assert db.pg.val(f"SELECT status FROM person_duplicate_candidates WHERE id = '{d['id']}'") == "open"
    rs.dismiss_duplicate(db, str(d["id"]), "different people: one is a consultant", META)
    assert db.pg.val(f"SELECT status FROM person_duplicate_candidates WHERE id = '{d['id']}'") == "dismissed"


def test_same_name_at_the_same_known_organisation_is_the_same_person(rdb):  # noqa: F811
    db = rdb
    opp = _opp(db)
    rs.add_research_source(db, opp, url=None, title="A", text="Maria Lopez, Head of Cargo at Example Air, opened the session.", meta=META)
    rs.add_research_source(db, opp, url=None, title="B", text="Example Air's Head of Cargo Maria Lopez said volumes grew.", meta=META)
    rs.research(db, NO_AI, opp, META)
    assert len(_person(db, "Maria Lopez")) == 1


def test_ai_proposals_keep_only_what_the_passage_binds(rdb):  # noqa: F811
    db = rdb
    opp = _opp(db)
    rs.add_research_source(db, opp, url=None, title="Briefing",
                           text="The Head of Cargo will chair the panel. Daniel Mwangi attended on behalf of the airline.", meta=META)

    def transport(_settings, _system, user):
        doc = user.split("<document>\n", 1)[-1]
        if "Daniel Mwangi" not in doc:
            return json.dumps({"people": []}), 100, 10
        return json.dumps({"people": [{"name": "Daniel Mwangi", "role": "Head of Cargo", "organisation": "Example Air", "role_status": "current",
                                       "quote": "Daniel Mwangi attended on behalf of the airline."}]}), 100, 10
    rs.research(db, SETTINGS, opp, META, transport=transport)
    rows = _person(db, "Daniel Mwangi")
    assert len(rows) == 1 and rows[0][3] in ("", None) and rows[0][1] in ("", None) and rows[0][2] in ("", None)
    notes = db.pg.val(f"SELECT string_agg(note, ' | ') FROM person_evidence WHERE person_id = '{rows[0][0]}'")
    assert "not in the quoted passage" in notes or "not bound" in notes
