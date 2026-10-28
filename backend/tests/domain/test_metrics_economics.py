"""Verification matrix #6 (metrics) and #10 (economics); modules 3 and 4."""
from datetime import date
from decimal import Decimal as D

import pytest

from app.domain import economics as ec
from app.domain import metrics as m

DXB_NBO = m.Lane("DXB", "NBO")
NBO_DXB = DXB_NBO.reverse()


def bk(i, lane, day, kg, rev="1000", ccy="USD", status="confirmed", **kw):
    return m.BookingRow(f"B{i}", lane, date(2026, 10, day), status, D(kg) if kg else None, D(kg) if kg else None, None,
                        D(rev) if rev else None, ccy, **kw)


ROWS = [bk(1, DXB_NBO, 5, "1000"), bk(2, DXB_NBO, 6, "500"), bk(3, NBO_DXB, 5, "300"),
        bk(4, DXB_NBO, 7, "999", status="cancelled")]


def test_lanes_are_directional():
    assert DXB_NBO != NBO_DXB and DXB_NBO.key == "DXB->NBO"
    with pytest.raises(ValueError):
        m.Lane("DXB", "DXB")
    a = m.booked_quantity(ROWS, DXB_NBO, date(2026, 10, 1), date(2026, 10, 31), "weight_kg")
    b = m.booked_quantity(ROWS, NBO_DXB, date(2026, 10, 1), date(2026, 10, 31), "weight_kg")
    assert a.value == D("1500") and b.value == D("300")   # cancelled booking excluded


def test_no_utilisation_without_compatible_denominator():
    start, end = date(2026, 10, 1), date(2026, 10, 31)
    vol_only = [m.CapacityRow(DXB_NBO, start, end, "volume_m3", "bookable", D("100"))]
    u = m.utilisation(ROWS, vol_only, DXB_NBO, start, end, "weight_kg")
    assert u.value is None and "not compatible" in u.reason
    reverse_only = [m.CapacityRow(NBO_DXB, start, end, "weight_kg", "bookable", D("10000"))]
    u = m.utilisation(ROWS, reverse_only, DXB_NBO, start, end, "weight_kg")
    assert u.value is None and "reverse lane" in u.reason
    assert m.utilisation(ROWS, [], DXB_NBO, start, end, "weight_kg").value is None
    ok = [m.CapacityRow(DXB_NBO, start, end, "weight_kg", "bookable", D("6000"))]
    assert m.utilisation(ROWS, ok, DXB_NBO, start, end, "weight_kg").value == D("0.2500")


def test_unknown_weight_is_not_zero():
    rows = ROWS + [bk(9, DXB_NBO, 8, None)]
    q = m.booked_quantity(rows, DXB_NBO, date(2026, 10, 1), date(2026, 10, 31), "weight_kg")
    assert q.value is None and "missing" in q.reason


def test_actual_vs_chargeable_weight_kept_distinct():
    r = m.BookingRow("X", DXB_NBO, date(2026, 10, 2), "confirmed", D("80"), D("120"), D("0.7"), None, None)
    assert m.booked_quantity([r], DXB_NBO, date(2026, 10, 1), date(2026, 10, 31), "weight_kg", "actual").value == D("80")
    assert m.booked_quantity([r], DXB_NBO, date(2026, 10, 1), date(2026, 10, 31), "weight_kg", "chargeable").value == D("120")


def test_currencies_never_summed_without_dated_fx():
    rows = [bk(1, DXB_NBO, 5, "1", rev="100", ccy="USD"), bk(2, DXB_NBO, 5, "1", rev="367.25", ccy="AED")]
    t = m.revenue_totals(rows, "USD")
    assert t.by_currency == {"USD": D("100"), "AED": D("367.25")}
    assert t.reporting_total is None and "FX" in t.reason
    rows[1] = bk(2, DXB_NBO, 5, "1", rev="367.25", ccy="AED", fx_rate_to_reporting=D("0.2723"), fx_source="CBUAE", fx_date=date(2026, 10, 5))
    assert m.revenue_totals(rows, "USD").reporting_total == D("200.00")


def series(values_by_day):
    return [(d, None if v is None else D(v)) for d, v in values_by_day]


def daily(start, n, value):
    from datetime import timedelta
    return [(start + timedelta(days=i), value) for i in range(n)]


def test_incomplete_period_compares_equal_elapsed_days():
    pts = series(daily(date(2026, 9, 1), 30, "10") + daily(date(2026, 10, 1), 31, "10"))
    c = m.compare_periods(pts, date(2026, 10, 1), date(2026, 10, 31), as_of=date(2026, 10, 10), data_start=date(2026, 9, 1))
    assert c.incomplete and c.compared_days == 10
    assert c.current == D("100") and c.previous == D("100") and c.change_vs_previous == D("0")
    assert c.year_ago is None and any("year-ago" in n for n in c.notes)


def test_seasonal_dip_is_not_flagged_but_true_decline_is():
    # Year ago October was also low (seasonal); September high.
    pts = daily(date(2025, 10, 1), 31, "5") + daily(date(2026, 9, 1), 30, "10") + daily(date(2026, 10, 1), 31, "5")
    c = m.compare_periods(series(pts), date(2026, 10, 1), date(2026, 10, 31), as_of=date(2026, 11, 2), data_start=date(2025, 10, 1))
    assert (c.current, c.previous) == (D("155"), D("300"))
    assert c.change_vs_previous == D("-0.4833") and c.change_vs_year_ago == D("0.0000")
    assert m.declining_account_review("Forwarder A", c) is None
    pts2 = daily(date(2025, 10, 1), 31, "10") + daily(date(2026, 9, 1), 30, "10") + daily(date(2026, 10, 1), 31, "5")
    c2 = m.compare_periods(series(pts2), date(2026, 10, 1), date(2026, 10, 31), as_of=date(2026, 11, 2), data_start=date(2025, 10, 1))
    item = m.declining_account_review("Forwarder A", c2, lost_reasons={"price": 7, "capacity": 2}, lane_mix_shift={"DXB->NBO": D("-0.3")})
    assert item is not None and item.figures["change_vs_previous"] == "-0.4833" and item.figures["change_vs_year_ago"] == "-0.5000"
    assert item.hypotheses and all(h.startswith("Hypothesis:") for h in item.hypotheses)


def test_unknown_in_period_is_not_summed():
    pts = series([(date(2026, 10, 1), "5"), (date(2026, 10, 2), None)])
    c = m.compare_periods(pts, date(2026, 10, 1), date(2026, 10, 2), as_of=date(2026, 10, 5))
    assert c.current is None


# ----------------------------------------------------------- economics


def A():
    return (ec.Assumption("commission 5% of airline revenue", "WFC finance guidance", date(2026, 9, 1)),)


def test_revenue_is_not_contribution_and_unknown_terms_unqualified():
    v = ec.CommercialValue("o1", "USD", airline_revenue=D("1000000"))
    r = ec.retained_contribution(v)
    assert r.status == "unqualified" and r.retained_contribution is None


def test_scenario_requires_dated_assumptions():
    v = ec.CommercialValue("o1", "USD", wfc_remuneration=D("50000"), incremental_costs=D("20000"), basis="scenario")
    assert ec.retained_contribution(v).status == "unqualified"
    v = ec.CommercialValue("o1", "USD", wfc_remuneration=D("50000"), incremental_costs=D("20000"), basis="scenario", assumptions=A())
    r = ec.retained_contribution(v)
    assert r.status == "scenario" and r.retained_contribution == D("30000") and "2026-09-01" in r.reasons[0]


def test_pipeline_totals_no_double_counting():
    vals = [
        ec.CommercialValue("o1", "USD", wfc_remuneration=D("100"), incremental_costs=D("10"), basis="contract", competition_group="KE-GSSA"),
        ec.CommercialValue("o2", "USD", wfc_remuneration=D("80"), incremental_costs=D("0"), basis="contract", competition_group="KE-GSSA"),
        ec.CommercialValue("o3", "AED", wfc_remuneration=D("500"), incremental_costs=D("100"), basis="contract"),
        ec.CommercialValue("o3", "AED", wfc_remuneration=D("500"), incremental_costs=D("100"), basis="contract", referred_from="WFC-KSA"),
        ec.CommercialValue("o4", "USD", airline_revenue=D("999999")),
    ]
    t = ec.pipeline_totals(vals)
    assert t.by_currency == {"USD": D("90"), "AED": D("400")}    # o2 excluded; AED not added to USD
    assert "o2" in t.excluded and "o3" in t.excluded and t.unqualified == ["o4"]
    assert sorted(t.counted) == ["o1", "o3"]


def test_potential_won_realised_tracked_separately():
    vals = [ec.CommercialValue("o1", "USD", wfc_remuneration=D("100"), incremental_costs=D("10"), basis="contract", value_kind="won"),
            ec.CommercialValue("o2", "USD", wfc_remuneration=D("100"), incremental_costs=D("10"), basis="contract")]
    assert ec.pipeline_totals(vals, "potential").counted == ["o2"]
    assert ec.pipeline_totals(vals, "won").counted == ["o1"]
