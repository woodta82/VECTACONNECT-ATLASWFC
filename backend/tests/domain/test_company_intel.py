"""Company intelligence rules (29 Oct 2026): supplied sheets, organisations named in text, purpose queries, relevance."""
from __future__ import annotations

from app.domain import company_intel as ci
from app.reference.airline_codes import resolve, split_codes
from app.reference.airports import airport


def test_supplied_bru_style_sheets_are_read_with_airport_country_codes_and_types():
    sheets = {
        "GSA l BRU": [["GSA", "Represented Airlines", "E-mail address"],
                      ["Example GSA Services NV", "LO | M6 | FO | 3O", "cargo@example-gsa.example"],
                      ["All-Carriers Cargo BV", "ALL", "ops@allcarriers.example"],
                      [None, None, None],
                      ["No Mail GSA", "KL/MP", "see website"]],
        "AIRLINE | BRU": [["Type", "Represented Airlines", "E-mail address"],
                          ["Passenger/Belly", "IB/VY", "bru.cargo@iberia.example"],
                          ["Cargo-only", "CV", "sales.bru@cargolux.example"]],
        "Notes": [["Just a note"]],
    }
    ds = ci.parse_supplied_sheets(sheets, filename="FF__GSA_List_BRU.xlsx")
    assert ds.airport_iata == "BRU" and ds.country == "BE"
    gsa = [r for r in ds.rows if r.kind == "gssa"]
    assert [r.name for r in gsa] == ["Example GSA Services NV", "All-Carriers Cargo BV", "No Mail GSA"]
    assert gsa[0].airline_codes == ["LO", "M6", "FO", "3O"] and gsa[0].emails == ["cargo@example-gsa.example"]
    assert gsa[1].airline_codes == [] and any("ALL" in n for n in gsa[1].notes)              # 'ALL' is a note, never a list of airlines
    assert gsa[2].emails == [] and any("not a valid address" in n for n in gsa[2].notes)
    air = [r for r in ds.rows if r.kind == "airline"]
    assert air[0].carrier_type == "passenger_belly" and air[0].airline_codes == ["IB", "VY"]
    assert air[1].carrier_type == "cargo_only" and air[1].airline_codes == ["CV"]
    assert any("Notes" in s for s in ds.skipped)
    assert split_codes("LO | M6") == ["LO", "M6"] and resolve("LO")[0] == "LOT Polish Airlines"
    assert resolve("ZZ9") == (None, "ZZ9 (airline not resolved)")
    assert airport("KGL")[2] == "RW" and airport("XXX") is None


def test_organisations_in_text_need_a_suffix_or_known_name_and_bind_kind_emails_and_representation_to_the_sentence():
    text = ("Thousand Hills Cargo Services Ltd is the cargo GSSA for RwandAir and Ethiopian Airlines at Kigali. Contact cargo@thousandhills.example. "
            "The weather was fine. Lakeside Travel Agency Ltd is the GSA for passenger ticket sales of Kenya Airways in Rwanda. "
            "Our partner Blue Ridge Handling provides ground handling at the airport.")
    found = {m.name: m for m in ci.organisations_in_text(text, known=["Blue Ridge Handling"], airline_names=["RwandAir", "Ethiopian Airlines", "Kenya Airways"])}
    th = found["Thousand Hills Cargo Services Ltd"]
    assert th.kind == "gssa" and "GSSA" in th.kind_basis
    assert th.emails == ["cargo@thousandhills.example"]
    assert set(th.represented) == {"RwandAir", "Ethiopian Airlines"} and th.representation_scope == "cargo"
    lt = found["Lakeside Travel Agency Ltd"]
    assert lt.representation_scope == "passenger" and lt.represented == ["Kenya Airways"]      # a passenger ticket-sales mandate, kept apart
    br = found["Blue Ridge Handling"]
    assert br.kind == "handler"
    assert "The" not in found and "Kigali" not in found                                       # no bare words, no places


def test_purpose_queries_follow_the_brief_geography_airport_and_kinds():
    qs = ci.build_purpose_queries(purpose="companies", brief="Find cargo GSAs operating in East Africa and the airlines they represent",
                                  countries=["RW"], country_names={"RW": "Rwanda"}, modules=["airline_representation"],
                                  kinds=ci.kinds_for(["airline_representation"]), airport_iata="KGL", organisation=None, max_per_country=8)
    texts = [q.text for q in qs]
    assert all('"Rwanda"' in t for t in texts) and all("Kigali" in t for t in texts)
    assert any("GSSA" in t for t in texts) and any("represented airlines" in t for t in texts)
    assert len(qs) <= 8 and len({t.lower() for t in texts}) == len(texts)
    people = ci.build_purpose_queries(purpose="people", brief="Identify cargo commercial directors", countries=[None], country_names={}, modules=[],
                                      kinds=[], airport_iata=None, organisation="Example Air", max_per_country=8)
    assert any("commercial director" in q.text for q in people) and all('"Example Air"' in q.text for q in people)
    market = ci.build_purpose_queries(purpose="market", brief=None, countries=["RW"], country_names={"RW": "Rwanda"}, modules=[], kinds=[],
                                      airport_iata=None, organisation=None, max_per_country=8)
    assert any("new route" in q.text for q in market) and any("appoint" in q.text for q in market)
    assert ci.kinds_for(["technology_solutions"]) == ["technology_provider"]
    assert ci.kinds_for([], ["forwarder", "bogus"]) == ["forwarder"]


def test_company_relevance_explains_every_point_and_caps_at_100():
    r = ci.company_relevance(kind="gssa", wanted_kinds=["gssa", "airline"], country="RW", brief_countries=["RW"], airport_iata="KGL", brief_airport="KGL",
                             represented=3, emails=2, website=True, evidence_count=4, brief_terms_hit=True)
    assert r["score"] == 100 and sum(c["points"] for c in r["components"]) == 100
    assert {c["key"] for c in r["components"]} == {"kind", "geography", "profile", "brief", "evidence"}
    weak = ci.company_relevance(kind=None, wanted_kinds=["gssa"], country="KE", brief_countries=["RW"], airport_iata=None, brief_airport=None,
                                represented=0, emails=0, website=False, evidence_count=1, brief_terms_hit=False)
    assert weak["score"] == 3 and all(c["reason"] for c in weak["components"])


def test_emails_in_text_mark_the_own_site_domain():
    out = ci.emails_in_text("Sales: sales@thousandhills.example. Agent mail: info@other.example", "thousandhills.example")
    assert [(e["email"], e["own_site"]) for e in out] == [("sales@thousandhills.example", "yes"), ("info@other.example", "no")]
