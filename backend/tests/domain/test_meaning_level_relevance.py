"""27 Oct 2026, third instruction: freight relevance at the meaning level (item 1), no broad keyword shortcuts (item 2),
announced vs verified open (item 3) and the remaining interpretation errors (item 4). Positive and negative cases."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.domain import evidence as ev
from app.domain import identity, meaning, qualification as q
from app.domain import relevance
from app.domain.field_validation import FieldClaim as F
from app.domain.field_validation import validate_claim

UTC = timezone.utc
NOW = datetime(2026, 10, 27, tzinfo=UTC)


def v(ctype, fields, text, *, title=None, quote=None):
    return validate_claim(ctype, fields, text, claim_quote=quote or text, document_title=title)


def scope(ctype, text, *, title=None, quote=None, service=None):
    fields = {"service": F(service, quote or text)} if service else {}
    r = v(ctype, fields, text, title=title, quote=quote)
    return next(f for f in r.fields if f.field == "freight_scope")


# ------------------------------------------------------------------ item 1
def test_the_reported_failure_cargo_excluded_through_the_field_validator():
    t = "Example Air invites proposals from general sales agents for representation in Kenya. Cargo sales are excluded from this mandate."
    fs = scope("gssa_tender", t)
    assert fs.value == "not_freight" and fs.support == "unsupported" and "excluded" in fs.reason
    assert any(c["kind"] == "excluded" and c["word"] == "cargo" for c in fs.extra["cues"])


@pytest.mark.parametrize("text", [
    "Example Air invites GSA proposals for passenger sales in Kenya, excluding cargo.",
    "Example Air invites proposals from general sales agents in Kenya. The appointment does not include cargo.",
    "Aerolínea Ejemplo convoca a agentes generales de ventas en Perú. Se excluye la carga de este mandato.",
    "Air Exemple recherche un agent général de vente au Sénégal, à l'exclusion du fret.",
])
def test_cargo_explicitly_excluded_never_supports_cargo(text):
    fs = scope("gssa_tender", text)
    assert fs.value in ("not_freight", "passenger") and fs.support == "unsupported", fs.reason


def test_passenger_only_scope_with_incidental_cargo_wording():
    t = ("Gulf Example Airways invites proposals for a general sales agent for passenger sales and ticketing in Bahrain. "
         "The airline's cargo business is handled by its own cargo division and is not affected.")
    fs = scope("gssa_tender", t)
    assert fs.value == "passenger" and fs.support == "unsupported"


def test_historical_cargo_activity_outside_the_current_mandate():
    t = "Example Air, which appointed a cargo GSA in Ghana in 2019, now invites proposals for a passenger sales agent in Ghana."
    fs = scope("gssa_tender", t)
    assert fs.value == "passenger" and any(c["kind"] == "background" and c["word"] == "cargo" for c in fs.extra["cues"])
    old = "In 2018 Example Air tendered its cargo handling. Example Air now invites proposals for passenger handling in Ghana."
    assert scope("service_tender", old, service="HANDLING").value == "passenger"


def test_conflicting_cargo_inclusion_and_exclusion_requires_review():
    doc = "Sample Airways invites proposals for cargo sales representation in Uganda.\n\nCargo sales are not part of this appointment."
    fs = scope("gssa_tender", doc, quote="Sample Airways invites proposals for cargo sales representation in Uganda.")
    assert fs.value == "conflicting" and fs.support == "review_required"


@pytest.mark.parametrize("text", [
    "Example Air invites proposals for the appointment of a cargo GSSA to sell freighter and bellyhold capacity in Ethiopia.",
    "Example Air invites proposals from general sales and service agents for cargo sales representation in Kenya.",
    "Example Air invites tenders for cargo ramp handling and ULD build-up at Accra, Ghana.",
    "Sample Airways invites quotations for road feeder trucking services between Dubai and Abu Dhabi.",
])
def test_genuine_positive_cargo_mandates(text):
    assert scope("gssa_tender" if "agent" in text or "GSSA" in text else "service_tender", text).value == "cargo"


def test_separate_passenger_and_cargo_lots_get_their_own_readings():
    title = "Request for proposals: general sales agents, Tanzania (two lots)"
    l1 = "Lot 1: passenger general sales agent in Tanzania. Reference CEA-PAX-2027-1."
    l2 = "Lot 2: cargo general sales and service agent in Tanzania. Reference CEA-CGO-2027-2."
    doc = f"Coastal Example Airways invites proposals for two separate lots.\n\n{l1}\n\n{l2}"
    assert scope("gssa_tender", doc, title=title, quote=l1).value == "passenger"
    assert scope("gssa_tender", doc, title=title, quote=l2).value == "cargo"


def test_a_passenger_title_does_not_override_a_cargo_lot_passage_and_vice_versa():
    assert relevance.freight_scope("gssa_tender", "GSSA", "Lot 2: cargo GSSA in Tanzania.", "Passenger and cargo agents").scope == "cargo"
    assert relevance.freight_scope("gssa_tender", "GSSA", "Lot 1: passenger sales agent in Tanzania.", "Cargo and passenger agents").scope == "passenger"


def test_scope_that_cannot_be_established_requires_review():
    fs = scope("gssa_tender", "Sample Airways invites proposals from general sales agents for representation in Bahrain.")
    assert fs.value == "unclear" and fs.support == "review_required"


def test_combined_signal_readings():
    assert relevance.combine(["cargo", "not_freight"]) == "conflicting"
    assert relevance.combine(["not_freight"]) == "not_freight"
    assert relevance.combine(["passenger", "not_freight"]) == "not_freight"
    assert relevance.combine(["conflicting", "cargo"]) == "conflicting"


def test_excluded_and_review_scopes_drive_qualification():
    t = ev.resolve_tender([], NOW)
    ex = ev.assess_claim([ev.EvidenceLink("d", "f", "official_portal", "supports")])
    for sc, res in (("not_freight", "fail"), ("conflicting", "review_required"), ("cargo", "pass")):
        checks = {c.code: c.result for c in q.airline_representation_checks(existence=ex, tender=t, territory_cell_state="gap",
                                                                              capability_readiness="ready", eligibility_known=True, eligibility_met=True,
                                                                              scope_known=True, freight_scope=sc, freight_reason="x")}
        assert checks["freight_relevance"] == res


# ------------------------------------------------------------------ item 2
@pytest.mark.parametrize("text,service", [
    ("Example Air invites tenders for ramp lighting maintenance at Mombasa airport, Kenya.", None),
    ("Sample Airways invites quotations for passenger loading bridge maintenance at Entebbe, Uganda.", None),
    ("Example Air invites proposals for aircraft catering supply at Kigali airport of about 300 tonnes of meals per year.", None),
    ("Kigali International Airport invites bids for a duty-free retail concession in the departures hall.", None),
    ("Example Air invites proposals for an RFS-compliant reporting module.", None),
    ("Example Air invites tenders for ULD-shaped signage at the terminal entrance.", None),
])
def test_incidental_keywords_never_establish_cargo(text, service):
    fs = scope("service_tender", text, service=service)
    assert fs.value != "cargo" and fs.support != "supported", fs.reason


def test_incidental_keyword_reading_through_the_validator_service_field():
    t = "Example Air invites tenders for ramp lighting maintenance at Mombasa airport, Kenya."
    r = v("service_tender", {"service": F("HANDLING", t)}, t)
    assert next(f for f in r.fields if f.field == "service").support == "unsupported"
    assert next(f for f in r.fields if f.field == "freight_scope").value == "not_freight"


def test_freight_capable_service_without_freight_wording_is_a_review_candidate_not_cargo():
    fs = scope("service_tender", "Kenya Airports Authority invites tenders for ground handling services at Nanyuki Airstrip.", service="HANDLING")
    assert fs.value == "unclear" and fs.support == "review_required"


# ------------------------------------------------------------------ item 3
def test_title_only_rfp_is_announced_not_open():
    t = "Request for proposal for the appointment of a cargo GSSA in Malawi. Example Air."
    st = next(f for f in v("gssa_tender", {"status": F("open", t)}, t).fields if f.field == "status")
    assert st.support == "unsupported" and st.reason.startswith("announced — current status unverified") and st.extra.get("announced")
    for heading in ("RFP EXA-CGO-2027-17: cargo GSSA, Malawi", "Appel d'offres : manutention du fret, Lomé", "Licitación: manipulación de carga aérea",
                    "Call for tenders: cargo GSSA, Malawi", "Expression of Interest EOI-RFS-2027-4"):
        assert next(f for f in v("service_tender", {"status": F("open", heading)}, heading).fields if f.field == "status").support == "unsupported", heading
    for live in ("Example Air invites proposals from cargo GSSA providers in Malawi.", "Proposals must be submitted by 28 April 2027.",
                 "The tender remains open until further notice.", "Harbour Air Services lists its open requests for proposal below."):
        assert next(f for f in v("gssa_tender", {"status": F("open", live)}, live).fields if f.field == "status").support == "supported", live


def obs(published, status=None, deadline=None):
    return ev.TenderObservation("d1", "f1", "src", "official_portal", published, status, deadline=deadline)


def test_announced_is_separate_from_open_and_from_age_and_from_deadline():
    from app.domain.deadlines import StatedDeadline
    recent = ev.resolve_tender([obs(NOW - timedelta(days=5))], NOW, age_days=90, announced=True)
    assert recent.status == "announced" and not recent.actionable and "announced — current status unverified" in recent.basis
    old = ev.resolve_tender([obs(NOW - timedelta(days=500))], NOW, age_days=90, announced=True)
    assert old.status == "historical"
    future = StatedDeadline.from_json({"precision": "date", "day": "2027-04-28", "earliest_utc": "2027-04-27T10:00:00+00:00",
                                       "latest_utc": "2027-04-29T12:00:00+00:00"})
    with_dl = ev.resolve_tender([obs(NOW - timedelta(days=5), None, future)], NOW, age_days=90, announced=True)
    assert with_dl.status == "open" and with_dl.actionable and "closing date" in with_dl.basis
    past = StatedDeadline.from_json({"precision": "date", "day": "2026-01-10", "earliest_utc": "2026-01-09T10:00:00+00:00",
                                     "latest_utc": "2026-01-11T12:00:00+00:00"})
    assert ev.resolve_tender([obs(NOW - timedelta(days=300), None, past)], NOW, announced=True).status == "expired"
    assert ev.resolve_tender([obs(NOW - timedelta(days=5))], NOW, announced=False).status == "unknown"
    checks = {c.code: c for c in q.airline_representation_checks(existence=ev.assess_claim([ev.EvidenceLink("d1", "f", "official_portal", "supports")]),
                                                                 tender=recent, territory_cell_state="gap", capability_readiness="ready",
                                                                 eligibility_known=True, eligibility_met=True, scope_known=True, freight_scope="cargo")}
    assert checks["live_status"].result == "review_required" and "announced" in checks["live_status"].rationale


# ------------------------------------------------------------------ item 4
def test_multistop_rotation_is_not_one_origin_destination_pair():
    t = "Example Cargo will launch a weekly freighter rotation Nairobi-Entebbe-Kigali-Nairobi from 5 January 2027."
    for name, country in (("origin", "Uganda"), ("destination", "Rwanda"), ("origin", "Kenya")):
        f = next(x for x in v("route_launch", {name: F(country, t)}, t).fields if x.field == name)
        assert f.support == "review_required" and "multi-stop rotation" in f.reason and f.extra["rotation"][0] == "Nairobi"
    assert meaning.rotation_in("weekly service routed Doha–Budapest–Helsinki–Doha") == ["Doha", "Budapest", "Helsinki", "Doha"]
    simple = "Sample Airways will start a twice-weekly freighter service from Dubai to Lagos on 15 February 2027."
    assert meaning.rotation_in(simple) is None
    assert next(x for x in v("route_launch", {"origin": F("United Arab Emirates", simple)}, simple).fields if x.field == "origin").support == "supported"


def test_daily_road_feeder_service_launch_is_recognised():
    t = "Oman Air Cargo has introduced a daily Road Feeder Service (RFS) between Muscat, Oman, and Dubai, UAE."
    assert v("route_launch", {}, t).type_supported
    t2 = "Example Cargo has introduced a daily road feeder service between Riyadh and Dammam, Saudi Arabia."
    assert v("route_launch", {}, t2).type_supported
    neg = "Example Cargo has no plans to introduce a road feeder service between Riyadh and Dammam."
    assert not v("route_launch", {}, neg).type_supported


def test_road_feeder_appointments_and_launches_belong_to_trucking_gateways():
    assert identity.module_for("representation_change", "TRUCKING")[0] == "trucking_gateways"
    assert identity.module_for("route_launch", "TRUCKING")[0] == "trucking_gateways"
    assert identity.module_for("representation_change", None)[0] == "airline_representation"
    # fourth instruction of 27 Oct, item 4: a route launch without trucking scope is a capacity and trade-lane event
    assert identity.module_for("route_launch", None)[0] == "capacity_lanes"
    from app.services.ingestion import _stated_trucking
    a = "Sample Airways has appointed Desert Road Logistics as its road feeder service provider for cargo between Muscat and Sohar."
    assert _stated_trucking(a, a) == "TRUCKING"
    assert _stated_trucking("Sample Airways has appointed a GSSA in Oman.", "x") is None
    assert _stated_trucking("Sample Airways will no longer use road feeder services.", "Sample Airways will no longer use road feeder services.") is None


@pytest.mark.parametrize("line", ["schedule b: kenya and uganda.", "SCHEDULE B: KENYA AND UGANDA.", "Schedule B: Kenya and Uganda.", "lot 2: kenya."])
def test_schedule_and_lot_wording_is_case_insensitive(line):
    r = v("tender_scope", {"contract_territory": F("Kenya", line)}, line)
    assert r.type_supported and next(f for f in r.fields if f.field == "contract_territory").support == "supported", line
    assert next(f for f in v("tender_scope", {"contract_territory": F("Tanzania", line)}, line).fields if f.field == "contract_territory").support == "unsupported"


def test_non_freight_concession_does_not_enter_the_freight_workflow():
    t = "Chhatrapati Shivaji Maharaj International Airport invites bids for a non-aeronautical services concession."
    assert scope("service_tender", t).value == "not_freight"


def test_ambiguous_cities_and_numeric_dates_still_wait_for_review():
    t = "Example Air invites proposals for cargo handling in Valencia. Closing date: 05/03/2027."
    r = v("service_tender", {"country": F("Spain", t), "deadline": F("2027-03-05", t)}, t)
    assert {f.field: f.support for f in r.fields}["country"] == "review_required"
    assert {f.field: f.support for f in r.fields}["deadline"] == "review_required"
