"""Performance metrics with explicit bases (modules 3 and 4).

- Lanes are directional: (origin, destination) is an ordered pair.
- Utilisation needs a capacity denominator on the SAME basis (weight vs
  volume) for the SAME lane and period; otherwise it is `None` with a reason.
- Money is summed per currency. Conversion happens only when an FX rate with
  a source and date is supplied for every row.
- Unknown values stay unknown: `None` never becomes 0.
- Period comparisons use equivalent periods and flag incomplete ones.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable, Literal, Sequence

Basis = Literal["weight_kg", "volume_m3"]


@dataclass(frozen=True)
class Lane:
    origin: str
    destination: str

    def __post_init__(self):
        if self.origin == self.destination:
            raise ValueError("origin and destination must differ")

    @property
    def key(self) -> str:
        return f"{self.origin}->{self.destination}"

    def reverse(self) -> "Lane":
        return Lane(self.destination, self.origin)


@dataclass(frozen=True)
class BookingRow:
    external_id: str
    lane: Lane
    flight_date: date | None
    status: Literal["confirmed", "amended", "cancelled"]
    actual_weight_kg: Decimal | None
    chargeable_weight_kg: Decimal | None
    volume_m3: Decimal | None
    revenue: Decimal | None
    currency: str | None
    forwarder: str | None = None
    fx_rate_to_reporting: Decimal | None = None
    fx_source: str | None = None
    fx_date: date | None = None


@dataclass(frozen=True)
class CapacityRow:
    lane: Lane
    period_start: date
    period_end: date
    basis: Basis
    capacity_type: Literal["offered", "bookable", "allotted"]
    amount: Decimal


@dataclass
class MetricValue:
    value: Decimal | None
    unit: str
    reason: str | None = None
    detail: dict = field(default_factory=dict)


def _active(rows: Iterable[BookingRow]) -> list[BookingRow]:
    return [r for r in rows if r.status != "cancelled"]


def booked_quantity(rows: Sequence[BookingRow], lane: Lane, start: date, end: date, basis: Basis,
                    weight_kind: Literal["chargeable", "actual"] = "chargeable") -> MetricValue:
    attr = {"weight_kg": f"{weight_kind}_weight_kg", "volume_m3": "volume_m3"}[basis]
    on_lane = [r for r in _active(rows) if r.lane == lane]
    undated = [r.external_id for r in on_lane if r.flight_date is None]
    if undated:
        return MetricValue(None, basis, f"{len(undated)} booking(s) on this lane have no flight date and cannot be placed in a period",
                           {"undated": undated})
    selected = [r for r in on_lane if r.flight_date and start <= r.flight_date <= end]
    missing = [r.external_id for r in selected if getattr(r, attr) is None]
    if missing:
        return MetricValue(None, basis, f"{len(missing)} booking(s) missing {attr}", {"missing": missing})
    total = sum((getattr(r, attr) for r in selected), Decimal("0"))
    return MetricValue(total, basis, None, {"bookings": len(selected), "weight_kind": weight_kind if basis == "weight_kg" else None})


def utilisation(rows: Sequence[BookingRow], capacity: Sequence[CapacityRow], lane: Lane, start: date, end: date,
                basis: Basis, capacity_type: Literal["offered", "bookable", "allotted"] = "bookable") -> MetricValue:
    caps = [c for c in capacity if c.lane == lane and c.basis == basis and c.capacity_type == capacity_type]
    if not caps:
        other = [c for c in capacity if c.lane == lane]
        reason = "no capacity data for this lane"
        if other:
            reason = f"capacity supplied only as {sorted({(c.basis, c.capacity_type) for c in other})}; not compatible with {basis}/{capacity_type}"
        elif any(c.lane == lane.reverse() for c in capacity):
            reason = f"capacity exists only for the reverse lane {lane.reverse().key}"
        return MetricValue(None, "ratio", reason)
    exact = [c for c in caps if c.period_start == start and c.period_end == end]
    if not exact:
        return MetricValue(None, "ratio", "capacity period does not match the requested period")
    denominator = sum((c.amount for c in exact), Decimal("0"))
    if denominator <= 0:
        return MetricValue(None, "ratio", "capacity denominator is zero")
    numerator = booked_quantity(rows, lane, start, end, basis)
    if numerator.value is None:
        return MetricValue(None, "ratio", numerator.reason, numerator.detail)
    ratio = (numerator.value / denominator).quantize(Decimal("0.0001"), ROUND_HALF_UP)
    return MetricValue(ratio, "ratio", None, {"numerator": str(numerator.value), "denominator": str(denominator), "basis": basis})


@dataclass
class MoneyTotals:
    by_currency: dict[str, Decimal]
    reporting_total: Decimal | None
    reporting_currency: str | None
    missing_revenue: int
    reason: str | None


def revenue_totals(rows: Sequence[BookingRow], reporting_currency: str | None = None) -> MoneyTotals:
    by_ccy: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    missing = 0
    convertible = True
    converted = Decimal("0")
    for r in _active(rows):
        if r.revenue is None or r.currency is None:
            missing += 1
            continue
        by_ccy[r.currency] += r.revenue
        if reporting_currency:
            if r.currency == reporting_currency:
                converted += r.revenue
            elif r.fx_rate_to_reporting is not None and r.fx_source and r.fx_date:
                converted += r.revenue * r.fx_rate_to_reporting
            else:
                convertible = False
    reason = None
    total: Decimal | None = None
    if reporting_currency:
        if convertible:
            total = converted.quantize(Decimal("0.01"), ROUND_HALF_UP)
        else:
            reason = "one or more rows lack an FX rate with source and date; totals shown per currency only"
    return MoneyTotals(dict(by_ccy), total, reporting_currency if total is not None else None, missing, reason)


# --------------------------------------------------------------------- period comparison


@dataclass
class PeriodComparison:
    current: Decimal | None
    previous: Decimal | None
    year_ago: Decimal | None
    change_vs_previous: Decimal | None
    change_vs_year_ago: Decimal | None
    incomplete: bool
    compared_days: int
    notes: list[str]


def _sum_in(points: Sequence[tuple[date, Decimal | None]], start: date, end: date) -> tuple[Decimal | None, bool]:
    vals = [v for d, v in points if start <= d <= end]
    if any(v is None for v in vals):
        return None, True
    return sum((v for v in vals if v is not None), Decimal("0")), False


def _pct(cur: Decimal | None, base: Decimal | None) -> Decimal | None:
    if cur is None or base is None or base == 0:
        return None
    return ((cur - base) / base).quantize(Decimal("0.0001"), ROUND_HALF_UP)


def _shift_year(d: date, years: int = -1) -> date:
    try:
        return d.replace(year=d.year + years)
    except ValueError:  # 29 Feb
        return d.replace(year=d.year + years, day=28)


def _is_calendar_month(start: date, end: date) -> bool:
    return start.day == 1 and start.year == end.year and start.month == end.month and (end + timedelta(days=1)).day == 1


def compare_periods(points: Sequence[tuple[date, Decimal | None]], start: date, end: date, as_of: date,
                    data_start: date | None = None) -> PeriodComparison:
    """Compare [start, end] against the immediately preceding period of equal
    length and the same dates one year earlier (seasonality). If the current
    period is not finished at `as_of`, every period is truncated to the same
    number of elapsed days so like is compared with like."""
    notes: list[str] = []
    incomplete = as_of < end
    effective_end = min(end, as_of)
    days = (effective_end - start).days + 1
    if days <= 0:
        return PeriodComparison(None, None, None, None, None, True, 0, ["period has not started"])
    if incomplete:
        notes.append(f"current period incomplete: comparing first {days} day(s) of each period")
    length = (end - start).days + 1
    if _is_calendar_month(start, end):
        # Monthly reporting compares with the previous calendar month.
        prev_month_end = start - timedelta(days=1)
        prev_start = prev_month_end.replace(day=1)
        prev_end = min(prev_start + timedelta(days=days - 1), prev_month_end)
        if days > (prev_month_end - prev_start).days + 1:
            notes.append("previous month is shorter; compared over its full length")
    else:
        prev_start = start - timedelta(days=length)
        prev_end = prev_start + timedelta(days=days - 1)
    ya_start = _shift_year(start)
    ya_end = ya_start + timedelta(days=days - 1)

    cur, cur_missing = _sum_in(points, start, effective_end)
    prev, prev_missing = _sum_in(points, prev_start, prev_end)
    ya, ya_missing = _sum_in(points, ya_start, ya_end)
    for label, missing in (("current", cur_missing), ("previous", prev_missing), ("year-ago", ya_missing)):
        if missing:
            notes.append(f"{label} period contains unknown values; not summed")
    if data_start is not None:
        if prev_start < data_start:
            prev = None
            notes.append("no data for the previous equivalent period")
        if ya_start < data_start:
            ya = None
            notes.append("no data for the year-ago period; seasonality not assessed")
    return PeriodComparison(cur, prev, ya, _pct(cur, prev), _pct(cur, ya), incomplete, days, notes)


@dataclass
class ReviewItem:
    account: str
    kind: str
    figures: dict
    hypotheses: list[str]  # explicitly labelled as hypotheses, not findings
    notes: list[str]


def declining_account_review(account: str, comparison: PeriodComparison, *, threshold: Decimal = Decimal("-0.15"),
                             lost_reasons: dict[str, int] | None = None,
                             lane_mix_shift: dict[str, Decimal] | None = None) -> ReviewItem | None:
    """Flag an account only when it is down beyond the threshold against the
    previous period AND (where year-ago data exists) against the same period
    last year, so ordinary seasonality does not raise an alert."""
    if comparison.change_vs_previous is None or comparison.change_vs_previous > threshold:
        return None
    if comparison.change_vs_year_ago is not None and comparison.change_vs_year_ago > threshold:
        return None
    hypotheses: list[str] = []
    if lost_reasons:
        top = sorted(lost_reasons.items(), key=lambda kv: (-kv[1], kv[0]))[0]
        hypotheses.append(f"Hypothesis: quote losses, most often recorded as '{top[0]}' ({top[1]} quotes)")
    if lane_mix_shift:
        lane, delta = sorted(lane_mix_shift.items(), key=lambda kv: kv[1])[0]
        if delta < 0:
            hypotheses.append(f"Hypothesis: volume shift away from lane {lane} ({delta:+.1%})")
    if comparison.change_vs_year_ago is None:
        hypotheses.append("Hypothesis: seasonal pattern (no year-ago data to rule it out)")
    figures = {
        "current": str(comparison.current), "previous": str(comparison.previous),
        "year_ago": None if comparison.year_ago is None else str(comparison.year_ago),
        "change_vs_previous": str(comparison.change_vs_previous),
        "change_vs_year_ago": None if comparison.change_vs_year_ago is None else str(comparison.change_vs_year_ago),
        "compared_days": comparison.compared_days,
    }
    return ReviewItem(account, "declining_account", figures, hypotheses, list(comparison.notes))
