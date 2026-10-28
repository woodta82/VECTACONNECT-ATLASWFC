"""27 Oct 2026, item 3: the interpretation gaps listed in the 3.1.0-wfc.3 release report, each with positive and
negative cases. The relationship-level eligibility protections (test_amendments_domain.py) stay in force."""
from datetime import date

import pytest

from app.domain import eligibility as el
from app.domain import meaning
from app.domain.field_validation import FieldClaim as F
from app.domain.field_validation import _validate_deadline, validate_claim

REF = date(2026, 10, 27)


def v(claim_type, fields, text, quote=None, **kw):
    return validate_claim(claim_type, fields, text, claim_quote=quote or text, reference_date=REF, **kw)


def field(val, name):
    return next(f for f in val.fields if f.field == name)


# ---------------------------------------------------------------- "Only ... may apply"
@pytest.mark.parametrize("src,value", [
    ("Only bidders with an office in Gaborone or Francistown may apply.", "an office in Gaborone or Francistown"),
    ("This tender is open only to companies registered in Botswana.", "companies registered in Botswana"),
    ("Participation is restricted to IATA-accredited agents.", "IATA-accredited agents"),
    ("Bidders are eligible if they hold a current ground handling licence.", "eligible if they hold a current ground handling licence"),
])
def test_only_may_apply_and_restricted_to_are_eligibility(src, value):
    r = v("eligibility", {"eligibility": F(value, src)}, src)
    assert r.type_supported and field(r, "eligibility").support == "supported", (r.type_reason, field(r, "eligibility").reason)


def test_only_may_apply_negative_readings_are_not_supported():
    src = "Only bidders with an office in Gaborone or Francistown may apply."
    assert field(v("eligibility", {"eligibility": F("an office in Gaborone and Francistown", src)}, src), "eligibility").support == "unsupported"
    assert field(v("eligibility", {"eligibility": F("an office in Maun", src)}, src), "eligibility").support == "unsupported"


# ---------------------------------------------------------------- French and Spanish eligibility wording
@pytest.mark.parametrize("src,value", [
    ("Les soumissionnaires doivent disposer d'au moins 8 camions et d'une licence de transport routier valide au Sénégal.",
     "au moins 8 camions et une licence de transport routier valide au Sénégal"),
    ("Seuls les prestataires établis en Côte d'Ivoire peuvent soumissionner.", "les prestataires établis en Côte d'Ivoire"),
    ("Les candidats devront justifier d'une expérience de trois ans.", "une expérience de trois ans"),
    ("Los oferentes deben contar con al menos tres instructores certificados.", "al menos tres instructores certificados"),
    ("Sólo podrán participar empresas con sede en Chile.", "empresas con sede en Chile"),
    ("Requisitos: acreditar cinco años de experiencia en carga aérea.", "cinco años de experiencia en carga aérea"),
])
def test_french_and_spanish_eligibility_is_recognised(src, value):
    r = v("eligibility", {"eligibility": F(value, src)}, src)
    assert r.type_supported and field(r, "eligibility").support == "supported", (r.type_reason, field(r, "eligibility").reason)


@pytest.mark.parametrize("src,value", [
    ("Les soumissionnaires doivent disposer d'au moins 8 camions.", "au plus 8 camions"),
    ("Los oferentes deben contar con al menos tres instructores certificados.", "al menos treinta instructores certificados"),
    ("Les candidats devront justifier d'une expérience de trois ans.", "une expérience de cinq ans"),
])
def test_french_and_spanish_wrong_readings_are_not_supported(src, value):
    assert field(v("eligibility", {"eligibility": F(value, src)}, src), "eligibility").support == "unsupported"


# ---------------------------------------------------------------- an uninterpretable criterion stays visibly pending
def test_uninterpretable_eligibility_is_held_for_review_not_dropped():
    src = "Bidders will be expected to show a strong track record in the region."     # no recognised requirement wording
    r = v("eligibility", {"eligibility": F("a strong track record in the region", src)}, src)
    assert r.type_supported and "held for review" in r.type_reason                    # not rejected into oblivion
    f = field(r, "eligibility")
    assert f.support == "review_required" and "could not be interpreted" in f.reason
    # ... and still never 'supported', and a value the quote does not state is unsupported
    assert field(v("eligibility", {"eligibility": F("ten years of experience", src)}, src), "eligibility").support == "unsupported"


def test_other_claim_types_with_unrecognised_wording_are_still_rejected():
    src = "The weather in Nairobi is pleasant in July."
    assert v("gssa_tender", {"airline": F("Example Air", src)}, src).type_supported is False


# ---------------------------------------------------------------- "withdrawn with immediate effect"
@pytest.mark.parametrize("src", [
    "Addendum of 20 October 2026: the tender is withdrawn with immediate effect; a new procurement will be announced in 2027.",
    "Notice: tender EXA-1 has been annulled.", "The procurement has been terminated and will not be awarded.",
])
def test_withdrawn_annulled_terminated_are_cancelled_status(src):
    r = v("tender_status", {"status": F("cancelled", src)}, src)
    assert r.type_supported, r.type_reason
    assert field(r, "status").support == "supported", field(r, "status").reason


def test_withdrawn_is_not_open_and_a_withdrawn_bid_is_not_a_cancellation():
    src = "Addendum: the tender is withdrawn with immediate effect."
    assert field(v("tender_status", {"status": F("open", src)}, src), "status").support == "unsupported"
    bid = "One bidder withdrew its offer; the tender remains open and proposals are still invited."
    assert field(v("tender_status", {"status": F("cancelled", bid)}, bid), "status").support == "unsupported"
    assert field(v("tender_status", {"status": F("open", bid)}, bid), "status").support == "supported"


# ---------------------------------------------------------------- eligibility dates vs the submission deadline in one sentence
ONE = "Bidders must hold a certificate valid until 31 March 2027 and submit proposals by 15 January 2027."


def test_eligibility_dates_are_separated_from_the_deadline():
    assert el.compare("a certificate valid until 31 March 2027", ONE)[0] == "supported"
    assert el.compare("a certificate valid until 15 January 2027", ONE) == ("unsupported", "the source's 2027-01-15 is the submission deadline, not an eligibility date")
    sub = el.compare("proposals by 15 January 2027", ONE)
    assert sub[0] == "review_required" and "submission clause" in sub[1]
    # the deadline validator, the other way round: the certificate date is not the deadline
    assert _validate_deadline(F("2027-03-31", ONE), True, None).support == "unsupported"
    assert _validate_deadline(F("2027-01-15", ONE), True, None).support == "supported"


# ---------------------------------------------------------------- countries in table cells and parentheses keep their roles
def geo(claim_type, name, value, q):
    return field(v(claim_type, {name: F(value, q)}, q), name)


def test_table_cell_country_is_the_delivery_place():
    row = "GFS-TRN-2026-10 | Dangerous goods training | Doha, Qatar | 19 December 2026"
    assert geo("service_tender", "country", "Qatar", row).support == "supported"
    issuer_row = "GFS-TRN-2026-10 | Dangerous goods training | issued by Qatar Civil Aviation | 19 December 2026"
    assert geo("service_tender", "country", "Qatar", issuer_row).support == "unsupported"        # the role cue wins


def test_parenthesis_country_keeps_its_role():
    q = "Northern Cargo Airlines amends tender NCA-DATA-2026-6 (cargo documentation processing, Germany): the scope now includes Austria."
    assert geo("service_tender", "country", "Germany", q).support == "supported"
    assert geo("service_tender", "country", "Austria", q).support == "unsupported"                 # 'includes Austria' states no role
    org = "Example Air (Kenya) issued a GSSA notice."
    assert geo("gssa_tender", "country", "Kenya", org).support == "unsupported"                    # a name's parenthesis is not delivery
    lic = "Bidders need a licence (issued by Kenya) to operate in Uganda."
    assert geo("service_tender", "country", "Kenya", lic).support == "unsupported"
    assert geo("service_tender", "country", "Uganda", lic).support == "supported"


# ---------------------------------------------------------------- cities through the maintained register; ambiguous ones go to review
def test_cities_resolve_through_the_register():
    q = "Northern Cargo Airlines adds a third weekly freighter frequency between Frankfurt and Nairobi."
    assert geo("capacity_statement", "origin", "Germany", q).support == "supported"
    assert geo("capacity_statement", "destination", "Kenya", q).support == "supported"
    assert geo("capacity_statement", "destination", "Germany", q).support == "unsupported"
    fr = "Air Sahel invite les prestataires de services de camionnage (RFS) entre Dakar et Bamako."
    assert geo("service_tender", "country", "Senegal", fr).support == "supported"
    assert geo("service_tender", "country", "Mali", fr).support == "supported"
    assert geo("service_tender", "country", "Niger", fr).support == "unsupported"


def test_ambiguous_city_requires_review_never_a_guess():
    q = "Aerocarga convoca licitación para servicios de handling en Santiago."
    for value in ("Chile", "Spain", "Santiago"):
        f = geo("service_tender", "country", value, q)
        assert f.support == "review_required" and "Santiago" in f.reason, (value, f.reason)
    assert geo("service_tender", "country", "Kenya", q).support == "unsupported"                 # not even a candidate
    assert meaning.country_roles("services in Santiago", "CL") == []                             # never resolved silently


# ---------------------------------------------------------------- zone abbreviations only with established context
Q_SCT = "Proposals must be received no later than 22 December 2026 at 15:00 SCT."


def test_context_zone_is_a_fact_only_when_the_source_establishes_it():
    with_country = "Island Freight Airways invites proposals for cargo representation in Seychelles. " + Q_SCT
    assert _validate_deadline(F("2026-12-22T15:00:00", Q_SCT), True, None, with_country).extra["precision"] == "instant"
    explicit = _validate_deadline(F("2026-12-22T15:00:00", "Proposals are due 22 December 2026 at 15:00 SCT (UTC+4)."), True, None, None)
    assert explicit.extra["precision"] == "instant"
    alone = _validate_deadline(F("2026-12-22T15:00:00", Q_SCT), True, None, None)
    assert alone.extra["precision"] == "local_time" and "not established by the source" in alone.reason
    wrong_country = _validate_deadline(F("2026-12-22T15:00:00", Q_SCT), True, None, "Notice for Mauritius. " + Q_SCT)
    assert wrong_country.extra["precision"] == "local_time"
    ast = "Bids close 30 November 2026 at 12:00 AST."
    assert _validate_deadline(F("2026-11-30T12:00:00", ast), True, None, "Desert Air Cargo, Saudi Arabia, invites bids.").extra["precision"] == "instant"
    assert _validate_deadline(F("2026-11-30T12:00:00", ast), True, None, "Bids for Canada.").extra["precision"] == "local_time"


# ---------------------------------------------------------------- a reserved right to annul is not a cancellation (found on genuine notices)
@pytest.mark.parametrize("src", [
    "The Procuring Entity reserves the right to accept or reject any Tender, and to annul the Tendering process and reject all Tenders at any time prior to Contract Award.",
    "Airlines reserve the right to withdraw the RFP (in whole or in part) at any time.",
    "The Authority may at its discretion cancel this procurement without obligation to any bidder.",
    "L'autorité se réserve le droit d'annuler la procédure à tout moment.",
])
def test_a_reserved_right_to_annul_or_withdraw_is_not_a_cancelled_status(src):
    r = v("tender_status", {"status": F("cancelled", src)}, src)
    assert not (r.type_supported and field(r, "status").support == "supported"), (r.type_reason, field(r, "status").reason)


def test_an_actual_annulment_still_is():
    src = "The Procuring Entity has annulled the tendering process; no contract will be awarded."
    r = v("tender_status", {"status": F("cancelled", src)}, src)
    assert r.type_supported and field(r, "status").support == "supported"
