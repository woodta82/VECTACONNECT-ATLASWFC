"""27 Oct 2026 (second instruction), items 1, 2, 3 and 5: freight relevance, geography across the whole document, publication
age vs deadline vs verified status, and the interpretation failures. Every change has a positive and a negative case."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.domain import evidence as ev
from app.domain import qualification as q
from app.domain import relevance
from app.domain.eligibility import compare
from app.domain.field_validation import FieldClaim as F
from app.domain.field_validation import date_convention, dates_in_text, validate_claim

UTC = timezone.utc


def v(ctype, fields, text, *, title=None, quote=None, reviewer=False):
    return validate_claim(ctype, fields, text, claim_quote=quote or text, document_title=title, reviewer=reviewer)


def field(val, name):
    return next(f for f in val.fields if f.field == name)


# ------------------------------------------------------------------ item 1: freight relevance
@pytest.mark.parametrize("text,scope", [
    ("Example Air invites proposals from general sales and service agents for cargo sales representation in Kenya.", "cargo"),
    ("Example Air invites proposals from GSSA providers for representation in Kenya.", "cargo"),               # GSSA is the cargo term
    ('REQUEST FOR PROPOSAL FOR APPOINTMENT OF "GENERAL SALES AGENT" ("GSA") FOR PASSENGER SALES OF AIR INDIA LIMITED IN QATAR', "passenger"),
    ("Sample Airways invites proposals from general sales agents for representation in Bahrain.", "unclear"),  # generic GSA wording
    ("Harbour Air Services seeks a general sales agent for passenger and cargo sales in Qatar.", "mixed"),
    ("Appel d'offres : Air Atlas Maroc recherche un prestataire pour la manutention du fret à Casablanca, Maroc.", "cargo"),
    ("Licitación: servicios de transporte aéreo regular sometidos a obligaciones de servicio público en la ruta Menorca-Madrid.", "passenger"),
    ("Kenya Airports Authority invites tenders for ground handling services at Nanyuki Airstrip.", "unclear"),
])
def test_freight_scope_is_read_from_the_mandate_wording(text, scope):
    fs = relevance.freight_scope("gssa_tender", "GSSA", text, None)
    assert fs.scope == scope, fs.reason
    assert fs.support == {"cargo": "supported", "passenger": "unsupported", "mixed": "review_required", "unclear": "review_required"}[scope]


def test_trucking_needs_stated_freight_and_passenger_wording_still_counts():
    # Third instruction, item 2: a service code is not evidence that the work concerns freight.
    assert relevance.freight_scope("service_tender", "TRUCKING", "Andina Logistica requiere servicios de camionaje entre Lima y Santiago.", None).scope == "unclear"
    assert relevance.freight_scope("service_tender", "TRUCKING", "Andina Logistica requiere servicios de camionaje de carga aerea entre Lima y Santiago.", None).scope == "cargo"
    assert relevance.freight_scope("service_tender", "TRUCKING", "Sample Airways invites quotations for road feeder trucking services.", None).scope == "cargo"
    assert relevance.freight_scope("service_tender", "TRUCKING", "Coach transport for passengers between the terminals is requested.", None).scope == "passenger"


def test_generic_gsa_wording_alone_never_establishes_cargo_and_the_title_counts():
    text = "Sample Airways invites proposals from general sales agents for representation in Bahrain. Tender reference SAW-GSA-2027-05."
    r = v("gssa_tender", {"airline": F("Sample Airways", text), "country": F("Bahrain", text), "service": F("GSSA", text)}, text, title="RFP SAW-GSA-2027-05")
    assert field(r, "freight_scope").support == "review_required" and field(r, "freight_scope").value == "unclear"
    r2 = v("gssa_tender", {"airline": F("Sample Airways", text), "service": F("GSSA", text)}, text, title="RFP: cargo GSA, Bahrain")
    assert field(r2, "freight_scope").value == "cargo" and field(r2, "freight_scope").support == "supported"


def test_passenger_only_mandate_is_excluded_with_its_reason_and_other_facts_still_supported():
    t = "Gulf Example Airways invites proposals for the appointment of a General Sales Agent (GSA) for passenger sales and ticketing in Oman."
    r = v("gssa_tender", {"airline": F("Gulf Example Airways", t), "country": F("Oman", t), "service": F("GSSA", t), "status": F("open", t)}, t)
    fs = field(r, "freight_scope")
    assert fs.value == "passenger" and fs.support == "unsupported" and "excluded from the freight pipeline" in fs.reason
    assert field(r, "country").support == "supported" and field(r, "status").support == "supported"
    checks = q.airline_representation_checks(existence=ev.assess_claim([ev.EvidenceLink("d", "f", "official_portal", "supports")]),
                                             tender=ev.resolve_tender([], datetime(2026, 10, 27, tzinfo=UTC)), territory_cell_state="gap",
                                             capability_readiness="ready", eligibility_known=True, eligibility_met=True, scope_known=True,
                                             freight_scope="passenger", freight_reason=fs.reason)
    assert q.qualification_status(checks) == "blocked"
    assert {c.code: c.result for c in checks}["freight_relevance"] == "fail"
    with pytest.raises(q.OverrideRejected):      # an override cannot put a passenger tender into the freight pipeline
        q.validate_override(q.Override("freight_relevance", "pass", "we think it is cargo after all", datetime(2026, 10, 27, tzinfo=UTC)))


def test_mixed_and_unclear_mandates_stay_pending_review_not_qualified():
    for scope in ("mixed", "unclear"):
        checks = q.airline_representation_checks(existence=ev.assess_claim([ev.EvidenceLink("d", "f", "official_portal", "supports")]),
                                                 tender=ev.resolve_tender([], datetime(2026, 10, 27, tzinfo=UTC)), territory_cell_state="gap",
                                                 capability_readiness="ready", eligibility_known=True, eligibility_met=True, scope_known=True,
                                                 freight_scope=scope, freight_reason="x")
        assert q.qualification_status(checks) == "incomplete" and {c.code: c.result for c in checks}["freight_relevance"] == "review_required"


def test_reviewer_reading_replaces_the_derived_scope_but_an_extractor_label_does_not():
    t = "Sample Airways invites proposals from general sales agents for representation in Bahrain."
    r = v("gssa_tender", {"airline": F("Sample Airways", t), "freight_scope": F("cargo", t)}, t, reviewer=True)
    assert field(r, "freight_scope").value == "cargo" and "reviewer" in field(r, "freight_scope").reason
    r2 = v("gssa_tender", {"airline": F("Sample Airways", t), "freight_scope": F("cargo", t)}, t, reviewer=False)
    assert field(r2, "freight_scope").value == "unclear"


def test_combine_readings():
    assert relevance.combine(["cargo", "cargo"]) == "cargo"
    assert relevance.combine(["passenger"]) == "passenger"
    assert relevance.combine(["cargo", "passenger"]) == "mixed"
    assert relevance.combine(["passenger", "unclear"]) == "unclear"
    assert relevance.combine([]) == "unclear"


# ------------------------------------------------------------------ item 2: geography across the whole document
AIR_INDIA_T = 'REQUEST FOR PROPOSAL FOR APPOINTMENT OF "GENERAL SALES AGENT" ("GSA") FOR PASSENGER SALES OF AIR INDIA LIMITED AND AIR INDIA EXPRESS LIMITED IN QATAR'
AIR_INDIA_DEF = '"Territory" shall mean the geographical limits of the country i.e., Qatar.'
AIR_INDIA_DISC = "Disclaimer: this request for proposal is issued for passenger sales in Kingdom of Saudi Arabia."
AIR_INDIA_DOC = f"{AIR_INDIA_T}\n\nDate of Issue: 15-10-2026\n\n{AIR_INDIA_DEF}\n\n{AIR_INDIA_DISC}\n\nLast date for submission of proposal 06-11-2026"


def test_air_india_qatar_case_saudi_arabia_is_a_flagged_conflict_never_a_supported_territory():
    r = v("gssa_tender", {"country": F("Saudi Arabia", AIR_INDIA_DISC)}, AIR_INDIA_DOC, title=AIR_INDIA_T, quote=AIR_INDIA_T)
    c = field(r, "country")
    assert c.support == "review_required" and "geography conflict" in c.reason and "Qatar" in c.reason and c.extra.get("geography_conflict")
    assert r.geography_conflict and "Saudi Arabia" in r.geography_conflict and "Qatar" in r.geography_conflict
    assert "India" not in r.geography_conflict.split("as the territory")[0]        # "AIR INDIA" is a name, not a territory


def test_defined_territory_without_a_preposition_is_the_delivery_territory():
    r = v("gssa_tender", {"country": F("Qatar", AIR_INDIA_DEF)}, AIR_INDIA_DOC, title=AIR_INDIA_T, quote=AIR_INDIA_T)
    assert field(r, "country").support == "supported" and "defined territory" in field(r, "country").reason
    t2 = "Territory: Bahrain. Proposals are invited for cargo GSSA representation."
    assert field(v("gssa_tender", {"country": F("Bahrain", t2)}, t2), "country").support == "supported"
    t3 = "Lugar de ejecución: Madrid (ES300), País: España. Identificador 367A2025."
    assert field(v("service_tender", {"country": F("Spain", t3)}, t3, quote="Identificador 367A2025 licitación"), "country").support == "supported"
    # negative: a country merely mentioned after "i.e." in a different role is still not delivery
    t4 = "The issuer, i.e., Kenya Airways, is headquartered in Nairobi."
    assert field(v("gssa_tender", {"country": F("Kenya", t4)}, t4), "country").support == "unsupported"


def test_all_capitals_title_still_resolves_the_preposition():
    t = 'APPOINTMENT OF "GENERAL SALES AGENT" ("GSA") FOR PASSENGER SALES OF AIR INDIA LIMITED IN BENIN, COTE D\'IVOIRE, TOGO AND SENEGAL'
    for c in ("Senegal", "Togo", "Benin"):
        assert field(v("gssa_tender", {"country": F(c, t)}, t, title=t), "country").support == "supported", c


def test_multi_country_mandate_and_lots_are_not_a_conflict():
    title = "Request for proposal: cargo GSSA in Ghana, Togo and Benin"
    body = (f"{title}\n\nExample Air invites proposals from cargo GSSA providers in Ghana, Togo and Benin.\n\n"
            "Lot 1: Ghana (Accra). Lot 2: Togo (Lomé). Lot 3: Benin (Cotonou).")
    for c in ("Ghana", "Togo", "Benin"):
        r = v("gssa_tender", {"country": F(c, "Example Air invites proposals from cargo GSSA providers in Ghana, Togo and Benin.")}, body, title=title)
        assert field(r, "country").support == "supported" and r.geography_conflict is None, c
    lot = "Lot 2: Togo (Lomé). Lot 3: Benin (Cotonou)."
    assert field(v("tender_scope", {"contract_territory": F("Togo", lot)}, body, title=title, quote=lot), "contract_territory").support == "supported"
    assert field(v("tender_scope", {"contract_territory": F("Nigeria", lot)}, body, title=title, quote=lot), "contract_territory").support == "unsupported"


def test_conflict_needs_a_defined_territory_otherwise_the_passage_rule_stands():
    doc = "Example Air invites cargo GSSA proposals. Services are delivered in Kenya. The agreement is governed by the laws of England."
    r = v("gssa_tender", {"country": F("Kenya", "Services are delivered in Kenya.")}, doc, title="Request for proposal")
    assert field(r, "country").support == "supported" and r.geography_conflict is None
    doc2 = "Request for proposal: cargo GSSA in Kenya\n\nDisclaimer: this request is issued for cargo sales in Uganda."
    r2 = v("gssa_tender", {"country": F("Uganda", "Disclaimer: this request is issued for cargo sales in Uganda.")}, doc2, title="Request for proposal: cargo GSSA in Kenya")
    assert field(r2, "country").support == "review_required" and r2.geography_conflict


def test_issuer_and_applicant_locations_keep_their_roles_in_a_conflict_check():
    doc = ("Request for proposal: cargo GSSA in Qatar\n\nExample Air, headquartered in India, invites proposals from agents registered in the United Arab Emirates "
           "for cargo sales representation in Qatar.")
    quote = "Example Air, headquartered in India, invites proposals from agents registered in the United Arab Emirates for cargo sales representation in Qatar."
    r = v("gssa_tender", {"country": F("Qatar", quote), "issuer_country": F("India", quote)}, doc, title="Request for proposal: cargo GSSA in Qatar", quote=quote)
    assert field(r, "country").support == "supported" and field(r, "issuer_country").support == "supported"
    assert r.geography_conflict is None
    assert field(v("gssa_tender", {"country": F("India", quote)}, doc, title="Request for proposal: cargo GSSA in Qatar", quote=quote), "country").support == "unsupported"


def test_french_city_with_airport_descriptor_resolves_the_country():
    t = "Appel d'offres : Air Atlas Maroc recherche un prestataire pour la manutention du fret à l'aéroport de Casablanca, Maroc."
    assert field(v("service_tender", {"country": F("Morocco", t)}, t), "country").support == "supported"
    assert field(v("service_tender", {"country": F("Algeria", t)}, t), "country").support == "unsupported"


# ------------------------------------------------------------------ item 3: publication age, deadline and verified status are separate
def obs(doc, published, status=None, deadline=None):
    return ev.TenderObservation(doc, f"fam-{doc}", "src", "official_portal", published, status, deadline=deadline)


NOW = datetime(2026, 10, 27, tzinfo=UTC)


def test_old_open_wording_without_a_closing_date_is_unverified_not_open_and_no_date_is_invented():
    t = ev.resolve_tender([obs("d1", NOW - timedelta(days=400), "open")], NOW, age_days=90)
    assert t.status == "unverified" and t.stated_status == "open" and t.deadline is None and not t.actionable
    assert "no closing date" in t.basis and "400 days ago" in t.basis
    checks = {c.code: c for c in q.airline_representation_checks(existence=ev.assess_claim([ev.EvidenceLink("d1", "f", "official_portal", "supports")]), tender=t,
                                                                 territory_cell_state="gap", capability_readiness="ready", eligibility_known=True, eligibility_met=True,
                                                                 scope_known=True, freight_scope="cargo")}
    assert checks["live_status"].result == "review_required" and checks["not_expired"].result == "unknown"


def test_old_notice_without_status_wording_is_historical_and_recent_one_is_unknown():
    old = ev.resolve_tender([obs("d1", NOW - timedelta(days=1500))], NOW, age_days=90)
    assert old.status == "historical" and "historical" in old.basis and old.deadline is None
    recent = ev.resolve_tender([obs("d1", NOW - timedelta(days=5))], NOW, age_days=90)
    assert recent.status == "unknown" and "no supported status wording" in recent.basis


def test_a_stated_deadline_decides_before_age_and_terminal_statuses_are_untouched():
    from app.domain.deadlines import StatedDeadline
    passed = StatedDeadline.from_json({"precision": "date", "day": "2023-06-20", "earliest_utc": "2023-06-19T10:00:00+00:00", "latest_utc": "2023-06-21T12:00:00+00:00"})
    assert passed is not None
    t = ev.resolve_tender([obs("d1", NOW - timedelta(days=1200), "open", passed)], NOW, age_days=90)
    assert t.status == "expired"
    assert ev.resolve_tender([obs("d1", NOW - timedelta(days=1200), "cancelled")], NOW, age_days=90).status == "cancelled"
    assert ev.resolve_tender([obs("d1", NOW - timedelta(days=30), "open")], NOW, age_days=90).status == "open"        # recent: open, deadline unknown


def test_age_threshold_is_configurable(monkeypatch):
    monkeypatch.setenv("NOTICE_AGE_REVIEW_DAYS", "30")
    assert ev.age_review_days() == 30
    assert ev.resolve_tender([obs("d1", NOW - timedelta(days=45), "open")], NOW).status == "unverified"
    monkeypatch.setenv("NOTICE_AGE_REVIEW_DAYS", "60")
    assert ev.resolve_tender([obs("d1", NOW - timedelta(days=45), "open")], NOW).status == "open"


def test_procedural_submission_wording_is_not_an_open_status():
    t = "Applicants shall submit a separate application for each territory they apply for."
    assert field(v("gssa_tender", {"status": F("open", t)}, t, quote="Request for proposal for appointment of passenger general sales agents"), "status").support == "unsupported"
    t2 = "Last date for submission of proposal 06-11-2026"
    assert field(v("gssa_tender", {"status": F("open", t2)}, t2, quote="Request for proposal for appointment of cargo GSSA"), "status").support == "supported"


# ------------------------------------------------------------------ item 5: the demonstrated failures
def test_french_procurement_announcements_and_service_terminology():
    t = "Avis d'appel public à la concurrence : Air Exemple recherche des prestataires pour l'assistance en escale fret à l'aéroport de Lomé, Togo."
    r = v("service_tender", {"service": F("HANDLING", t), "status": F("open", t), "country": F("Togo", t)}, t)
    assert r.type_supported and field(r, "service").support == "supported" and field(r, "status").support == "supported" and field(r, "country").support == "supported"
    t2 = "Procédure de sélection des prestataires d'assistance en escale autorisés à rendre les services faisant l'objet d'une limitation"
    assert v("service_tender", {"service": F("HANDLING", t2)}, t2).type_supported
    t3 = "Sélection d'un opérateur pour l'exercice des services d'assistance en escale. Date limite de réception des offres : 20 mars 2027."
    r3 = v("service_tender", {"service": F("HANDLING", t3), "status": F("open", t3)}, t3)
    assert r3.type_supported and field(r3, "status").support == "supported"
    neg = "Air Exemple n'a pas lancé d'appel d'offres pour l'assistance en escale cette année."
    assert not v("service_tender", {"service": F("HANDLING", neg)}, neg).type_supported


def test_spanish_submission_and_award_wording():
    t = "Convocatoria: Carga Ejemplo S.A. solicita ofertas para servicios de manipulación de carga aérea en Bogotá, Colombia. Plazo de presentación de ofertas: 20 de febrero de 2027."
    r = v("service_tender", {"service": F("HANDLING", t), "status": F("open", t)}, t)
    assert r.type_supported and field(r, "status").support == "supported" and field(r, "service").support == "supported"
    a = "Adjudicación: la licitación CEJ-HDL-2026-9 ha sido adjudicada a la empresa Servicios Andinos."
    assert field(v("tender_status", {"status": F("awarded", a)}, a), "status").support == "supported"
    b = "Las empresas asignadas para prestar los servicios de asistencia en tierra a terceros son Aviapartner, Groundforce y Swissport."
    assert field(v("tender_status", {"status": F("awarded", b)}, b), "status").support == "supported"
    assert field(v("service_tender", {"status": F("open", a)}, a), "status").support == "unsupported"


def test_seeking_qualified_agents_and_eoi_language():
    t = "Example Air is seeking qualified General Sales and Service Agents to represent its cargo business in Zambia and Zimbabwe."
    r = v("gssa_tender", {"status": F("open", t), "country": F("Zambia", t)}, t)
    assert r.type_supported and field(r, "status").support == "supported" and field(r, "country").support == "supported"
    e = "Expression of Interest EOI-RFS-2027-4: Sample Airways plans to contract qualified road feeder service providers for cargo trucking between Nairobi and Kampala."
    r2 = v("service_tender", {"service": F("TRUCKING", e), "tender_ref": F("EOI-RFS-2027-4", e)}, e)
    assert r2.type_supported and "planned" not in r2.type_reason, r2.type_reason
    n = "Example Air has no plans to appoint general sales agents in Zambia this year."
    assert not v("gssa_tender", {"status": F("open", n)}, n).type_supported


def test_should_have_and_tender_security_keep_their_meaning():
    t = "The Applicant should have at least three years of cargo GSA experience in the Territory. A Tender Security of USD 10,000 is required with the proposal."
    ok = field(v("eligibility", {"eligibility": F("at least three years of cargo GSA experience in the Territory", t)}, t), "eligibility")
    assert ok.support == "supported" and ok.extra.get("modality") == "advisory" and "advisory" in ok.reason
    sec = field(v("eligibility", {"eligibility": F("a Tender Security of USD 10,000", t)}, t), "eligibility")
    assert sec.support == "supported" and sec.extra.get("modality") == "mandatory"
    assert field(v("eligibility", {"eligibility": F("at least five years of cargo GSA experience in the Territory", t)}, t), "eligibility").support == "unsupported"
    assert field(v("eligibility", {"eligibility": F("a Tender Security of USD 100,000", t)}, t), "eligibility").support == "unsupported"
    k = "Tender Security of Kenya shillings one hundred thousand (Kshs. 100,000.00) only"
    assert field(v("eligibility", {"eligibility": F("Tender Security of Kenya shillings one hundred thousand (Kshs. 100,000.00)", k)}, k), "eligibility").support == "supported"
    assert field(v("eligibility", {"eligibility": F("Tender Security of Kshs. 1,000,000.00", k)}, k), "eligibility").support == "unsupported"
    five = "The Applicant should have at least 5(five) years of experience in travel business in the Territory."
    assert field(v("eligibility", {"eligibility": F("at least 5 years of experience in travel business in the Territory", five)}, five), "eligibility").support == "supported"
    assert field(v("eligibility", {"eligibility": F("at least 3 years of experience in travel business in the Territory", five)}, five), "eligibility").support == "unsupported"


def test_amendment_replacing_a_quantity():
    s = "The closing date is extended from 12 February 2027 to 26 February 2027 at 16:00 CAT; the requirement for four years of audited accounts is reduced to three years."
    assert compare("three years of audited accounts", s)[0] == "supported"
    assert compare("four years of audited accounts", s)[0] == "unsupported" and "superseded" in compare("four years of audited accounts", s)[1]
    s2 = "The minimum annual turnover is increased from USD 1 million to USD 2 million."
    assert compare("a minimum annual turnover of USD 2 million", s2)[0] == "supported"
    assert compare("a minimum annual turnover of USD 1 million", s2)[0] == "unsupported"
    plain = "Bidders must have four years of audited accounts."
    assert compare("four years of audited accounts", plain)[0] == "supported"         # no amendment wording: nothing is superseded


def test_deadline_extension_and_revised_status_evidence():
    t = "Update of 24 October 2026: proposals are now due on 23 February 2027. The tender remains open."
    r = v("tender_status", {"status": F("revised", t), "deadline": F("2027-02-23", t)}, t)
    assert field(r, "status").support == "supported" and field(r, "deadline").support == "supported"
    t2 = "The closing date, previously 12 March 2027, is now 26 March 2027."
    r2 = v("tender_status", {"status": F("revised", t2), "deadline": F("2027-03-26", t2)}, t2)
    assert field(r2, "status").support == "supported" and field(r2, "deadline").support == "supported"
    assert field(v("tender_deadline", {"deadline": F("2027-03-12", t2)}, t2), "deadline").support == "unsupported"
    plain = "Proposals are due on 23 February 2027."
    assert field(v("tender_status", {"status": F("revised", plain)}, plain), "status").support == "unsupported"


def test_numeric_dates_follow_the_notice_convention_or_wait_for_review():
    doc = "Date of issue: 20-01-2027.\n\nLast date for submission of proposals: 05-03-2027 at 15:00 NPT."
    assert date_convention(doc) == "dmy"
    assert [d.day.isoformat() for d in dates_in_text("05-03-2027", convention="dmy")] == ["2027-03-05"]
    q_ = "Last date for submission of proposals: 05-03-2027 at 15:00 NPT."
    ok = field(v("gssa_tender", {"deadline": F("2027-03-05T15:00:00", q_)}, doc, quote=q_), "deadline")
    assert ok.support == "supported" and "day-first" in ok.reason
    assert field(v("gssa_tender", {"deadline": F("2027-05-03T15:00:00", q_)}, doc, quote=q_), "deadline").support == "unsupported"
    alone = "Closing date: 05/03/2027."
    held = field(v("gssa_tender", {"deadline": F("2027-03-05", alone)}, alone), "deadline")
    assert held.support == "review_required" and "5 March 2027" in held.reason and "3 May 2027" in held.reason and held.extra.get("ambiguous_date") == "05/03/2027"
    mixed = "Issued 13/01/2027. Also 01/13/2027. Closing 05/03/2027."
    assert date_convention(mixed) is None
    assert [d.day.isoformat() for d in dates_in_text("Deadline: 02-Mar-2026, 23:59 (GMT -4.00)")] == ["2026-03-02"]


# ------------------------------------------------------------------ found by held-out set 3 (run once), fixed afterwards; held-out set 4 was
# written before these fixes
def test_territory_definition_with_ie_and_no_comma_still_conflicts_with_a_disclaimer():
    title = "Request for proposal: cargo GSSA for the Territory"
    d = '"Territory" shall mean the geographical limits of the country, i.e. Bahrain.'
    disc = "Disclaimer: this request for proposal is issued for cargo sales in the State of Kuwait and is governed by the laws of Kuwait."
    doc = f"{title}\n\nExample Air invites proposals from cargo GSSA providers for the Territory.\n\n{d}\n\n{disc}"
    k = v("gssa_tender", {"country": F("Kuwait", disc)}, doc, title=title, quote="Example Air invites proposals from cargo GSSA providers for the Territory.")
    assert field(k, "country").support == "review_required" and k.geography_conflict and "Bahrain" in k.geography_conflict
    b = v("gssa_tender", {"country": F("Bahrain", d)}, doc, title=title, quote="Example Air invites proposals from cargo GSSA providers for the Territory.")
    assert field(b, "country").support == "supported"


def test_a_definition_that_cannot_be_read_holds_other_countries_for_review():
    title = "Request for proposal: cargo GSSA for the Territory"
    d = '"Territory" shall mean the area set out in Annex 4.'
    other = "Services are delivered in Kuwait."
    doc = f"{title}\n\n{d}\n\n{other}"
    r = v("gssa_tender", {"country": F("Kuwait", other)}, doc, title=title, quote=other)
    assert field(r, "country").support == "review_required" and "defines its territory" in field(r, "country").reason
    # without a territory definition the passage rule stands
    doc2 = f"Request for proposal: cargo GSSA\n\n{other}"
    assert field(v("gssa_tender", {"country": F("Kuwait", other)}, doc2, title="Request for proposal: cargo GSSA", quote=other), "country").support == "supported"


def test_sentences_do_not_break_on_abbreviations():
    from app.domain import meaning
    assert meaning._sentences("The country, i.e. Bahrain. Corrigendum No. 2 applies. Tender Security Kshs. 100,000.") == [
        "The country, i.e. Bahrain.", "Corrigendum No. 2 applies.", "Tender Security Kshs. 100,000."]


def test_amendments_without_extended_or_amended_wording():
    t = "The minimum annual turnover is increased from USD 1 million to USD 2 million. The closing date, previously 12 March 2027, is now 26 March 2027."
    r = v("tender_status", {"status": F("revised", t), "deadline": F("2027-03-26", t)}, t)
    assert r.type_supported and field(r, "status").support == "supported" and field(r, "deadline").support == "supported"
    m = "The closing date has been moved from 4 March 2027 to 18 March 2027."
    assert field(v("tender_status", {"status": F("revised", m)}, m), "status").support == "supported"
    assert field(v("tender_deadline", {"deadline": F("2027-03-04", m)}, m), "deadline").support == "unsupported"
    plain = "Proposals are due on 26 March 2027."
    assert not v("tender_status", {"status": F("revised", plain)}, plain).type_supported or \
        field(v("tender_status", {"status": F("revised", plain)}, plain), "status").support == "unsupported"


def test_deadline_for_eoi_submissions_is_open_wording():
    t = "Deadline for EOI submissions: 28 January 2027, 17:00 (UTC+3)."
    assert field(v("service_tender", {"status": F("open", t)}, t, quote="Expression of Interest: road feeder services"), "status").support == "supported"
    n = "The deadline for submissions passed on 28 January 2025 and the EOI is closed."
    assert field(v("service_tender", {"status": F("open", n)}, n, quote="Expression of Interest: road feeder services"), "status").support == "unsupported"
