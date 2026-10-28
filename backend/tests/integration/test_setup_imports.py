"""Directive §10 and acceptance 10: a fresh installation is set up entirely
through imports (no hand-inserted database rows), commits are bound to the
reviewed preview, changes between preview and commit are detected, partial
imports are disclosed, and the remaining datasets (trucking, finance,
digital-channel events, training credentials, gateway connections) commit,
re-run idempotently and reverse. Real PostgreSQL, production adapter."""
from __future__ import annotations

import pytest

from app.services import imports_service as imp
from app.services.audit import RequestMeta

META = RequestMeta(ip="203.0.113.10", request_id="req-i", session_ref="sessimports01")

SETUP = {
    "operating_companies": "name,legal_entity_name,country,is_group_member\nWFC-UAE,,AE,yes\nWFC-KE,,KE,yes\n",
    "airports": ("iata_code,icao_code,name,country,timezone\nDXB,OMDB,Dubai International,AE,Asia/Dubai\n"
                 "NBO,HKJK,Jomo Kenyatta International,KE,Africa/Nairobi\nMBA,HKMO,Moi International,KE,Africa/Nairobi\n"
                 "LHR,EGLL,London Heathrow,GB,Europe/London\n"),
    "airlines": "iata_code,name,icao_code,awb_prefix,country\nXA,Example Air,,,AE\n",
    "contacts": ("external_id,full_name,role_title,organisation,operating_company,email,is_internal\n"
                 "P-1,Commercial lead Gulf,Head of Commercial,,WFC-UAE,,yes\nP-2,Cargo Director (Example Air),Cargo Director,Example Air,,,no\n"),
    "stations": "code,name,is_offline,country,timezone\nNYK1,Nanyuki offline point,yes,KE,Africa/Nairobi\n",
    "territories": "code,name,kind,country\nEAF,East Africa (WFC definition),region,\n",
    "service_requirements": "service_code,credential_type\nHANDLING,IATA_DGR\n",
}


def load(db, dataset, text, **kw):
    return imp.import_file(db, dataset, f"{dataset}.csv", text.encode(), None, META, **kw)


def test_fresh_install_is_usable_through_setup_imports(sadb):
    assert sadb.pg.val("SELECT count(*) FROM airports") == "0"
    for ds, text in SETUP.items():
        r = load(sadb, ds, text)
        assert r["reconciliation"]["rows_quarantined"] == 0, (ds, r["errors"])
    assert sadb.pg.val("SELECT count(*) FROM airports") == "4"
    assert sadb.pg.val("SELECT o.canonical_name FROM airlines a JOIN organisations o ON o.id=a.organisation_id WHERE a.iata_code='XA'") == "Example Air"
    assert sadb.pg.val("SELECT count(*) FROM people WHERE is_internal") == "1"
    assert sadb.pg.val("SELECT count(*) FROM service_credential_requirements") == "1"
    # Re-running every setup file is idempotent.
    for ds, text in SETUP.items():
        r = load(sadb, ds, text)
        assert (r["reconciliation"]["inserted"], r["reconciliation"]["updated"]) == (0, 0), ds
    # Bookings now import without any hand-inserted reference rows (the e2e DXB/NBO gap).
    b = ("external_id,forwarder,airline_iata,origin,destination,flight_date,booked_at,status,chargeable_weight,revenue,currency,operating_company\n"
         "BK-1,Forwarder A,XA,DXB,NBO,2026-10-05,2026-10-01T09:00:00+04:00,confirmed,1000,2500.00,USD,WFC-UAE\n")
    assert load(sadb, "bookings", b)["reconciliation"]["inserted"] == 1


def test_commit_is_bound_to_the_reviewed_preview(sadb):
    for ds in ("operating_companies", "airports", "airlines"):
        load(sadb, ds, SETUP[ds])
    head = "external_id,origin,destination,booked_at,status,chargeable_weight,operating_company\n"
    f = head + "BK-1,DXB,NBO,2026-10-01T09:00:00Z,confirmed,100,WFC-UAE\nBK-2,DXB,NBO,2026-10-01T09:00:00Z,confirmed,50,WFC-NOPE\n"
    pre = imp.dry_run(sadb, "bookings", "b.csv", f.encode(), None, META)
    assert pre["planned"] == {"insert": 1, "update": 0, "unchanged": 0} and pre["preview"][0]["key"] == "BK-1"
    assert sadb.pg.val("SELECT count(*) FROM bookings") == "0"                        # preview writes nothing
    # Someone else's import changes BK-1 between preview and commit: the reviewed plan is stale.
    other = imp.import_file(sadb, "bookings", "other.csv", (head + "BK-1,DXB,NBO,2026-10-01T09:00:00Z,confirmed,999,WFC-UAE\n").encode(), None, META)
    assert other["reconciliation"]["inserted"] == 1
    with pytest.raises(imp.ImportRejected) as e:
        imp.commit(sadb, pre["job_id"], META)
    assert e.value.status == 409 and "changed since this preview" in e.value.detail
    pre2 = imp.dry_run(sadb, "bookings", "b.csv", f.encode(), None, META)
    res = imp.commit(sadb, pre2["job_id"], META)
    assert res["partial"] and "1 row(s) quarantined" in res["partial_note"]          # partial import disclosed
    assert sadb.pg.val(f"SELECT partial FROM import_jobs WHERE id='{res['job_id']}'") == "t"
    with pytest.raises(imp.ImportRejected) as e:
        imp.commit(sadb, pre2["job_id"], META)                                       # a preview commits once
    assert e.value.status == 409


def test_remaining_datasets_commit_rerun_and_reverse(sadb):
    for ds in ("operating_companies", "airports", "airlines", "stations"):
        load(sadb, ds, SETUP[ds])
    data = {
        "trucking": ("external_id,provider,origin_station,gateway,departure_days,departure_time,transit_minutes,restrictions\n"
                     "T-1,Rift Valley Haulage,NYK1,NBO,1;3;5,06:00,240,No DG\nT-2,Rift Valley Haulage,NOPE,NBO,2,07:00,200,\n"),
        "finance": ("operating_company,period_start,period_end,metric,amount,currency,basis\n"
                    "WFC-UAE,2026-09-01,2026-09-30,gssa_commission,120000.50,USD,month-end pack\n"),
        "channel_events": ("external_id,event_type,session_key,booking_ref,channel,occurred_at,forwarder\n"
                           "E-1,search,S1,,portal,2026-10-01T08:00:00Z,Forwarder A\nE-2,booking,S1,BK-1,portal,2026-10-01T08:05:00Z,Forwarder A\n"),
        "training_credentials": ("external_id,operating_company,credential_type,service_code,station,holder_description,issued_on,expires_on\n"
                                 "C-1,WFC-KE,IATA_DGR,HANDLING,NBO,Export team,2025-01-01,2027-01-01\n"),
        "gateway_connections": ("external_id,gateway,destination,airline_iata,flight_number,departure_days,departure_time,connection_cutoff_minutes\n"
                                "G-1,NBO,DXB,XA,XA720,1;3;5,23:50,180\n"),
    }
    for ds, text in data.items():
        r = load(sadb, ds, text)
        assert r["reconciliation"]["inserted"] >= 1, (ds, r)
        again = load(sadb, ds, text)
        assert (again["reconciliation"]["inserted"], again["reconciliation"]["updated"]) == (0, 0), (ds, again)
    assert sadb.pg.rows("SELECT array_to_string(departure_days,';'), to_char(departure_time_local,'HH24:MI'), transit_minutes "
                        "FROM road_feeder_services") == [["1;3;5", "06:00", "240"]]
    assert sadb.pg.val("SELECT count(*) FROM import_row_errors e JOIN import_jobs j ON j.id=e.import_job_id "
                       "WHERE e.field='origin_station' AND j.mode='commit'") == "2"   # quarantined on both commits, kept
    assert sadb.pg.val("SELECT count(*) FROM channel_events WHERE forwarder_id IS NOT NULL") == "2"
    # Amend then reverse a finance figure: previous value restored.
    amended = load(sadb, "finance", data["finance"].replace("120000.50", "125000.00"))
    assert amended["reconciliation"]["updated"] == 1
    imp.reverse(sadb, amended["job_id"], "month-end pack was provisional", META)
    assert sadb.pg.val("SELECT amount FROM financial_aggregates") == "120000.5000"
    # Reversal is refused when other records depend on rows the import created.
    airports_job = sadb.pg.val("SELECT id FROM import_jobs WHERE dataset='airports' AND mode='commit' ORDER BY created_at LIMIT 1")
    with pytest.raises(imp.ImportRejected) as e:
        imp.reverse(sadb, airports_job, "wrong file", META)
    assert e.value.status == 409 and sadb.pg.val("SELECT count(*) FROM airports") == "4"
    # Agreements are corrected by re-import, not reversed; the refusal says so.
    ag = load(sadb, "agreements", "external_id,airline_iata,airline_name,operating_company,territories,services\nAG-1,XA,Example Air,WFC-KE,KE,GSSA\n")
    with pytest.raises(imp.ImportRejected) as e:
        imp.reverse(sadb, ag["job_id"], "wrong", META)
    assert "corrected by importing a corrected file" in e.value.detail
