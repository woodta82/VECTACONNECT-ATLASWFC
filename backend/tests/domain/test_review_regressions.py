"""Regression tests for defects found by the independent review (26 Oct 2026).
Each test reproduces the reported failure scenario."""
import io
from datetime import date, datetime, timezone
from decimal import Decimal as D

import pytest

from app.domain import economics as ec
from app.domain import imports as im
from app.domain import metrics as mt
from app.domain import qualification as q
from app.domain.capability import CapabilityRecord, capability_readiness

NOW = datetime(2026, 10, 26, tzinfo=timezone.utc)


def test_r4_capability_cannot_be_overridden_to_pass():
    checks = [q.Check("capability", "unknown", True, "operating company not yet assigned")]
    with pytest.raises(q.OverrideRejected):
        q.apply_overrides(checks, [q.Override("capability", "pass", "We are confident we can do this", NOW)], NOW)
    # review_required / fail overrides remain allowed
    out = q.apply_overrides(checks, [q.Override("capability", "fail", "Station closed for refurbishment", NOW)], NOW)
    assert q.qualification_status(out) == "blocked"


def test_r9_competition_group_with_mixed_currencies_counts_nothing():
    vals = [ec.CommercialValue("A", "USD", wfc_remuneration=D("100"), incremental_costs=D("10"), basis="contract", competition_group="g1"),
            ec.CommercialValue("B", "EUR", wfc_remuneration=D("80"), incremental_costs=D("0"), basis="contract", competition_group="g1"),
            ec.CommercialValue("C", "USD", wfc_remuneration=D("5"), incremental_costs=D("0"), basis="contract")]
    t = ec.pipeline_totals(vals)
    assert t.by_currency == {"USD": D("5")} and t.counted == ["C"]
    assert "mixes currencies" in t.excluded["A"] and "mixes currencies" in t.excluded["B"]


def test_r11_undated_booking_makes_lane_quantity_unknown():
    lane = mt.Lane("DXB", "NBO")
    rows = [mt.BookingRow("B1", lane, date(2026, 10, 5), "confirmed", D("100"), D("100"), None, None, None),
            mt.BookingRow("B2", lane, None, "confirmed", D("900"), D("900"), None, None, None)]
    v = mt.booked_quantity(rows, lane, date(2026, 10, 1), date(2026, 10, 31), "weight_kg")
    assert v.value is None and "no flight date" in v.reason


def test_r12_naive_datetimes_need_declared_zone_and_ambiguous_numbers_rejected():
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["external_id", "origin", "destination", "booked_at", "status", "revenue", "currency"])
    ws.append(["X1", "DXB", "NBO", datetime(2026, 10, 1, 9, 0), "confirmed", 10.5, "USD"])   # Excel cell: no tz
    buf = io.BytesIO()
    wb.save(buf)
    _, _, errors, _ = im.run_import("bookings", "b.xlsx", buf.getvalue(), {})
    assert errors and "time zone" in errors[0].message
    _, effects, errors, _ = im.run_import("bookings", "b.xlsx", buf.getvalue(), {}, naive_tz="Asia/Dubai")
    assert not errors and effects[0].values["booked_at"] == datetime(2026, 10, 1, 5, 0, tzinfo=timezone.utc)

    head = "external_id,origin,destination,booked_at,status,revenue,currency\n"
    for bad in ('"1.234,56"', '"12,34"', "1e5"):
        _, _, errs, _ = im.run_import("bookings", "b.csv", (head + f"X,DXB,NBO,2026-10-01T09:00:00Z,confirmed,{bad},USD\n").encode(), {})
        assert errs and errs[0].field == "revenue", bad
    _, eff, errs, _ = im.run_import("bookings", "b.csv", (head + 'X,DXB,NBO,2026-10-01T09:00:00Z,confirmed,"1,234.56",USD\n').encode(), {})
    assert not errs and eff[0].values["revenue"] == D("1234.56")


def test_r10_unresolved_references_are_quarantined():
    head = "external_id,origin,destination,booked_at,status\n"
    data = (head + "X1,DXB,LHR,2026-10-01T09:00:00Z,confirmed\nX2,DXB,NBO,2026-10-01T09:00:00Z,confirmed\n").encode()
    known = {"DXB", "NBO"}

    def check(v):
        return [(f, f"airport {v[f]} is not registered") for f in ("origin", "destination") if v.get(f) and v[f] not in known]
    _, effects, errors, rec = im.run_import("bookings", "b.csv", data, {}, reference_check=check)
    assert [e.code for e in errors] == ["unresolved_reference"] and rec.rows_quarantined == 1 and [e.key for e in effects] == ["X2"]


def test_r15_expired_record_does_not_hide_a_valid_one():
    recs = [CapabilityRecord("WFC-KE", "GSSA", "NBO", "verified", date(2020, 1, 1), date(2023, 12, 31)),
            CapabilityRecord("WFC-KE", "GSSA", "NBO", "verified", date(2024, 1, 1), date(2027, 12, 31))]
    r = capability_readiness(recs, [], operating_company="WFC-KE", service_code="GSSA", station="NBO", on=date(2026, 10, 26))
    assert r.readiness == "ready" and r.matched_record == recs[1]
