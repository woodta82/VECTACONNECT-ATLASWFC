"""Open-web discovery rules (29 Oct 2026): queries per geography and capability area, publisher inference, access restrictions."""
from __future__ import annotations

from app.domain import open_web as ow

NAMES = {"KE": "Kenya", "UG": "Uganda", "OM": "Oman"}


def test_queries_cover_every_selected_area_and_country_with_formal_notices_first():
    qs = ow.build_queries(countries=["KE", "UG"], country_names=NAMES, modules=["airline_representation", "trucking_gateways"], keywords=None,
                         organisation=None, airline=None, max_per_country=10)
    ke = [q for q in qs if q.country == "KE"]
    assert ke[0].purpose.startswith("GSSA and cargo representation tenders") and '"Kenya"' in ke[0].text and "tender" in ke[0].text
    assert {q.module for q in ke} == {"airline_representation", "trucking_gateways"}
    assert any("road feeder" in q.text for q in ke) and len({q.text for q in qs}) == len(qs)
    assert {q.country for q in qs} == {"KE", "UG"}


def test_wide_search_is_capped_and_a_named_organisation_narrows_every_query():
    qs = ow.build_queries(countries=["OM"], country_names=NAMES, modules=[], keywords="GSSA", organisation="Gulf Example Airways", airline=None,
                         max_per_country=8)
    assert len(qs) == 8 and all('"Gulf Example Airways"' in q.text for q in qs) and all('"Oman"' in q.text for q in qs)
    assert qs[0].purpose.startswith("Named organisation or keywords")
    world = ow.build_queries(countries=[None], country_names=NAMES, modules=[], keywords=None, organisation=None, airline=None, max_per_country=12)
    assert all(q.country is None and "(worldwide)" in q.purpose for q in world) and len(world) == 11   # nine areas + two general queries


def test_publisher_authority_is_inferred_conservatively():
    assert ow.infer_authority("https://tenders.go.ke/notice/123") == "official_portal"
    assert ow.infer_authority("https://www.ppda.go.ug/tenders") == "official_portal"
    assert ow.infer_authority("https://www.aircargonews.net/story") == "trade_press"
    assert ow.infer_authority("https://www.example-air.example/press", organisation_hosts=["example-air.example"]) == "company_release"
    assert ow.infer_authority("https://random-blog.example/post") == "unverified"
    assert ow.host_of("https://www.Example.COM/x") == "example.com"


def test_restrictions_from_status_and_from_gate_pages():
    assert ow.restriction_from_status(401) == "login_required" and ow.restriction_from_status(402) == "payment_required"
    assert ow.restriction_from_status(403) == "access_denied" and ow.restriction_from_status(404) is None
    gate = "Tender documents. Please log in or register to download the tender document. Subscribe for full access."
    assert ow.restriction_from_page(gate, "Tender portal") == "payment_required"
    login = "Members area. Sign in to view this notice. Password:"
    assert ow.restriction_from_page(login) == "login_required"
    article = ("Example Air invites proposals from GSSA providers for Kenya. " * 40) + " You may log in to comment."
    assert ow.restriction_from_page(article) is None
    assert ow.corroboration_query("Example Air GSSA tender Kenya 2026", "https://x.example/a") == '"Example Air GSSA tender Kenya 2026"'
    assert ow.corroboration_query(None, "https://x.example/notices/example-air-gssa-tender-kenya-2026") == "example air gssa tender kenya"
    assert ow.corroboration_query(None, "https://x.example/n/123") is None
