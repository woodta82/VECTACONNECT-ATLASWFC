"""Verification matrix #5 (import idempotency, amendments, cancellations, reconciliation, quarantine)."""
import io
from decimal import Decimal as D

import pytest

from app.domain import imports as im

HEADER = "external_id,forwarder,airline_iata,origin,destination,flight_date,booked_at,status,actual_weight,chargeable_weight,volume,revenue,currency,operating_company\n"
BATCH1 = HEADER + (
    "BK-1,Forwarder A,XA,DXB,NBO,2026-10-05,2026-10-01T09:00:00+04:00,confirmed,800,1000,6.1,2500.00,USD,WFC-UAE\n"
    "BK-2,Forwarder A,XA,NBO,DXB,2026-10-06,2026-10-01T10:00:00+04:00,confirmed,300,300,2,900.50,USD,WFC-UAE\n"
    "BK-3,Forwarder B,XA,DXB,NBO,2026-10-07,2026-10-02T10:00:00+04:00,confirmed,100,150,1,1000,AED,WFC-UAE\n"
    "BK-4,Forwarder B,XA,DXB,DXB,2026-10-07,2026-10-02T10:00:00+04:00,confirmed,100,150,1,10,USD,WFC-UAE\n"     # same origin/dest
    "BK-5,Forwarder B,XA,DXB,NBO,2026-10-07,2026-10-02 10:00,confirmed,100,150,1,10,USD,WFC-UAE\n"              # no offset
    "BK-6,Forwarder B,XA,DXB,NBO,2026-10-07,2026-10-02T10:00:00Z,confirmed,abc,150,1,10,USD,WFC-UAE\n"          # bad number
    "BK-7,Forwarder B,XA,DXB,NBO,2026-10-07,2026-10-02T10:00:00Z,confirmed,1,1,1,10,,WFC-UAE\n"                 # money w/o currency
    "BK-1,Forwarder A,XA,DXB,NBO,2026-10-05,2026-10-01T09:00:00+04:00,confirmed,800,1000,6.1,2500.00,USD,WFC-UAE\n"  # dup in file
)


def apply(effects, store):
    for e in effects:
        store[e.key] = dict(e.values)
    return store


def test_dry_run_quarantines_bad_rows_and_reconciles():
    preview, effects, errors, rec = im.run_import("bookings", "b.csv", BATCH1.encode(), {})
    assert preview.unmapped_required == []
    assert rec.rows_read == 8 and rec.rows_valid == 3 and rec.rows_quarantined == 5
    codes = sorted({e.code for e in errors})
    assert codes == ["duplicate_in_file", "inconsistent", "invalid_value"]
    assert all(e.raw for e in errors)  # raw values kept, nothing dropped silently
    assert rec.inserted == 3
    assert rec.sums["chargeable_weight"] == {"kg": "1450"}
    assert rec.sums["revenue"] == {"AED": "1000", "USD": "3400.50"}


def test_rerun_is_idempotent_then_amendment_and_cancellation():
    store: dict = {}
    _, effects, _, _ = im.run_import("bookings", "b.csv", BATCH1.encode(), store)
    apply(effects, store)
    _, effects2, _, rec2 = im.run_import("bookings", "b.csv", BATCH1.encode(), store)
    assert (rec2.inserted, rec2.updated, rec2.unchanged) == (0, 0, 3)
    amend = HEADER + (
        "BK-1,Forwarder A,XA,DXB,NBO,2026-10-05,2026-10-01T09:00:00+04:00,amended,800,1100,6.1,2700.00,USD,WFC-UAE\n"
        "BK-2,Forwarder A,XA,NBO,DXB,2026-10-06,2026-10-01T10:00:00+04:00,cancelled,300,300,2,900.50,USD,WFC-UAE\n"
    )
    _, effects3, _, rec3 = im.run_import("bookings", "amend.csv", amend.encode(), store)
    assert (rec3.inserted, rec3.updated) == (0, 2)
    assert rec3.sums["revenue"] == {"USD": "2700.00"}      # cancelled row excluded from the totals
    by_key = {e.key: e for e in effects3}
    assert by_key["BK-1"].previous["chargeable_weight"] == D("1000")   # traceable previous value
    apply(effects3, store)
    assert len(store) == 3 and store["BK-2"]["status"] == "cancelled"  # no duplicates
    # Reversal restores the batch exactly.
    plan = im.reversal_plan(effects3)
    assert ("BK-1", "restore", by_key["BK-1"].previous) in plan and len(plan) == 2


def test_file_validation():
    with pytest.raises(im.FileRejected):
        im.validate_upload("x.xlsm", b"PK\x03\x04")
    with pytest.raises(im.FileRejected):
        im.validate_upload("x.exe", b"MZ")
    with pytest.raises(im.FileRejected):
        im.validate_upload("x.xlsx", b"not a zip")
    with pytest.raises(im.FileRejected):
        im.validate_upload("x.csv", b"\xff\xfe\x00bad")
    with pytest.raises(im.FileRejected):
        im.validate_upload("x.csv", b"")


def test_xlsx_import_and_missing_required_mapping():
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["External ID", "Origin", "Destination", "Period Start", "Period End", "Basis", "Capacity Type", "Amount", "Snapshot At"])
    ws.append(["CAP-1", "DXB", "NBO", "2026-10-01", "2026-10-31", "weight_kg", "bookable", 1234.56, "2026-09-30T12:00:00+00:00"])
    buf = io.BytesIO()
    wb.save(buf)
    preview, effects, errors, rec = im.run_import("capacity", "cap.xlsx", buf.getvalue(), {})
    assert not errors and rec.inserted == 1
    assert effects[0].values["amount"] == D("1234.56")  # no binary-float artefact (not 1234.5599999...)
    _, _, errors, _ = im.run_import("capacity", "c.csv", b"foo,bar\n1,2\n", {})
    assert errors[0].code == "mapping"


def test_every_dataset_has_contract_and_template():
    for name, c in im.CONTRACTS.items():
        assert c.source_of_truth and c.retention and c.required
        assert im.template_csv(name).strip().split(",")[0] == c.fields[0].name
