"""Directive §9 (all nine capability areas have a usable workflow and a
meaningful output), §11 (prioritisation for every module) and acceptance
test 11 (missing feeds show "not connected", never zero). Every input is
loaded through the import workflow; nothing is hand-inserted."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from app.domain.prioritisation import RULES, SCORED, definitions
from app.domain.field_validation import FieldClaim as F
from app.services import imports_service as imp
from app.services import ingestion as ing
from app.services import sources_service as srcs
from app.services import modules_service as mod
from app.services import opportunity_service as opps
from app.services.audit import RequestMeta

META = RequestMeta(ip="203.0.113.10", request_id="req-m", session_ref="sessmodules01")
TODAY = date.today()
M0 = TODAY.replace(day=1)
PREV = (M0 - timedelta(days=1)).replace(day=1)          # previous calendar month
YA = PREV.replace(year=PREV.year - 1)                   # same month last year
NEXT_MONDAY = TODAY + timedelta(days=(7 - TODAY.weekday()) % 7 or 7)


def load(db, ds, text):
    r = imp.import_file(db, ds, f"{ds}.csv", text.encode(), None, META)
    assert r["reconciliation"]["rows_quarantined"] == 0, (ds, r["errors"])
    return r


def seed(db):
    load(db, "operating_companies", "name,country\nWFC-UAE,AE\nWFC-KE,KE\n")
    load(db, "airports", "iata_code,name,country,timezone\nDXB,Dubai International,AE,Asia/Dubai\nNBO,Jomo Kenyatta International,KE,Africa/Nairobi\n"
                         "EBB,Entebbe International,UG,Africa/Kampala\n")
    load(db, "airlines", "iata_code,name,country\nXA,Example Air,AE\n")
    load(db, "stations", "code,name,is_offline,country,timezone\nNYK1,Nanyuki offline point,yes,KE,Africa/Nairobi\n")
    load(db, "agreements", "external_id,airline_iata,airline_name,operating_company,territories,services,effective_from,effective_to,"
                           "exclusivity,appointment_rights\nAG-1,XA,Example Air,WFC-KE,KE,GSSA,2025-01-01,2028-12-31,exclusive,may_extend\n")
    load(db, "capabilities", "operating_company,service_code,station,status,valid_from,valid_to\n"
                             "WFC-KE,GSSA,NBO,verified,2025-01-01,2028-12-31\nWFC-KE,GSSA,EBB,verified,2025-01-01,2028-12-31\n"
                             "WFC-KE,TRAINING,,verified,2025-01-01,2028-12-31\n")
    b = "external_id,forwarder,airline_iata,origin,destination,flight_date,booked_at,status,chargeable_weight,revenue,currency,operating_company\n"
    rows = []
    for i, (fwd, d, kg) in enumerate([("Forwarder A", YA + timedelta(days=3), 1000), ("Forwarder A", PREV + timedelta(days=3), 400),
                                      ("Forwarder B", TODAY - timedelta(days=200), 900), ("Forwarder A", M0 - timedelta(days=40), 1000)]):
        rows.append(f"BK-{i},{fwd},XA,DXB,NBO,{d},{d}T08:00:00Z,confirmed,{kg},{kg * 2}.00,USD,WFC-UAE")
    load(db, "bookings", b + "\n".join(rows) + "\n")
    load(db, "quotes", "external_id,forwarder,origin,destination,quoted_at,status,lost_reason,amount,currency\n" + "\n".join(
        f"Q-{i},Forwarder A,DXB,NBO,{TODAY - timedelta(days=10)}T08:00:00Z,{'won' if i == 0 else 'lost'},{'price' if i else ''},100.00,USD"
        for i in range(6)) + "\n")
    load(db, "capacity", "external_id,airline_iata,origin,destination,period_start,period_end,basis,capacity_type,amount,snapshot_at\n"
                         f"C-1,XA,DXB,NBO,{YA},{YA + timedelta(days=27)},weight_kg,bookable,5000,{YA}T00:00:00Z\n"
                         f"C-2,XA,DXB,NBO,{PREV},{PREV + timedelta(days=27)},weight_kg,bookable,6000,{PREV}T00:00:00Z\n")
    load(db, "trucking", "external_id,provider,origin_station,gateway,departure_days,departure_time,transit_minutes\n"
                         "T-1,Rift Valley Haulage,NYK1,NBO,1;3;5,06:00,240\n")
    load(db, "gateway_connections", "external_id,gateway,destination,airline_iata,flight_number,departure_days,departure_time,connection_cutoff_minutes\n"
                                    "G-1,NBO,DXB,XA,XA720,1;3;5,23:50,180\nG-2,NBO,DXB,XA,XA722,1;3;5,08:00,\n")
    load(db, "channel_events", "external_id,event_type,session_key,booking_ref,channel,occurred_at,forwarder\n"
                               f"E-1,quote_request,S1,,portal,{PREV + timedelta(days=1)}T08:00:00Z,Forwarder A\n"
                               f"E-2,quote,S1,BK-1,portal,{PREV + timedelta(days=1)}T08:05:00Z,Forwarder A\n"
                               f"E-3,booking,S1,BK-1,portal,{PREV + timedelta(days=1)}T08:09:00Z,Forwarder A\n")
    load(db, "exceptions", "external_id,exception_type,severity,booking_ref,customer,operating_company,description,deadline,status\n"
                           f"EX-1,reservation,high,BK-1,Forwarder A,WFC-UAE,Reservation not confirmed,{TODAY + timedelta(days=1)}T10:00:00Z,open\n")
    load(db, "contacts", "external_id,full_name,role_title,operating_company,is_internal\nP-1,Ops lead Nairobi,Operations,WFC-KE,yes\n")


def test_missing_feeds_show_not_connected_never_zero(sadb):
    """Acceptance 11."""
    for res in (mod.account_growth(sadb), mod.forwarder_sales(sadb), mod.capacity_lanes(sadb, PREV, M0 - timedelta(days=1)),
                mod.trucking_gateways(sadb, NEXT_MONDAY), mod.outsourcing_training(sadb), mod.technology_solutions(sadb, PREV, TODAY)):
        assert res["status"] == "not_connected", res
        assert any("not connected" in g for g in res["gaps"])
        rows = [v for k, v in res.items() if isinstance(v, list) and k not in ("sources", "gaps")]
        assert all(r == [] for r in rows)                                  # no zero-filled rows


def test_every_area_produces_meaningful_output(sadb):
    seed(sadb)
    ag = mod.account_growth(sadb)
    assert ag["status"] == "ok"
    cand = next(c for c in ag["candidates"] if c["territory"] == "UG")
    assert (cand["service"], cand["operating_company"], cand["station"], cand["actionable"]) == ("GSSA", "WFC-KE", "EBB", True)

    fs = mod.forwarder_sales(sadb)
    a = next(r for r in fs["accounts"] if r["forwarder"] == "Forwarder A")
    b = next(r for r in fs["accounts"] if r["forwarder"] == "Forwarder B")
    assert b["dormant"] and b["needs_review"]
    assert any(r.startswith("declining") for r in a["review_reasons"]), a
    assert a["conversion"] is not None and float(a["conversion"]) < 0.25 and a["lost_on_price"] == 5

    cl = mod.capacity_lanes(sadb, PREV, M0 - timedelta(days=1))
    lane = next(r for r in cl["lanes"] if r["lane"] == "DXB→NBO")
    assert lane["capacity_changes"][0]["change"] is not None and lane["yield_per_kg"]["USD"] is not None
    rev_lane = next(r for r in cl["lanes"] if r["lane"] == "NBO→DXB")       # directional: the reverse lane is separate
    assert rev_lane["bookings"] == 0 and rev_lane["chargeable_kg"] is None     # no bookings => unknown weight, not 0 kg

    tg = mod.trucking_gateways(sadb, NEXT_MONDAY)
    st = tg["stations"][0]
    assert st["station"] == "NYK1" and st["feasible"] == 1 and st["unresolved"] == 1   # unknown cutoff is never "feasible"

    tech = mod.technology_solutions(sadb, PREV, M0 - timedelta(days=1))
    gaps = {r["forwarder"]: r["adoption_gap"] for r in tech["adoption"]}
    assert gaps.get("Forwarder A") is False
    assert tech["funnels"][0]["status"] == "computed" and tech["combined"][0]["forwarder"] == "Forwarder A"

    # Outsourcing and training: verified demand (a supported tender) matched to capability and credentials.
    sid = srcs.create_source(sadb, srcs.SourceSpec("Sample Airways procurement", "web_page", "https://procure.sample-airways.example/",
                                                   "official_portal", retention_permitted=True, enabled=True), META)
    text = ("Sample Airways invites proposals for cargo staff training in Uganda. Reference SAW-TRN-2027-01. "
            f"Proposals must be submitted by {NEXT_MONDAY.day} {NEXT_MONDAY.strftime('%B %Y')} at 12:00 EAT.")
    q = "Sample Airways invites proposals for cargo staff training in Uganda."
    ing.ingest(sadb, ing.IncomingDocument(ing.SourceInfo(sid, "procure", "official_portal", "https://procure.sample-airways.example/", True),
                                          "https://procure.sample-airways.example/t1", "https://procure.sample-airways.example/t1", text,
                                          published_at=datetime.now(timezone.utc) - timedelta(days=1)),
               [ing.ClaimProposal("service_tender", q, {"airline": F("Sample Airways", q), "country": F("Uganda", q),
                                                        "service": F("TRAINING", q), "status": F("open", q)}, assessed_by="human")])
    ot = mod.outsourcing_training(sadb)
    assert ot["demand"], ot["not_live"]
    demand = next(d for d in ot["demand"] if d["service"] == "TRAINING")
    assert demand["countries"] == ["UG"] and demand["matches"][0]["operating_company"] == "WFC-KE"
    assert demand["matches"][0]["readiness"] == "ready"

    # Service and operations: ownership and resolution history.
    exc = sadb.pg.val("SELECT id FROM operational_exceptions")
    person = sadb.pg.val("SELECT id FROM people")
    mod.assign_exception_owner(sadb, exc, person, META)
    mod.acknowledge_exception(sadb, exc, "investigating with the airline", META)
    assert [r[0] for r in sadb.pg.rows(f"SELECT to_status FROM operational_exception_history WHERE exception_id='{exc}' ORDER BY id")] == \
        ["open", "owner_changed", "acknowledged"]
    assert sadb.pg.val("SELECT owner_person_id IS NOT NULL FROM tasks WHERE source_type='operational_exception'") == "t"


def test_module_opportunities_are_qualified_and_prioritised(sadb):
    seed(sadb)
    key = next(c["key"] for c in mod.account_growth(sadb)["candidates"] if c["territory"] == "UG")
    res = mod.opportunity_from_account_growth(sadb, key, META)
    opp = res["opportunity_id"]
    checks = dict(sadb.pg.rows(f"SELECT check_code, result FROM qualification_checks WHERE opportunity_id='{opp}'"))
    assert checks["existence"] == "pass" and checks["appointment_rights"] == "pass" and checks["capability"] == "pass"
    assert sadb.pg.val(f"SELECT count(*) FROM opportunity_geography WHERE opportunity_id='{opp}' AND support='internal_record'") == "1"
    dims = dict(sadb.pg.rows(f"SELECT dimension, status FROM assessments WHERE opportunity_id='{opp}'"))
    assert set(dims) == {"attractiveness", "evidence_confidence", "readiness", "risk"}
    assert sadb.pg.val(f"SELECT version FROM assessments a JOIN scoring_model_versions m ON m.id=a.model_version_id WHERE a.opportunity_id='{opp}' LIMIT 1") == "wfc-ag-0.1"
    # A second request for the same record is refused, not duplicated.
    try:
        mod.opportunity_from_account_growth(sadb, key, META)
        raise AssertionError("duplicate created")
    except mod.ModuleRejected as e:
        assert e.status == 409
    fwd_key = next(a["key"] for a in mod.forwarder_sales(sadb)["accounts"] if a["forwarder"] == "Forwarder A")
    fo = mod.opportunity_from_forwarder(sadb, fwd_key, META)["opportunity_id"]
    assert sadb.pg.val(f"SELECT status FROM assessments WHERE opportunity_id='{fo}' AND dimension='attractiveness'") in ("scored", "insufficient_evidence")
    opps.assign_owner(sadb, fo, sadb.pg.val("SELECT id FROM people"), META)
    # Every module has a documented prioritisation: scored (provisional) or transparent rules.
    mods = {d["module"]: d for d in definitions()}
    assert set(mods) == {"airline_representation", "account_growth", "forwarder_sales", "capacity_lanes", "service_operations",
                         "trucking_gateways", "outsourcing_training", "technology_solutions", "network_development"}
    assert all(d["provisional"] for d in mods.values())
    assert set(RULES) == {"service_operations", "network_development"} and len(SCORED) == 7
