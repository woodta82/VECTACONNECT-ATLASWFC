"""Who holds which role, at which organisation (instruction of 28 Oct 2026, second continuation, items 2 and 3).

Every case pairs what must be bound with what must stay unresolved. Documents mix several people and organisations, former
roles, quoted partners and appointments; a title or organisation that appears elsewhere is never attached to a person.
"""
from __future__ import annotations

import pytest

from app.domain import attribution as attr
from app.domain import research_plan as plan

ORGS = ["Savanna Example Air", "Kenya Civil Aviation Authority", "Blue Ridge Handling", "Example Air"]
SUBJECT = ["Savanna Example Air"]


def _by_name(text: str, **kw) -> dict[str, list[attr.Mention]]:
    out: dict[str, list[attr.Mention]] = {}
    for m in attr.mentions(text, ORGS, subject_orgs=SUBJECT, **kw):
        out.setdefault(m.name, []).append(m)
    return out


def test_appointment_binds_role_and_organisation_and_marks_the_predecessor_as_former():
    t = ("NAIROBI, 20 October 2026 — Savanna Example Air has appointed Grace Achieng as Head of Cargo, effective 1 January 2027, "
         "succeeding Peter Mwangi, who retires after 12 years.")
    got = _by_name(t)
    g = got["Grace Achieng"][0]
    assert (g.role, g.organisation, g.role_status, g.affiliation) == ("Head of Cargo", "Savanna Example Air", "incoming", "employee")
    assert g.pattern == "appointment" and "appointment announced" in g.binding
    p = got["Peter Mwangi"][0]
    assert (p.role, p.role_status) == ("Head of Cargo", "former")


def test_a_title_elsewhere_in_the_document_is_never_attached_to_a_person():
    t = "The Head of Cargo will chair the evaluation panel. Daniel Mwangi attended the briefing in Nairobi on behalf of the airline."
    assert _by_name(t) == {}                       # no binding: nothing is recorded, nothing is guessed


def test_first_organisation_in_the_sentence_is_not_the_persons_organisation():
    t = "Example Air thanked its customers. Speaking at the event, Lucy Njeri, Managing Director of Blue Ridge Handling, said capacity would rise."
    m = _by_name(t)["Lucy Njeri"][0]
    assert m.organisation == "Blue Ridge Handling" and m.affiliation == "other_organisation"
    t2 = "The Kenya Civil Aviation Authority and Savanna Example Air signed the agreement. Present was Samuel Otieno, Procurement Manager."
    s = _by_name(t2)["Samuel Otieno"][0]
    assert s.role == "Procurement Manager" and s.organisation is None and s.affiliation == "unknown"


def test_several_people_and_organisations_in_one_document_keep_their_own_bindings():
    t = ("The Kenya Civil Aviation Authority and Savanna Example Air signed the agreement. Present were Ruth Wanjiku, Director General of "
         "the Kenya Civil Aviation Authority, and Samuel Otieno, Procurement Manager. Savanna Example Air's Chief Commercial Officer "
         "Amina Yusuf said the deal covers Nairobi.")
    got = _by_name(t)
    assert (got["Ruth Wanjiku"][0].role, got["Ruth Wanjiku"][0].organisation) == ("Director General", "Kenya Civil Aviation Authority")
    assert got["Ruth Wanjiku"][0].affiliation == "other_organisation"
    assert got["Samuel Otieno"][0].organisation is None
    a = got["Amina Yusuf"][0]
    assert (a.role, a.organisation, a.affiliation) == ("Chief Commercial Officer", "Savanna Example Air", "employee")


def test_quoted_partner_is_a_partner_not_an_employee_of_the_subject():
    t = ('"We look forward to growing exports together," said John Lee, Chief Executive Officer of Blue Ridge Handling, '
         "Savanna Example Air's ground handling partner.")
    m = _by_name(t)["John Lee"][0]
    assert (m.organisation, m.affiliation) == ("Blue Ridge Handling", "partner")
    t2 = "Example Air thanked shippers. Speaking for Blue Ridge Handling, a customer of the airline, was Mary Atieno, Logistics Manager at Blue Ridge Handling."
    m2 = _by_name(t2)["Mary Atieno"][0]
    assert m2.organisation == "Blue Ridge Handling" and m2.affiliation in ("customer", "other_organisation")
    t3 = "Former Example Air Head of Cargo Tom Barasa now advises shippers."
    m3 = _by_name(t3)["Tom Barasa"][0]
    assert m3.affiliation == "other_organisation"            # "shippers" elsewhere in the sentence does not make anyone a customer


def test_former_roles_are_kept_as_former_and_a_new_role_is_separate():
    t = ("Former Example Air Head of Cargo Tom Barasa now advises shippers. Jane Wairimu, former Cargo Sales Manager at Example Air, "
         "joined Blue Ridge Handling as Commercial Director in 2025.")
    got = _by_name(t)
    assert (got["Tom Barasa"][0].role, got["Tom Barasa"][0].role_status) == ("Head of Cargo", "former")
    jw = {(m.role, m.organisation, m.role_status) for m in got["Jane Wairimu"]}
    assert ("Cargo Sales Manager", "Example Air", "former") in jw
    assert ("Commercial Director", "Blue Ridge Handling", "current") in jw


def test_incoming_role_from_will_join():
    m = _by_name("Michael Odhiambo will join Savanna Example Air as its new Country Manager Uganda from 1 February 2027.")["Michael Odhiambo"][0]
    assert (m.role, m.organisation, m.role_status, m.role_on_opportunity) == ("Country Manager Uganda", "Savanna Example Air", "incoming",
                                                                              "regional_representative")


def test_contact_line_binds_the_title_but_not_an_organisation():
    got = _by_name("Contact: Grace Achieng, Cargo Procurement Manager. Enquiries to: Paul Kariuki.")
    g = got["Grace Achieng"][0]
    assert g.role == "Cargo Procurement Manager" and g.organisation is None and g.role_on_opportunity == "procurement_contact"
    p = got["Paul Kariuki"][0]
    assert p.role is None and p.organisation is None and p.role_on_opportunity == "procurement_contact"


def test_leadership_page_lists_employees_but_a_quoted_visitor_on_the_same_site_is_not_one():
    page = "Our leadership\n\nGrace Achieng\nHead of Cargo\n\nPeter Mwangi – Country Manager Kenya\n\nNews: John Lee, CEO of Blue Ridge Handling, visited."
    got = _by_name(page, page_org="Savanna Example Air", page_kind="leadership", page_url="https://sea.example/leadership")
    assert (got["Grace Achieng"][0].organisation, got["Grace Achieng"][0].affiliation) == ("Savanna Example Air", "employee")
    assert "listed with this title" in got["Grace Achieng"][0].binding
    assert got["Peter Mwangi"][0].role == "Country Manager Kenya"
    assert (got["John Lee"][0].organisation, got["John Lee"][0].affiliation) == ("Blue Ridge Handling", "other_organisation")


def test_a_news_page_on_the_companys_site_does_not_make_everyone_named_an_employee():
    news = "Savanna Example Air hosted shippers in Nairobi. Logistics Manager Mary Atieno said demand was strong."
    m = _by_name(news, page_org="Savanna Example Air", page_kind="news", page_url="https://sea.example/news/1")["Mary Atieno"][0]
    assert m.role == "Logistics Manager" and m.organisation is None and m.affiliation == "unknown"
    plain = "Grace Achieng\nHead of Cargo"                       # a listing format, but not on a leadership page
    assert _by_name(plain, page_org="Savanna Example Air", page_kind="news") == {}


def test_board_page_members_are_board_members():
    page = "Board of Directors\n\nHelen Kimani\nNon-Executive Director\n"
    m = _by_name(page, page_org="Savanna Example Air", page_kind="leadership", page_url="https://sea.example/board")["Helen Kimani"][0]
    assert m.affiliation == "board_member"


def test_mention_never_establishes_decision_making_authority():
    for m in attr.mentions("Savanna Example Air has appointed Grace Achieng as Chief Executive Officer.", ORGS, subject_orgs=SUBJECT):
        assert m.role_on_opportunity != "decision_maker"
        assert "decision-making authority is not established" in m.relevance_basis


@pytest.mark.parametrize("quote,role,org,expect", [
    ("Grace Achieng, Head of Cargo at Savanna Example Air, said.", "Head of Cargo", "Savanna Example Air", (True, True)),
    ("Grace Achieng met the Head of Cargo at Savanna Example Air.", "Head of Cargo", "Savanna Example Air", (False, False)),
    ("Grace Achieng, Procurement Manager, thanked Blue Ridge Handling.", "Procurement Manager", "Blue Ridge Handling", (True, False)),
])
def test_ai_proposals_are_accepted_only_when_the_passage_binds_them(quote, role, org, expect):
    assert attr.binding_confirms(quote, "Grace Achieng", role, org, ORGS) == expect


def test_sections_cover_the_whole_text_and_respect_the_size():
    text = "\n\n".join(f"Paragraph {i}. " + "word " * 300 for i in range(40))
    secs = plan.sections(text, 6000)
    assert len(secs) > 1 and all(len(s) <= 6000 for s in secs)
    assert "".join(secs) == text.strip()
    long_para = "Sentence one. " * 2000
    secs2 = plan.sections(long_para, 6000)
    assert "".join(secs2) == long_para.strip() and all(len(s) <= 6000 for s in secs2)


def test_links_to_follow_prefer_leadership_and_newsroom_on_the_same_site():
    links = [("https://sea.example/about/leadership", "Our leadership"), ("https://other.example/news", "Partner news"),
             ("https://sea.example/media-centre", "Media centre"), ("https://sea.example/careers", "Careers"),
             ("https://sea.example/news/2026/savanna-appoints-head-of-cargo", "Savanna appoints new Head of Cargo"),
             ("https://sea.example/logo.png", "logo")]
    picks = plan.links_to_follow(links, "https://sea.example/", ["Savanna"])
    assert [k for _u, _a, k in picks] == ["leadership", "news", "article"]
    assert all(u.startswith("https://sea.example/") for u, _a, _k in picks)


def test_queries_use_organisation_roles_and_country():
    qs = plan.build_queries(module="airline_representation", title="GSSA tender KE", reference="SEA-CGO-2026-81",
                            organisations=["Savanna Example Air"], countries=["Kenya"], limit=8)
    texts = [q.text for q in qs]
    assert any('"Savanna Example Air"' in t and "procurement" in t and "Kenya" in t for t in texts)
    assert any("appoint" in t for t in texts) and any('"SEA-CGO-2026-81"' in t for t in texts)
    assert len(texts) == len(set(texts)) <= 8


def test_a_place_after_a_title_is_not_read_as_a_first_name():
    t = "Former Savanna Example Air Country Manager Uganda Paul Ssenyonga, now an independent consultant, attended."
    got = _by_name(t)
    assert list(got) == ["Paul Ssenyonga"]
    m = got["Paul Ssenyonga"][0]
    assert (m.role, m.role_status, m.organisation) == ("Country Manager Uganda", "former", "Savanna Example Air")


def test_head_of_a_function_is_a_title_not_an_organisation():
    got = attr.mentions("Enquiries to: Samuel Kiptoo, Head of Procurement, Example Port Authority.", ["Example Port Authority"],
                        subject_orgs=["Example Port Authority"])
    assert [(m.name, m.role, m.organisation) for m in got] == [("Samuel Kiptoo", "Head of Procurement", "Example Port Authority")]
    got = attr.mentions("Lucy Njeri, Head of Cargo at Blue Ridge Handling, said capacity would rise.", ["Example Air"])
    assert [(m.role, m.organisation) for m in got] == [("Head of Cargo", "Blue Ridge Handling")]
