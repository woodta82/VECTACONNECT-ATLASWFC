"""The nine original WFC business workflows, end to end on PostgreSQL (28 Oct 2026 instruction, item 2).

Every input is loaded through the import workflow (or discovered from a registered source); every numerical output is
checked against a value calculated independently in this file from the same raw rows, never by calling the code under
test. Missing data must show an explicit gap, never a zero or a confident recommendation.

All data here is SYNTHETIC (invented organisations, example domains) and exercises the application's rules. It is not
evidence about WFC's live systems, which are not connected.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from app.domain.field_validation import FieldClaim as F
from app.services import discovery as dsc
from app.services import fit_service
from app.services import imports_service as imp
from app.services import ingestion as ing
from app.services import modules_service as mod
from app.services import ops_service
from app.services import opportunity_service as opps
from app.services import review_service as rev
from app.services import sources_service as srcs
from app.services.audit import RequestMeta
from tests.integration.sa import sadb  # noqa: F401
from tests.integration.test_review3_regressions import SETTINGS, Web, _listing, _page, model, rdb  # noqa: F401

META = RequestMeta(ip="203.0.113.20", request_id="req-wf", session_ref="sessworkflows1")
AS_OF = date(2026, 10, 15)                       # forwarder analysis date
SEP = (date(2026, 9, 1), date(2026, 9, 30))      # analysis period (a calendar month)
SHIP = date(2026, 10, 19)                        # a Monday
UTC = timezone.utc

# ------------------------------------------------------------------ raw data (the single source for expected values)
# (external_id, forwarder, origin, destination, flight_date, chargeable_kg, revenue_usd)
BOOKINGS = [
    ("A0", "Alpha Forwarding", "DXB", "NBO", date(2025, 8, 1), 400, 800),
    ("A1", "Alpha Forwarding", "DXB", "NBO", date(2025, 9, 10), 2000, 4000),
    ("A2", "Alpha Forwarding", "DXB", "NBO", date(2026, 8, 10), 1500, 3000),
    ("A3", "Alpha Forwarding", "DXB", "NBO", date(2026, 9, 10), 1200, 2520),
    ("A4", "Alpha Forwarding", "DXB", "NBO", date(2026, 10, 5), 900, 1800),
    ("B1", "Bravo Cargo", "DXB", "NBO", date(2025, 6, 1), 800, 1600),
    ("B2", "Bravo Cargo", "DXB", "NBO", date(2026, 6, 1), 700, 1400),
    ("C0", "Charlie Logistics", "DXB", "NBO", date(2025, 8, 1), 500, 1000),
    ("C1", "Charlie Logistics", "DXB", "NBO", date(2025, 9, 12), 1000, 2000),
    ("C2", "Charlie Logistics", "DXB", "NBO", date(2026, 8, 12), 1000, 2000),
    ("C3", "Charlie Logistics", "DXB", "NBO", date(2026, 9, 12), 1050, 2205),
    ("C4", "Charlie Logistics", "DXB", "NBO", date(2026, 10, 2), 1000, 2000),
    ("D1", "Delta Freight", "DXB", "NBO", date(2026, 8, 15), 5000, 9000),
    ("D2", "Delta Freight", "DXB", "NBO", date(2026, 9, 15), 6800, 12920),
    ("E1", "Echo Shipping", "NBO", "DXB", date(2026, 8, 20), 3000, 4500),
    ("E2", "Echo Shipping", "NBO", "DXB", date(2026, 9, 20), 2000, 3000),
    ("F1", "Foxtrot Air Logistics", "DXB", "EBB", date(2026, 9, 25), 500, 1250),
]
# (forwarder, status, lost_reason) quoted on 20 Sep 2026
QUOTES = ([("Alpha Forwarding", "won", "")] * 2 + [("Alpha Forwarding", "lost", "price")] * 3 + [("Alpha Forwarding", "lost", "service")]
          + [("Alpha Forwarding", "open", "")] * 2
          + [("Charlie Logistics", "won", "")] + [("Charlie Logistics", "lost", "price")] * 8 + [("Charlie Logistics", "lost", "transit")])
CAPACITY = [("CAP-1", "DXB", "NBO", SEP[0], SEP[1], 10000), ("CAP-2", "NBO", "DXB", SEP[0], SEP[1], 8000)]


def load(db, ds, text):
    r = imp.import_file(db, ds, f"{ds}.csv", text.encode(), None, META)
    assert r["reconciliation"]["rows_quarantined"] == 0, (ds, r["errors"])
    return r


def seed(db):
    load(db, "operating_companies", "name,country\nWFC-UAE,AE\nWFC-KE,KE\n")
    load(db, "airports", "iata_code,name,country,timezone\nDXB,Dubai International,AE,Asia/Dubai\nNBO,Jomo Kenyatta International,KE,Africa/Nairobi\n"
                         "EBB,Entebbe International,UG,Africa/Kampala\nDAR,Julius Nyerere International,TZ,Africa/Dar_es_Salaam\n"
                         "KGL,Kigali International,RW,Africa/Kigali\n")
    load(db, "airlines", "iata_code,name,country\nXA,Example Air,AE\nYB,Sample Airways,AE\n")
    load(db, "services", "code,name,category\nTRUCKING,Road feeder trucking,trucking\n")
    load(db, "stations", "code,name,is_offline,country,timezone\nNYK1,Nanyuki offline point,yes,KE,Africa/Nairobi\n"
                         "MSA1,Mombasa offline point,yes,KE,Africa/Nairobi\nKSM1,Kisumu offline point,yes,KE,Africa/Nairobi\n")
    load(db, "agreements", "external_id,airline_iata,airline_name,operating_company,territories,services,effective_from,effective_to,"
                           "exclusivity,appointment_rights\n"
                           "AG-1,XA,Example Air,WFC-KE,KE;RW,GSSA,2025-01-01,2028-12-31,exclusive,may_extend\n"
                           "AG-2,YB,Sample Airways,WFC-KE,KE,GSSA,2025-01-01,2028-12-31,exclusive,prohibited\n")
    load(db, "capabilities", "operating_company,service_code,station,status,valid_from,valid_to\n"
                             "WFC-KE,GSSA,NBO,verified,2025-01-01,2028-12-31\nWFC-KE,GSSA,EBB,verified,2025-01-01,2028-12-31\n"
                             "WFC-KE,GSSA,DAR,verified,2024-01-01,2026-01-01\nWFC-KE,TRAINING,,verified,2025-01-01,2028-12-31\n")
    load(db, "bookings", "external_id,forwarder,airline_iata,origin,destination,flight_date,booked_at,status,chargeable_weight,revenue,currency,"
                         "operating_company\n" + "".join(
                             f"{i},{f},XA,{o},{d},{fd},{fd}T08:00:00Z,confirmed,{kg},{rv}.00,USD,WFC-UAE\n" for i, f, o, d, fd, kg, rv in BOOKINGS))
    load(db, "quotes", "external_id,forwarder,origin,destination,quoted_at,status,lost_reason,amount,currency\n" + "".join(
        f"Q{n},{f},DXB,NBO,2026-09-20T08:00:00Z,{s},{lr},100.00,USD\n" for n, (f, s, lr) in enumerate(QUOTES)))
    load(db, "capacity", "external_id,airline_iata,origin,destination,period_start,period_end,basis,capacity_type,amount,snapshot_at\n" + "".join(
        f"{i},XA,{o},{d},{a},{b},weight_kg,bookable,{amt},2026-08-25T00:00:00Z\n" for i, o, d, a, b, amt in CAPACITY))
    load(db, "trucking", "external_id,provider,origin_station,gateway,departure_days,departure_time,transit_minutes\n"
                         "T-1,Rift Valley Haulage,NYK1,NBO,1;3;5,06:00,240\nT-2,Coast Road Lines,MSA1,NBO,7,06:00,600\n")
    load(db, "gateway_connections", "external_id,gateway,destination,airline_iata,flight_number,departure_days,departure_time,connection_cutoff_minutes\n"
                                    "G-1,NBO,DXB,XA,XA720,1;3;5,23:50,180\nG-2,NBO,DXB,XA,XA722,1;3;5,08:00,\n")
    events = []
    for n in range(1, 7):                         # six portal sessions, all quoted, one booked
        events.append(f"E{n}a,quote_request,S{n},,portal,2026-09-0{n}T08:00:00Z,Alpha Forwarding")
        events.append(f"E{n}b,quote,S{n},PB{n},portal,2026-09-0{n}T08:05:00Z,Alpha Forwarding")
    events.append("E1c,booking,S1,PB1,portal,2026-09-01T08:09:00Z,Alpha Forwarding")
    for n in range(1, 4):                         # three API integration failures
        events.append(f"X{n},integration_failure,,,api,2026-09-1{n}T10:00:00Z,Alpha Forwarding")
    load(db, "channel_events", "external_id,event_type,session_key,booking_ref,channel,occurred_at,forwarder\n" + "\n".join(events) + "\n")
    load(db, "contacts", "external_id,full_name,role_title,operating_company,is_internal\nP-1,Ops lead Nairobi,Operations,WFC-KE,yes\n")


# ------------------------------------------------------------------ independent calculations
def kg(forwarder=None, origin=None, destination=None, start=None, end=None):
    return sum(k for _i, f, o, d, fd, k, _r in BOOKINGS if (forwarder is None or f == forwarder) and (origin is None or o == origin)
               and (destination is None or d == destination) and (start is None or start <= fd <= end))


def revenue(origin, destination, start, end):
    return sum(r for _i, _f, o, d, fd, _k, r in BOOKINGS if o == origin and d == destination and start <= fd <= end)


# ------------------------------------------------------------------ 1. airline representation
TENDER = ("Example Air invites proposals from cargo general sales and service agents for Kenya. Reference XA-CGO-2026-90. "
          "Proposals must be submitted by {d}. The scope covers cargo sales and customer service.")
SCOPE_Q = "The scope covers cargo sales and customer service."


def test_1_airline_representation_discovery_to_pipeline(rdb):  # noqa: F811
    sadb = rdb  # noqa: F811
    seed(sadb)
    deadline = datetime.now(UTC).date() + timedelta(days=40)
    when = f"{deadline.day} {deadline.strftime('%B %Y')}"
    body = TENDER.format(d=when)

    def reply(doc):
        if "XA-CGO-2026-90" not in doc:
            return {"language": "en", "claims": []}
        return {"language": "en", "claims": [{"claim_type": "gssa_tender", "stance": "supports", "quote": body, "fields": {
            "airline": {"value": "Example Air", "quote": body}, "country": {"value": "Kenya", "quote": body},
            "service": {"value": "GSSA", "quote": body}, "status": {"value": "open", "quote": body},
            "tender_ref": {"value": "XA-CGO-2026-90", "quote": body}, "deadline": {"value": deadline.isoformat(), "quote": body}}},
                                          {"claim_type": "tender_scope", "stance": "supports", "quote": SCOPE_Q, "fields": {}}]}
    base = "https://procure.example-air.example"
    srcs.create_source(sadb, srcs.SourceSpec("Example Air procurement", "listing", base + "/rfp/", "official_portal", retention_permitted=True,
                                             enabled=True, country_coverage=["KE"]), META)
    web = Web({base + "/rfp/": _listing([base + "/rfp/1"]),
               base + "/rfp/1": _page("RFP XA-CGO-2026-90", body, published=(datetime.now(UTC) - timedelta(days=2)).isoformat())})
    sid = dsc.create_search(sadb, dsc.SearchSpec("country", ["KE"], [], []))
    started = dsc.start_run(sadb, SETTINGS, search_id=sid)
    dsc.execute_run(sadb, SETTINGS, started["run_id"], None, fetch=web, transport=model(reply))
    # evidence: the AI-proposed claim is reviewed by a person
    claims = [r[0] for r in sadb.pg.rows("SELECT id FROM claims WHERE review_status <> 'confirmed'")]
    assert len(claims) == 2, sadb.pg.rows("SELECT claim_type, review_status FROM claims")
    for claim in claims:
        rev.confirm_claim(sadb, claim, "checked against the RFP page", META)
    opp = sadb.pg.val("SELECT o.id FROM opportunities o JOIN signals s ON s.id = o.signal_id WHERE s.tender_ref = 'XA-CGO-2026-90'")
    row = sadb.pg.rows(f"SELECT tender_status, freight_scope, module FROM opportunities WHERE id = '{opp}'")[0]
    assert row == ["open", "cargo", "airline_representation"]
    # qualification: scope from the capability register; eligibility settled by a recorded commercial judgement
    company = sadb.pg.val("SELECT id FROM operating_companies WHERE name = 'WFC-KE'")
    service = sadb.pg.val("SELECT id FROM services WHERE code = 'GSSA'")
    opps.add_override(sadb, opp, "eligibility", "pass", "no eligibility criteria published; IATA accreditation held", None, META)
    status = opps.set_scope(sadb, opp, company, service, META, station_code="NBO")
    checks = dict(sadb.pg.rows(f"SELECT check_code, result FROM qualification_checks WHERE opportunity_id = '{opp}'"))
    assert status == "ready_for_review", sadb.pg.rows(f"SELECT check_code, result, rationale FROM qualification_checks WHERE opportunity_id = '{opp}' AND result <> 'pass'")
    assert checks["capability"] == "pass" and checks["not_expired"] == "pass" and checks["freight_relevance"] == "pass"
    assert checks["evidence_reviewed"] == "pass"
    assert opps.approve(sadb, opp, "within mandate; pursue", META) == "approved_for_pursuit"
    for stage in ("reviewing", "qualified", "pursuing"):
        opps.change_stage(sadb, opp, stage, stage, META)
    # pipeline: the opportunity is live, cargo, in pursuit, with four separate prioritisation dimensions
    assert sadb.pg.val(f"SELECT commercial_stage FROM opportunities WHERE id = '{opp}'") == "pursuing"
    dims = dict(sadb.pg.rows(f"SELECT dimension, status FROM assessments WHERE opportunity_id = '{opp}'"))
    assert set(dims) == {"attractiveness", "evidence_confidence", "readiness", "risk"}
    hist = [r[0] for r in sadb.pg.rows(f"SELECT to_value FROM opportunity_status_history WHERE opportunity_id = '{opp}' "
                                       "AND field = 'commercial_stage' ORDER BY id")]
    assert hist == ["reviewing", "qualified", "pursuing"]


# ------------------------------------------------------------------ 2. account growth
def test_2_account_growth_mandate_to_expansion_with_rights_and_capability(sadb):  # noqa: F811
    seed(sadb)
    ag = mod.account_growth(sadb, on=AS_OF)
    got = {(c["airline"], c["territory"]): c for c in ag["candidates"]}
    # independent: XA holds GSSA in KE (and RW); WFC-KE has verified GSSA at EBB (UG, valid) and DAR (TZ, expired 2026-01-01)
    assert set(got) == {("Example Air", "UG"), ("Example Air", "TZ"), ("Sample Airways", "UG"), ("Sample Airways", "TZ")}
    assert got[("Example Air", "UG")]["actionable"] and got[("Example Air", "UG")]["station"] == "EBB"
    assert got[("Example Air", "UG")]["rank"] == 1 and got[("Example Air", "UG")]["rank_reason"].startswith("actionable; 0 blocker(s)")
    assert not got[("Example Air", "TZ")]["actionable"]                         # capability expired: blocked, not a recommendation
    assert any("expired" in b or "valid" in b for b in got[("Example Air", "TZ")]["blockers"] + got[("Example Air", "TZ")]["unknowns"])
    assert not got[("Sample Airways", "UG")]["actionable"]                      # contract prohibits extension
    assert any("prohibit" in b for b in got[("Sample Airways", "UG")]["blockers"])
    # airline bookings are evidence on the candidate: every booking above is with XA
    assert got[("Example Air", "UG")]["airline_bookings"] == len(BOOKINGS)
    # the actionable candidate becomes an opportunity with contractual-rights and capability checks
    res = mod.opportunity_from_account_growth(sadb, got[("Example Air", "UG")]["key"], META)
    checks = dict(sadb.pg.rows(f"SELECT check_code, result FROM qualification_checks WHERE opportunity_id = '{res['opportunity_id']}'"))
    assert checks["appointment_rights"] == "pass" and checks["capability"] == "pass" and checks["territory_conflict"] == "pass"
    factors = json.loads(sadb.pg.val(f"SELECT factors::text FROM assessments WHERE opportunity_id = '{res['opportunity_id']}' "
                                     "AND dimension = 'attractiveness'"))
    assert any("booking(s) with this airline" in json.dumps(f) for f in factors)


# ------------------------------------------------------------------ 3. forwarder sales
def test_3_forwarder_sales_bookings_and_quotes_to_prioritised_recommendation(sadb):  # noqa: F811
    seed(sadb)
    fs = mod.forwarder_sales(sadb, as_of=AS_OF)
    acc = {a["forwarder"]: a for a in fs["accounts"]}
    a = acc["Alpha Forwarding"]
    # independent: Sep 2026 vs Aug 2026 and vs Sep 2025
    cur, prev, ya = kg("Alpha Forwarding", start=date(2026, 9, 1), end=date(2026, 9, 30)), \
        kg("Alpha Forwarding", start=date(2026, 8, 1), end=date(2026, 8, 30)), kg("Alpha Forwarding", start=date(2025, 9, 1), end=date(2025, 9, 30))
    assert (cur, prev, ya) == (1200, 1500, 2000)
    assert Decimal(a["comparison"]["change_vs_previous"]) == (Decimal(cur - prev) / prev).quantize(Decimal("0.0001"))
    assert Decimal(a["comparison"]["change_vs_year_ago"]) == (Decimal(cur - ya) / ya).quantize(Decimal("0.0001"))
    assert any(r.startswith("declining") for r in a["review_reasons"]) and not a["dormant"]
    won, lost = sum(1 for f, s, _ in QUOTES if f == "Alpha Forwarding" and s == "won"), sum(1 for f, s, _ in QUOTES if f == "Alpha Forwarding" and s == "lost")
    assert a["decided_quotes"] == won + lost == 6 and Decimal(a["conversion"]) == (Decimal(won) / (won + lost)).quantize(Decimal("0.0001"))
    assert a["lost_on_price"] == 3
    b = acc["Bravo Cargo"]
    assert b["dormant"] and (AS_OF - date(2026, 6, 1)).days > 90 and b["bookings_12m"] == 1
    c = acc["Charlie Logistics"]
    assert Decimal(c["conversion"]) == Decimal("0.1000") and any("low quote conversion 10%" in r for r in c["review_reasons"])
    assert not any(r.startswith("declining") for r in c["review_reasons"])         # +5% vs a year ago: not declining
    # prioritised order: needs review, dormant first, then 12-month volume, then name
    order = [x["forwarder"] for x in fs["accounts"] if x["needs_review"]]
    assert order[:3] == ["Bravo Cargo", "Alpha Forwarding", "Charlie Logistics"], order
    assert [acc[f]["rank"] for f in order[:3]] == [1, 2, 3] and all("provisional" in acc[f]["rank_reason"] for f in order[:3])
    assert "dormant" in acc["Bravo Cargo"]["rank_reason"] and acc["Bravo Cargo"]["missing"] == ["quote conversion: no decided quotes in 90 days"]
    # recommendation -> opportunity with explained factors
    opp = mod.opportunity_from_forwarder(sadb, a["key"], META)["opportunity_id"]
    att = json.loads(sadb.pg.val(f"SELECT factors::text FROM assessments WHERE opportunity_id = '{opp}' AND dimension = 'attractiveness'"))
    assert any("vs comparison period" in json.dumps(f) or "booking(s) in the previous 12 months" in json.dumps(f) for f in att)
    risk = json.loads(sadb.pg.val(f"SELECT factors::text FROM assessments WHERE opportunity_id = '{opp}' AND dimension = 'risk'"))
    assert any("3 of 6 decided quote(s) lost on price" in json.dumps(f) for f in risk)


# ------------------------------------------------------------------ 4. capacity and trade lanes
def test_4_capacity_and_lanes_utilisation_yield_and_sourced_recommendation(sadb):  # noqa: F811
    seed(sadb)
    cl = mod.capacity_lanes(sadb, *SEP)
    lanes = {x["lane"]: x for x in cl["lanes"]}
    out = lanes["DXB→NBO"]
    booked = kg(origin="DXB", destination="NBO", start=SEP[0], end=SEP[1])
    prev = kg(origin="DXB", destination="NBO", start=date(2026, 8, 2), end=date(2026, 8, 31))
    assert booked == 9050 and prev == 7500
    assert Decimal(out["utilisation"]["value"]) == (Decimal(booked) / 10000).quantize(Decimal("0.0001"))
    assert out["trend"] == (Decimal(booked - prev) / prev).quantize(Decimal("0.0001"))
    assert out["yield_per_kg"]["USD"] == (Decimal(revenue("DXB", "NBO", *SEP)) / booked).quantize(Decimal("0.0001"))
    r = out["recommendation"]
    assert r["kind"] == "add_capacity" and r["strength"] == "strong" and r["provisional"]
    assert {s["dataset"] for s in r["sources"]} >= {"bookings", "capacity"} and any("10000" in s.get("snapshot", "") for s in r["sources"])
    back = lanes["NBO→DXB"]["recommendation"]
    assert back["kind"] == "review_allotment"
    assert Decimal(back["inputs"]["utilisation"]) == Decimal("0.2500") and Decimal(back["inputs"]["trend"]) == (Decimal(2000 - 3000) / 3000).quantize(Decimal("0.0001"))
    gap = lanes["DXB→EBB"]["recommendation"]
    assert gap["action"] is None and gap["kind"] == "insufficient_data" and any("utilisation" in m for m in gap["missing"])
    assert [x["lane"] for x in cl["recommendations"]] == ["DXB→NBO", "NBO→DXB"]
    # recommendation -> opportunity scored with the capacity model (spare capacity 9.5% -> anchor 2; trend +20.67% -> 3)
    opp = mod.opportunity_from_capacity(sadb, r["key"], *SEP, META)["opportunity_id"]
    att = json.loads(sadb.pg.val(f"SELECT factors::text FROM assessments WHERE opportunity_id = '{opp}' AND dimension = 'attractiveness'"))
    vals = {f["code"]: f["value"] for f in att}
    assert vals["spare_capacity"] == 2 and vals["booking_trend"] == 3


# ------------------------------------------------------------------ 5. service and operations
def test_5_service_and_operations_exception_to_resolution_with_history(sadb):  # noqa: F811
    seed(sadb)
    load(sadb, "exceptions", "external_id,exception_type,severity,booking_ref,customer,operating_company,description,deadline,status\n"
                             "EX-1,reservation,high,A3,Alpha Forwarding,WFC-UAE,Reservation not confirmed for A3,2026-10-20T10:00:00Z,open\n")
    exc = sadb.pg.val("SELECT id FROM operational_exceptions WHERE external_id = 'EX-1'")
    assert sadb.pg.val(f"SELECT count(*) FROM notifications WHERE entity_id = '{exc}'") == "1"           # one alert
    assert sadb.pg.val(f"SELECT count(*) FROM tasks WHERE source_id = '{exc}'") == "1"                   # one task
    # a repeated import does not duplicate the alert or the task
    load(sadb, "exceptions", "external_id,exception_type,severity,booking_ref,customer,operating_company,description,deadline,status\n"
                             "EX-1,reservation,high,A3,Alpha Forwarding,WFC-UAE,Reservation not confirmed for A3,2026-10-20T10:00:00Z,open\n")
    assert sadb.pg.val(f"SELECT count(*) FROM tasks WHERE source_id = '{exc}'") == "1"
    person = sadb.pg.val("SELECT id FROM people")
    mod.assign_exception_owner(sadb, exc, person, META)
    mod.acknowledge_exception(sadb, exc, "airline contacted", META)
    assert ops_service.resolve(sadb, exc, "booking confirmed by the airline", META)
    hist = [r[0] for r in sadb.pg.rows(f"SELECT to_status FROM operational_exception_history WHERE exception_id = '{exc}' ORDER BY id")]
    assert hist == ["open", "owner_changed", "acknowledged", "resolved"]
    assert sadb.pg.val(f"SELECT status FROM tasks WHERE source_id = '{exc}'") != "open"
    assert sadb.pg.val(f"SELECT resolved_at IS NOT NULL FROM operational_exceptions WHERE id = '{exc}'") == "t"


# ------------------------------------------------------------------ 6. trucking and gateways
def test_6_trucking_station_and_connections_to_coverage_recommendation(sadb):  # noqa: F811
    seed(sadb)
    tg = mod.trucking_gateways(sadb, SHIP)
    st = {s["station"]: s for s in tg["stations"]}
    # independent: T-1 leaves NYK1 Monday 06:00 + 240 min = 10:00 at NBO; XA720 departs 23:50 with a 180-min cutoff (20:50): feasible
    assert datetime(2026, 10, 19, 6, 0) + timedelta(minutes=240) <= datetime(2026, 10, 19, 23, 50) - timedelta(minutes=180)
    nyk = st["NYK1"]["recommendation"]
    assert nyk["kind"] == "coverage_available" and nyk["best_option"]["connection"] == "XA720"
    assert any("XA722" in m for m in nyk["missing"])                   # unknown cutoff: unresolved, never feasible
    assert st["MSA1"]["recommendation"]["kind"] == "coverage_gap"          # feeder runs on Sundays only
    assert st["KSM1"]["recommendation"]["kind"] == "coverage_gap" and "no road feeder" in st["KSM1"]["recommendation"]["why"]
    opp = mod.opportunity_from_trucking(sadb, nyk["key"], SHIP, META)["opportunity_id"]
    assert dict(sadb.pg.rows(f"SELECT check_code, result FROM qualification_checks WHERE opportunity_id = '{opp}'"))["feasibility"] == "pass"


# ------------------------------------------------------------------ 7. outsourcing and training
def test_7_outsourcing_verified_demand_to_qualified_match_and_non_live_records_excluded(sadb):  # noqa: F811
    seed(sadb)
    load(sadb, "training_credentials", "external_id,operating_company,credential_type,issued_on,expires_on\nCR-1,WFC-KE,IATA_DGR_INSTRUCTOR,2025-01-01,2028-01-01\n")
    load(sadb, "service_requirements", "service_code,credential_type\nTRAINING,IATA_DGR_INSTRUCTOR\n")
    sid = srcs.create_source(sadb, srcs.SourceSpec("Sample Airways procurement", "web_page", "https://procure.sample-airways.example/",
                                                   "official_portal", retention_permitted=True, enabled=True), META)
    src = ing.SourceInfo(sid, "procure", "official_portal", "https://procure.sample-airways.example/", True)
    nxt = datetime.now(UTC).date() + timedelta(days=30)
    live = (f"Sample Airways invites proposals for cargo dangerous goods training in Uganda. Reference SAW-TRN-2027-01. "
            f"Proposals must be submitted by {nxt.day} {nxt.strftime('%B %Y')}.")
    q = "Sample Airways invites proposals for cargo dangerous goods training in Uganda. Reference SAW-TRN-2027-01."
    ing.ingest(sadb, ing.IncomingDocument(src, "https://procure.sample-airways.example/t1", "https://procure.sample-airways.example/t1", live,
                                          published_at=datetime.now(UTC) - timedelta(days=1)),
               [ing.ClaimProposal("service_tender", q, {"airline": F("Sample Airways", q), "country": F("Uganda", q), "service": F("TRAINING", q),
                                                        "status": F("open", q), "tender_ref": F("SAW-TRN-2027-01", q)}, assessed_by="human")])
    gone = "Tender SAW-TRN-2026-07 for cargo training in Uganda, issued by Sample Airways, has been cancelled."
    old = "Sample Airways invites proposals for cargo training in Uganda. Reference SAW-TRN-2026-07."
    ing.ingest(sadb, ing.IncomingDocument(src, "https://procure.sample-airways.example/t0", "https://procure.sample-airways.example/t0", old,
                                          published_at=datetime.now(UTC) - timedelta(days=60)),
               [ing.ClaimProposal("service_tender", old, {"airline": F("Sample Airways", old), "country": F("Uganda", old), "service": F("TRAINING", old),
                                                          "status": F("open", old), "tender_ref": F("SAW-TRN-2026-07", old)}, assessed_by="human")])
    ing.ingest(sadb, ing.IncomingDocument(src, "https://procure.sample-airways.example/t0c", "https://procure.sample-airways.example/t0c", gone,
                                          published_at=datetime.now(UTC) - timedelta(days=10)),
               [ing.ClaimProposal("tender_status", gone, {"airline": F("Sample Airways", gone), "tender_ref": F("SAW-TRN-2026-07", gone),
                                                          "status": F("cancelled", gone)}, assessed_by="human")])
    ot = mod.outsourcing_training(sadb)
    demand = {d["title"]: d for d in ot["demand"]}
    live_d = next(d for t, d in demand.items() if "SAW-TRN-2027-01" in t)
    assert live_d["rank"] == 1 and "best match WFC-KE ready" in live_d["rank_reason"] and live_d["missing"] == ["deadline"]   # the claim states no deadline field
    assert live_d["countries"] == ["UG"] and live_d["matches"][0]["operating_company"] == "WFC-KE" and live_d["matches"][0]["readiness"] == "ready"
    assert not any("SAW-TRN-2026-07" in t for t in demand)                   # cancelled: never live demand
    assert any("SAW-TRN-2026-07" in n["title"] and "cancelled" in n["why"] for n in ot["not_live"])


# ------------------------------------------------------------------ 8. technology and solutions
def test_8_technology_linked_events_to_evidence_backed_solution(sadb):  # noqa: F811
    seed(sadb)
    tech = mod.technology_solutions(sadb, *SEP)
    sol = {s["key"].split("|")[1] + "|" + s["key"].split("|")[2]: s for s in tech["solutions"]}
    fr = sol["funnel|portal"]
    # independent: 6 linked quote-request sessions, 1 booked -> 16.67% < 20%
    assert fr["kind"] == "booking_friction" and fr["evidence"]["quote_requests"] == 6 and fr["evidence"]["booked"] == 1
    assert Decimal(fr["evidence"]["booking_rate"]) == (Decimal(1) / 6).quantize(Decimal("0.0001"))
    assert sol["integration|api"]["evidence"]["integration_failures"] == 3
    assert sol["funnel|api"]["kind"] == "insufficient_data" and sol["funnel|api"]["action"] is None   # no linked funnel events on api
    adoption = {s["forwarder"] for s in tech["solutions"] if s["kind"] == "digital_adoption"}
    # independent: forwarders with bookings in September and no channel events
    expect = {f for _i, f, _o, _d, fd, _k, _r in BOOKINGS if SEP[0] <= fd <= SEP[1]} - {"Alpha Forwarding"}
    assert adoption == expect
    assert any(s["kind"] == "combined_service" and s["forwarder"] == "Alpha Forwarding" for s in tech["solutions"])
    assert [s["rank"] for s in tech["solutions"]] == list(range(1, len(tech["solutions"]) + 1))
    opp = mod.opportunity_from_solution(sadb, fr["key"], *SEP, META)["opportunity_id"]
    assert sadb.pg.val(f"SELECT module FROM opportunities WHERE id = '{opp}'") == "technology_solutions"


# ------------------------------------------------------------------ 9. network development
def test_9_network_development_gap_to_reviewable_recommendation(sadb):  # noqa: F811
    seed(sadb)
    nd = mod.network_development(sadb, on=AS_OF)
    gaps = {(g["territory"], g["service"]): g for g in nd["coverage_gaps"]}
    # independent: AG-1 covers KE and RW for GSSA; WFC-KE holds verified GSSA at NBO (KE) only within KE/RW -> RW is a gap
    assert set(gaps) == {("RW", "GSSA")} and gaps[("RW", "GSSA")]["airlines"] == ["Example Air"]
    cand = mod.network_gap_candidate(sadb, gaps[("RW", "GSSA")]["key"], META)["id"]
    partner = sadb.pg.val("INSERT INTO organisations (canonical_name, kind, country) VALUES ('Kigali Cargo Partners', 'other', 'RW') RETURNING id")
    fit = fit_service.assess(sadb, cand, partner, [("RW", "GSSA")], META)
    assert fit["result"] == "insufficient_evidence"                          # no supported partner claims: an explicit gap
    research = sadb.pg.val("INSERT INTO network_candidates (kind, title) VALUES ('acquisition_research', 'Research: Rwanda handling agents') RETURNING id")
    nd2 = mod.network_development(sadb, on=AS_OF)
    by_id = {str(c["id"]): c for c in nd2["candidates"]}
    assert by_id[str(cand)]["rank"] == 1 and "fit insufficient_evidence" in by_id[str(cand)]["rank_reason"]
    assert by_id[str(research)]["rank"] is None and "never ranked or valued" in by_id[str(research)]["rank_reason"]
    assert nd2["coverage_gaps"][0]["candidate_id"] == str(cand)


# ------------------------------------------------------------------ missing data: explicit gaps, never zeros
def test_missing_data_gives_explicit_gaps_never_zero_or_confident_recommendations(sadb):  # noqa: F811
    for res in (mod.capacity_lanes(sadb, *SEP), mod.trucking_gateways(sadb, SHIP), mod.technology_solutions(sadb, *SEP),
                mod.network_development(sadb, on=AS_OF)):
        assert res["status"] == "not_connected" and any("not connected" in g for g in res["gaps"])
        assert not res.get("recommendations") and not res.get("solutions") and not res.get("coverage_gaps")
    # bookings without capacity: no utilisation, no recommendation, the gap is stated
    load(sadb, "airports", "iata_code,name,country,timezone\nDXB,Dubai International,AE,Asia/Dubai\nNBO,Jomo Kenyatta International,KE,Africa/Nairobi\n")
    load(sadb, "bookings", "external_id,origin,destination,flight_date,booked_at,status,chargeable_weight\n"
                           "Z1,DXB,NBO,2026-09-10,2026-09-01T08:00:00Z,confirmed,100\n")
    cl = mod.capacity_lanes(sadb, *SEP)
    lane = next(x for x in cl["lanes"] if x["lane"] == "DXB→NBO")
    assert lane["recommendation"]["action"] is None and lane["yield_per_kg"] is None
    assert any("capacity: not connected" in g for g in cl["gaps"])
