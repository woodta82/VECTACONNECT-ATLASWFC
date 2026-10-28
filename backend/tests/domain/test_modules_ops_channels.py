"""Modules 5 (service), 6 (trucking), 8 (technology), 9 (network development)."""
from datetime import date, datetime, time, timedelta, timezone

from app.domain import channels as ch
from app.domain import operations as op

UTC = timezone.utc
NOW = datetime(2026, 10, 26, 6, 0, tzinfo=UTC)


def test_delayed_reservation_creates_one_alert_and_one_task_then_resolution_keeps_history():
    store = op.OpsStore()
    kw = dict(exception_type="reservation", severity="medium", description="Reservation for AWB 000-1234 5675 delayed",
              booking_ref="000-12345675", customer="Forwarder A", operating_company="WFC-UAE",
              deadline_utc=NOW + timedelta(hours=4), owner="Ops desk DXB")
    op.report_exception(store, now=NOW, **kw)
    op.report_exception(store, now=NOW + timedelta(minutes=5), **kw)                    # repeat report
    op.report_exception(store, now=NOW + timedelta(minutes=9), **{**kw, "severity": "high"})  # escalation, same problem
    assert len(store.exceptions) == 1 and len(store.alerts) == 1 and len(store.tasks) == 1
    rec = store.exceptions[0]
    assert rec.severity == "high"
    key = rec.dedup_key
    op.resolve_exception(store, key, note="Space confirmed on next flight", now=NOW + timedelta(hours=1))
    assert store.active(key) is None and rec.status == "resolved"
    assert [h["change"] for h in rec.history] == ["status", "severity", "status"]
    assert list(store.tasks.values())[0]["status"] == "done"
    # A NEW occurrence after resolution is a new exception, with its own alert and task.
    op.report_exception(store, now=NOW + timedelta(days=1), **kw)
    assert len(store.exceptions) == 2 and len(store.alerts) == 2 and len(store.tasks) == 2


FEEDER = op.FeederService("RUH-OFFLINE", "DXB", frozenset({1, 3, 5}), time(6, 0), 600)
CONN = op.GatewayConnection("DXB", frozenset({1, 2, 3, 4, 5, 6, 7}), time(23, 30), 240)


def test_feeder_feasible_when_cutoff_met():
    f = op.feeder_feasibility(FEEDER, CONN, date(2026, 10, 26))  # Monday
    assert f.result == "feasible" and f.connects_on == date(2026, 10, 26)


def test_missing_cutoff_is_unresolved_not_recommended():
    f = op.feeder_feasibility(FEEDER, op.GatewayConnection("DXB", frozenset({1}), time(23, 30), None), date(2026, 10, 26))
    assert f.result == "unresolved"
    f = op.feeder_feasibility(op.FeederService("X", "DXB", frozenset({1}), time(6, 0), None), CONN, date(2026, 10, 26))
    assert f.result == "unresolved"


def test_feeder_missing_cutoff_window_is_infeasible():
    late = op.GatewayConnection("DXB", frozenset({1}), time(15, 0), 120)   # Mondays only, cutoff 13:00; feeder lands 16:00
    f = op.feeder_feasibility(FEEDER, late, date(2026, 10, 26))
    assert f.result == "infeasible"                       # next Monday is beyond the 2-day dwell limit
    assert op.feeder_feasibility(FEEDER, late, date(2026, 10, 26), max_wait_days=7).result == "feasible"
    assert op.feeder_feasibility(FEEDER, CONN, date(2026, 10, 27)).result == "infeasible"  # no Tuesday feeder


def ev(t, minute, session=None, ref=None):
    return ch.ChannelEvent(t, session, ref, NOW + timedelta(minutes=minute), "web")


def test_funnel_requires_linked_events():
    events = [ev("quote_request", 0, "s1"), ev("quote", 5, "s1", "BK1"), ev("booking", 30, None, "BK1"),
              ev("quote_request", 1, "s2"), ev("quote", 6, "s2", "BK2"),
              ev("quote_request", 2, "s3"),
              ev("booking", 40, None, "BK-UNLINKED")]
    f = ch.booking_funnel(events, NOW, NOW + timedelta(days=1), "web")
    assert f.status == "computed"
    assert f.stages == {"quote_requests": 3, "quoted": 2, "booked": 1}
    assert f.conversion == {"quote_rate": "0.6667", "booking_rate": "0.5000"}
    assert any("could not be linked" in lim for lim in f.limitations)


def test_no_funnel_without_instrumentation():
    events = [ev("quote_request", 0), ev("quote", 5), ev("booking", 30)]
    f = ch.booking_funnel(events, NOW, NOW + timedelta(days=1), "web")
    assert f.status == "instrumentation_missing" and f.stages == {} and f.limitations
    assert ch.booking_funnel([], NOW, NOW + timedelta(days=1), "web").status == "no_data"


def test_partner_fit_is_sourced_and_has_no_valuation():
    gaps = [("KE", "TRUCKING"), ("UG", "TRUCKING")]
    claims = [ch.PartnerClaim("serves_territory", "KE", "supported", "c1"),
              ch.PartnerClaim("offers_service", "TRUCKING", "supported", "c2"),
              ch.PartnerClaim("serves_territory", "UG", "unverified", "c3")]
    fa = ch.partner_fit(gaps, claims)
    assert fa.result == "strong" and fa.covered_gaps == ["KE/TRUCKING"] and fa.evidence_claim_ids == ["c1", "c2"]
    assert fa.valuation is None and any("unverified" in u for u in fa.unsupported)
    assert ch.partner_fit(gaps, [ch.PartnerClaim("serves_territory", "KE", "unverified", "c9")]).result == "insufficient_evidence"
