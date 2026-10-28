"""Data onboarding for every supported dataset (28 Oct 2026 instruction, item 3).

For each of the 19 contracts, on real PostgreSQL through the production import service:
upload → mapping (a renamed source column is reported unmapped, then mapped explicitly) → validation (a bad row is
quarantined with a reason) → preview (nothing written) → commit (exactly the preview) → reconciliation (rows read =
valid + quarantined; totals by currency or unit) → duplicate handling (the same file again changes nothing) →
correction (a changed value updates the existing record, never a second one) → reversal where supported (the
correction is undone, then the original import), or a refusal that names the re-import route.
"""
from __future__ import annotations

from dataclasses import dataclass

import pytest

from app.domain import imports as im
from app.services import imports_service as imp
from app.services.audit import RequestMeta
from tests.integration.sa import sadb  # noqa: F401

META = RequestMeta(ip="203.0.113.30", request_id="req-onb", session_ref="sessonboarding1")

BASE = [
    ("operating_companies", "name,country\nWFC-UAE,AE\nWFC-KE,KE\n"),
    ("airports", "iata_code,name,country,timezone\nDXB,Dubai International,AE,Asia/Dubai\nNBO,Jomo Kenyatta International,KE,Africa/Nairobi\n"),
    ("airlines", "iata_code,name,country\nXA,Example Air,AE\n"),
    ("services", "code,name,category\nTRUCKING,Road feeder trucking,trucking\n"),
    ("stations", "code,name,is_offline,country,timezone\nNYK1,Nanyuki offline point,yes,KE,Africa/Nairobi\n"),
]


@dataclass
class Case:
    header: str
    rows: tuple[str, str]
    corrected: str            # row 2 with one value changed
    bad: str                  # a row that must be quarantined
    renamed: str              # a required field whose source column has a different name
    count_sql: str
    value_sql: str            # reads the corrected value of row 2
    before: str
    after: str


CASES: dict[str, Case] = {
    "bookings": Case("external_id,origin,destination,flight_date,booked_at,status,chargeable_weight,revenue,currency",
                     ("B1,DXB,NBO,2026-09-10,2026-09-01T08:00:00Z,confirmed,100,250.00,USD",
                      "B2,DXB,NBO,2026-09-11,2026-09-01T09:00:00+04:00,confirmed,200,500.00,USD"),
                     "B2,DXB,NBO,2026-09-11,2026-09-01T09:00:00+04:00,confirmed,210,500.00,USD",
                     "B3,DXB,ZZZ,2026-09-12,2026-09-01T08:00:00Z,confirmed,50,10.00,USD", "origin",
                     "SELECT count(*) FROM bookings", "SELECT chargeable_weight_kg::numeric::text FROM bookings WHERE external_id='B2'", "200.000", "210.000"),
    "quotes": Case("external_id,forwarder,origin,destination,quoted_at,status,amount,currency",
                   ("Q1,Alpha,DXB,NBO,2026-09-01T08:00:00Z,open,100.00,USD", "Q2,Alpha,DXB,NBO,2026-09-02T08:00:00Z,open,90.00,USD"),
                   "Q2,Alpha,DXB,NBO,2026-09-02T08:00:00Z,lost,90.00,USD",
                   "Q3,Alpha,DXB,NBO,2026-09-02T08:00:00Z,maybe,90.00,USD", "forwarder",
                   "SELECT count(*) FROM quotes", "SELECT status FROM quotes WHERE external_id='Q2'", "open", "lost"),
    "agreements": Case("external_id,airline_iata,airline_name,operating_company,territories,services,appointment_rights",
                       ("AG1,XA,Example Air,WFC-KE,KE,GSSA,may_extend", "AG2,XA,Example Air,WFC-UAE,AE,GSSA,unknown"),
                       "AG2,XA,Example Air,WFC-UAE,AE,GSSA,prohibited",
                       "AG3,XA,Example Air,WFC-KE,KE,GSSA,sometimes", "territories",
                       "SELECT count(*) FROM representation_agreements",
                       "SELECT coalesce(appointment_rights,'unknown') FROM representation_agreements WHERE external_id='AG2'", "unknown", "prohibited"),
    "capabilities": Case("operating_company,service_code,station,status,valid_from,valid_to",
                         ("WFC-KE,GSSA,NBO,verified,2025-01-01,2028-12-31", "WFC-UAE,GSSA,DXB,unverified,2025-01-01,2028-12-31"),
                         "WFC-UAE,GSSA,DXB,verified,2025-01-01,2028-12-31",
                         "WFC-KE,GSSA,NBO,certain,2025-01-01,2028-12-31", "service_code",
                         "SELECT count(*) FROM capability_records",
                         "SELECT c.status FROM capability_records c JOIN airports a ON a.id=c.station_airport_id WHERE a.iata_code='DXB'", "unverified", "verified"),
    "capacity": Case("external_id,origin,destination,period_start,period_end,basis,capacity_type,amount,snapshot_at",
                     ("C1,DXB,NBO,2026-09-01,2026-09-30,weight_kg,bookable,10000,2026-08-25T00:00:00Z",
                      "C2,NBO,DXB,2026-09-01,2026-09-30,weight_kg,bookable,8000,2026-08-25T00:00:00Z"),
                     "C2,NBO,DXB,2026-09-01,2026-09-30,weight_kg,bookable,8500,2026-08-26T00:00:00Z",
                     "C3,NBO,DXB,2026-09-30,2026-09-01,weight_kg,bookable,8000,2026-08-25T00:00:00Z", "amount",
                     "SELECT count(*) FROM capacity_snapshots", "SELECT amount::numeric::text FROM capacity_snapshots WHERE external_id='C2'",
                     "8000.000", "8500.000"),
    "exceptions": Case("external_id,exception_type,severity,description,status",
                       ("X1,reservation,high,Not confirmed,open", "X2,supervision,low,Late documents,open"),
                       "X2,supervision,medium,Late documents,open",
                       "X3,reservation,extreme,Bad severity,open", "description",
                       "SELECT count(*) FROM operational_exceptions", "SELECT severity FROM operational_exceptions WHERE external_id='X2'", "low", "medium"),
    "trucking": Case("external_id,provider,origin_station,gateway,departure_days,departure_time,transit_minutes",
                     ("T1,Rift Haulage,NYK1,NBO,1;3;5,06:00,240", "T2,Rift Haulage,NYK1,NBO,2;4,07:00,250"),
                     "T2,Rift Haulage,NYK1,NBO,2;4,07:00,260",
                     "T3,Rift Haulage,NYK1,NBO,8,06:00,240", "provider",
                     "SELECT count(*) FROM road_feeder_services", "SELECT transit_minutes::text FROM road_feeder_services WHERE external_id='T2'",
                     "250", "260"),
    "finance": Case("operating_company,period_start,period_end,metric,amount,currency,basis",
                    ("WFC-UAE,2026-09-01,2026-09-30,gssa_commission,1000.00,USD,month-end", "WFC-KE,2026-09-01,2026-09-30,gssa_commission,500.00,KES,month-end"),
                    "WFC-KE,2026-09-01,2026-09-30,gssa_commission,550.00,KES,month-end",
                    "WFC-KE,2026-09-01,2026-09-30,gssa_commission,1.00,XXXX,month-end", "metric",
                    "SELECT count(*) FROM financial_aggregates", "SELECT amount::numeric(18,2)::text FROM financial_aggregates WHERE currency='KES'",
                    "500.00", "550.00"),
    "channel_events": Case("external_id,event_type,session_key,channel,occurred_at",
                           ("E1,quote_request,S1,portal,2026-09-01T08:00:00Z", "E2,quote,S1,portal,2026-09-01T08:05:00Z"),
                           "E2,booking,S1,portal,2026-09-01T08:05:00Z",
                           "E3,click,S1,portal,2026-09-01T08:05:00Z", "channel",
                           "SELECT count(*) FROM channel_events", "SELECT event_type FROM channel_events WHERE external_id='E2'", "quote", "booking"),
    "training_credentials": Case("external_id,operating_company,credential_type,issued_on,expires_on",
                                 ("CR1,WFC-KE,IATA_DGR,2025-01-01,2027-01-01", "CR2,WFC-UAE,IATA_DGR,2025-01-01,2026-12-31"),
                                 "CR2,WFC-UAE,IATA_DGR,2025-01-01,2027-12-31",
                                 "CR3,WFC-UAE,IATA_DGR,2025-01-01,not-a-date", "credential_type",
                                 "SELECT count(*) FROM training_credentials", "SELECT expires_on::text FROM training_credentials WHERE external_id='CR2'",
                                 "2026-12-31", "2027-12-31"),
    "airports": Case("iata_code,name,country,timezone",
                     ("KGL,Kigali International,RW,Africa/Kigali", "EBB,Entebbe,UG,Africa/Kampala"),
                     "EBB,Entebbe International,UG,Africa/Kampala",
                     "XYZ1,Bad code,UG,Africa/Kampala", "timezone",
                     "SELECT count(*) FROM airports", "SELECT name FROM airports WHERE iata_code='EBB'", "Entebbe", "Entebbe International"),
    "airlines": Case("iata_code,name,country",
                     ("YB,Sample Airways,AE", "ZC,Test Cargo,KE"),
                     "ZC,Test Cargo Airlines,KE",
                     "TOOLONG,Bad airline,KE", "name",
                     "SELECT count(*) FROM airlines",
                     "SELECT o.canonical_name FROM airlines a JOIN organisations o ON o.id=a.organisation_id WHERE a.iata_code='ZC'",
                     "Test Cargo", "Test Cargo Airlines"),
    "operating_companies": Case("name,country",
                                ("WFC-UG,UG", "WFC-RW,RW"), "WFC-RW,TZ", "WFC-ZZ,ZZZ", "name",
                                "SELECT count(*) FROM operating_companies",
                                "SELECT country FROM operating_companies WHERE name='WFC-RW'",
                                "RW", "TZ"),
    "territories": Case("code,name,kind,country",
                        ("EAF,East Africa,region,", "GCC,Gulf,region,"), "GCC,Gulf Cooperation Council,region,",
                        "BAD,Bad kind,continent,", "kind",
                        "SELECT count(*) FROM territories", "SELECT name FROM territories WHERE code='GCC'", "Gulf", "Gulf Cooperation Council"),
    "services": Case("code,name,category",
                     ("AUDITSVC,Audit,accounting", "TECHSVC,Technology,technology"), "TECHSVC,Cargo technology,technology",
                     "BAD,Bad category,catering", "category",
                     "SELECT count(*) FROM services", "SELECT name FROM services WHERE code='TECHSVC'", "Technology", "Cargo technology"),
    "service_requirements": Case("service_code,credential_type",
                                 ("TRUCKING,ROAD_PERMIT", "TRUCKING,IATA_DGR"), "TRUCKING,IATA_DGR", "NOSUCH,IATA_DGR", "credential_type",
                                 "SELECT count(*) FROM service_credential_requirements",
                                 "SELECT count(*)::text FROM service_credential_requirements WHERE credential_type='IATA_DGR'", "1", "1"),
    "contacts": Case("external_id,full_name,role_title,operating_company,is_internal",
                     ("P1,Ops lead,Operations,WFC-KE,yes", "P2,Sales lead,Sales,WFC-UAE,yes"), "P2,Sales lead,Head of Sales,WFC-UAE,yes",
                     "P3,Bad flag,Sales,WFC-UAE,perhaps", "full_name",
                     "SELECT count(*) FROM people", "SELECT role_title FROM people WHERE external_id='P2'", "Sales", "Head of Sales"),
    "stations": Case("code,name,is_offline,country,timezone",
                     ("MSA1,Mombasa offline point,yes,KE,Africa/Nairobi", "KSM1,Kisumu point,yes,KE,Africa/Nairobi"),
                     "KSM1,Kisumu offline point,yes,KE,Africa/Nairobi",
                     "BAD1,Bad flag,sometimes,KE,Africa/Nairobi", "is_offline",
                     "SELECT count(*) FROM stations", "SELECT name FROM stations WHERE code='KSM1'", "Kisumu point", "Kisumu offline point"),
    "gateway_connections": Case("external_id,gateway,destination,airline_iata,flight_number,departure_days,departure_time,connection_cutoff_minutes",
                                ("G1,NBO,DXB,XA,XA720,1;3;5,23:50,180", "G2,NBO,DXB,XA,XA722,1;3;5,08:00,120"),
                                "G2,NBO,DXB,XA,XA722,1;3;5,08:00,150",
                                "G3,NBO,DXB,XA,XA724,1;3;5,25:00,120", "departure_days",
                                "SELECT count(*) FROM gateway_connections",
                                "SELECT connection_cutoff_minutes::text FROM gateway_connections WHERE external_id='G2'", "120", "150"),
}


def test_every_contract_has_an_onboarding_case():
    assert set(CASES) == set(im.CONTRACTS)


def _file(header: str, rows) -> bytes:
    return ("\n".join([header, *rows]) + "\n").encode()


@pytest.mark.parametrize("dataset", sorted(CASES))
def test_dataset_onboarding_end_to_end(sadb, dataset):  # noqa: F811
    for ds, text in BASE:
        r = imp.import_file(sadb, ds, f"{ds}.csv", text.encode(), None, META)
        assert r["reconciliation"]["rows_quarantined"] == 0, (ds, r["errors"])
    c = CASES[dataset]
    assert sadb.pg.val(f"SELECT count(*) FROM import_jobs WHERE dataset = '{dataset}'") in ("0", str(sum(d == dataset for d, _ in BASE) * 2))
    baseline = int(sadb.pg.val(c.count_sql))
    renamed_header = ",".join(f"Source {h}" if h == c.renamed else h for h in c.header.split(","))
    upload = _file(renamed_header, [*c.rows, c.bad])

    # mapping: the renamed required column is reported, and the preview cannot be committed
    pre = imp.dry_run(sadb, dataset, f"{dataset}.csv", upload, None, META)
    assert c.renamed in pre["mapping"]["unmapped_required"] and not pre["commit_supported"]
    with pytest.raises(imp.ImportRejected) as e:
        imp.commit(sadb, pre["job_id"], META)
    assert e.value.status == 409

    # explicit mapping -> validation -> preview: two planned inserts, one quarantined row, nothing written
    pre = imp.dry_run(sadb, dataset, f"{dataset}.csv", upload, {c.renamed: f"Source {c.renamed}"}, META)
    assert pre["commit_supported"] and pre["planned"] == {"insert": 2, "update": 0, "unchanged": 0}, (pre["planned"], pre["errors"])
    assert len({e["row_number"] for e in pre["errors"]}) == 1 and pre["errors"][0]["message"]
    assert [p["action"] for p in pre["preview"]] == ["insert", "insert"]
    assert int(sadb.pg.val(c.count_sql)) == baseline

    # commit exactly the preview; reconciliation balances
    res = imp.commit(sadb, pre["job_id"], META)
    rec = res["reconciliation"]
    assert (rec["rows_read"], rec["rows_valid"], rec["rows_quarantined"], rec["inserted"]) == (3, 2, 1, 2)
    assert rec["rows_read"] == rec["rows_valid"] + rec["rows_quarantined"] and res["partial"]
    assert int(sadb.pg.val(c.count_sql)) == baseline + 2
    assert sadb.pg.val(c.value_sql) == c.before
    for f in im.CONTRACTS[dataset].reconcile_sums:
        assert rec["sums"][f], (f, rec["sums"])                                 # totals reported per currency or unit
    assert res["reversible"] == (dataset in im.REVERSIBLE)

    # duplicate: the same rows again change nothing
    dup = imp.import_file(sadb, dataset, f"{dataset}.csv", _file(c.header, c.rows), None, META)
    assert (dup["reconciliation"]["inserted"], dup["reconciliation"]["updated"], dup["reconciliation"]["unchanged"]) == (0, 0, 2)
    assert int(sadb.pg.val(c.count_sql)) == baseline + 2

    # correction: one changed value updates the existing record
    fix = imp.import_file(sadb, dataset, f"{dataset}.csv", _file(c.header, [c.rows[0], c.corrected]), None, META)
    if c.before != c.after:
        assert (fix["reconciliation"]["inserted"], fix["reconciliation"]["updated"]) == (0, 1), fix["reconciliation"]
    assert int(sadb.pg.val(c.count_sql)) == baseline + 2 and sadb.pg.val(c.value_sql) == c.after

    # freshness is recorded for the dataset
    fr = sadb.one("dataset_freshness", name=f"Import: {dataset}")
    assert fr is not None and fr["last_success_at"] is not None

    # reversal, or a refusal naming the correction route
    if dataset in im.REVERSIBLE:
        if c.before != c.after:
            imp.reverse(sadb, fix["job_id"], "correction was wrong", META)
            assert sadb.pg.val(c.value_sql) == c.before
        imp.reverse(sadb, res["job_id"], "wrong file", META)
        assert int(sadb.pg.val(c.count_sql)) == baseline
    else:
        with pytest.raises(imp.ImportRejected) as e:
            imp.reverse(sadb, res["job_id"], "wrong file", META)
        assert e.value.status == 409 and "corrected by importing a corrected file" in e.value.detail
