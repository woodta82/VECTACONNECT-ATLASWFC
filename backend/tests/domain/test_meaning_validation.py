"""Review of 26 Oct 2026, §1 and §5 acceptance tests: meaning, not keyword presence.

The first three inputs are the review's own reproductions; each previously passed as supported."""
from datetime import date

import pytest

from app.domain import meaning
from app.domain.field_validation import FieldClaim as F
from app.domain.field_validation import validate_claim

REF = date(2026, 10, 26)


def v(claim_type, fields, text, quote=None):
    return validate_claim(claim_type, fields, text, claim_quote=quote or text, reference_date=REF)


def field(val, name):
    return next(f for f in val.fields if f.field == name)


# ---------------------------------------------------------------- negation, history, plans, conflicts

NEG = "Example Air is not inviting GSSA bids for Kenya. No appointment process is open."


def test_negated_tender_is_not_a_tender_and_not_open():
    r = v("gssa_tender", {"status": F("open", NEG), "country": F("Kenya", NEG)}, NEG)
    assert r.type_supported is False and "not happening" in r.type_reason
    assert field(r, "status").support == "unsupported"


@pytest.mark.parametrize("text,status,expected,why", [
    ("Example Air invites GSSA bids for Kenya. Proposals are due by 30 November 2026.", "open", "supported", "stated"),
    ("The Example Air GSSA tender for Kenya has closed.", "closed", "supported", "stated"),
    ("The Example Air GSSA tender for Kenya has closed.", "open", "unsupported", "not stated"),
    ("Example Air invited GSSA bids for Kenya in 2019.", "open", "unsupported", "past"),
    ("Example Air plans to invite GSSA bids for Kenya later this year.", "open", "unsupported", "plan"),
    ("Example Air's GSSA tender for Kenya has not been cancelled; bids are due on 30 November 2026.", "cancelled", "unsupported", "not"),
    # Amended 26 Oct 2026 (item 2): "the earlier tender" is another process; it does not contradict the current one.
    ("Example Air invites GSSA bids for Kenya; the earlier tender was cancelled.", "open", "supported", "other process"),
    ("Example Air invites GSSA bids for Kenya. Update: this tender is now closed.", "open", "review_required", "contradictory"),
])
def test_status_meaning(text, status, expected, why):
    r = v("gssa_tender", {"status": F(status, text)}, text)
    f = field(r, "status")
    assert f.support == expected, f.reason
    if expected != "supported" and why != "not stated":
        assert why in f.reason


def test_historical_and_planned_tenders():
    past = "In 2019 Example Air invited GSSA bids for Kenya."
    assert v("gssa_tender", {}, past).type_supported is False
    planned = "Example Air plans to invite GSSA bids for Kenya later this year."
    r = v("gssa_tender", {}, planned)
    assert r.type_supported is True and "planned" in field(r, "opportunity_type").extra["modality"]


def test_deadline_idioms_are_not_negations():
    text = "Example Air invites GSSA bids for Kenya, to be received no later than 30 November 2026."
    assert v("gssa_tender", {"status": F("open", text)}, text).type_supported is True
    assert meaning.polarity(text, text.index("invites")) == "affirmed"


# ---------------------------------------------------------------- geography roles

HQ = "Example Air, headquartered in France, invites GSSA bids for Kenya."


def test_issuer_location_is_not_delivery_scope():
    r = v("gssa_tender", {"country": F("France", HQ), "issuer_country": F("France", HQ)}, HQ)
    c, i = [f for f in r.fields if f.field == "country"][0], field(r, "issuer_country")
    assert c.support == "unsupported" and "where the issuer is based" in c.reason and c.extra["stated_roles"] == ["issuer"]
    assert i.support == "supported"
    k = field(v("gssa_tender", {"country": F("Kenya", HQ)}, HQ), "country")
    assert k.support == "supported" and "place of delivery" in k.reason


@pytest.mark.parametrize("text,country,role", [
    ("Request for Proposal: GSSA for cargo at Moi International Airport, Mombasa, Kenya.", "KE", "scope"),
    ("France-based Example Air seeks a GSSA in Kenya.", "FR", "issuer"),
    ("Kenya Airways invites GSSA bids for Uganda.", "KE", "name"),
    ("Kenya Airways invites GSSA bids for Uganda.", "UG", "scope"),
    ("Example Air will operate DXB-NBO from December.", "AE", "origin"),
    ("Example Air will operate DXB-NBO from December.", "KE", "destination"),
    ("New service from Dubai International to Kenya.", "KE", "destination"),
    ("Example Air (Kenya) issued a notice.", "KE", "unknown"),
])
def test_country_roles(text, country, role):
    airports = {"DXB": "AE", "NBO": "KE"}
    roles = [m.role for m in meaning.country_roles(text, country, airport_country=airports.get)]
    assert role in roles, roles


def test_unknown_role_never_supports_delivery():
    text = "Example Air (Kenya) issued a GSSA notice."
    f = field(v("gssa_tender", {"country": F("Kenya", text)}, text), "country")
    assert f.support == "unsupported" and "does not establish" in f.reason


def test_excluded_country_is_not_scope():
    text = "Example Air invites GSSA bids for East Africa excluding Uganda."
    assert field(v("gssa_tender", {"country": F("Uganda", text)}, text), "country").support == "unsupported"


# ---------------------------------------------------------------- eligibility

LIC = "Applicants must hold a valid local licence issued by the Kenya Civil Aviation Authority."


def test_invented_eligibility_is_unsupported():
    f = field(v("eligibility", {"eligibility": F("Applicants must own ten cargo aircraft", LIC)}, LIC), "eligibility")
    assert f.support == "unsupported" and "10" in f.reason and "aircraft" in f.reason


def test_stated_eligibility_keeps_the_source_words():
    f = field(v("eligibility", {"eligibility": F("must hold a local licence from the Kenya Civil Aviation Authority", LIC)}, LIC), "eligibility")
    assert f.support == "supported" and f.normalised == LIC


def test_eligibility_numbers_and_polarity_must_match():
    text = "Bidders must have at least 5 years of GSSA experience. No local licence is required."
    assert field(v("eligibility", {"eligibility": F("at least 3 years of GSSA experience", text)}, text), "eligibility").support == "unsupported"
    assert field(v("eligibility", {"eligibility": F("at least 5 years of GSSA experience", text)}, text), "eligibility").support == "supported"
    q = "No local licence is required."
    assert field(v("eligibility", {"eligibility": F("a local licence is required", q)}, text), "eligibility").support == "unsupported"


def test_negated_service_is_unsupported():
    text = "Example Air invites GSSA bids for Kenya; cargo handling is not included."
    r = v("gssa_tender", {"service": F("HANDLING", text)}, text)
    assert field(r, "service").support == "unsupported"


def test_a_denial_is_established_by_its_negation():
    deny = "Example Air confirms it is not running a GSSA tender for Kenya and Uganda this year."
    r = validate_claim("gssa_tender", {"country": F("Kenya", deny)}, deny, claim_quote=deny, reference_date=REF, stance="contradicts")
    assert r.type_supported and "denies" in r.type_reason and field(r, "country").support == "supported"
    assert validate_claim("gssa_tender", {}, deny, claim_quote=deny, reference_date=REF).type_supported is False
    affirm = "Example Air invites GSSA bids for Kenya."
    assert validate_claim("gssa_tender", {}, affirm, claim_quote=affirm, reference_date=REF, stance="contradicts").type_supported is False


def test_negation_just_outside_the_quote_is_read_in_the_document():
    doc = "It is untrue that Example Air is inviting GSSA bids for Kenya, the airline said."
    q = "Example Air is inviting GSSA bids for Kenya"
    r = validate_claim("gssa_tender", {"status": F("open", q)}, doc, claim_quote=q, reference_date=REF)
    assert r.type_supported is False and field(r, "status").support == "unsupported"


def test_between_x_and_y():
    t = "a new freighter service between Dubai (DXB) and Nairobi (NBO)"
    ap = {"DXB": "AE", "NBO": "KE"}.get
    assert "origin" in [m.role for m in meaning.country_roles(t, "AE", airport_country=ap)]
    assert "destination" in [m.role for m in meaning.country_roles(t, "KE", airport_country=ap)]
