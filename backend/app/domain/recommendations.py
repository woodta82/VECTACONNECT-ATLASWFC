"""Reviewable recommendations for the internal-data capability areas (28 Oct 2026 instruction, item 2).

Each recommendation states:
- the ACTION proposed, or None with the reason no action can be proposed;
- the INPUTS it was computed from (figures, period, units, currency);
- the SOURCES those figures came from (dataset, last successful import, freshness, records);
- the inputs that are MISSING (an explicit gap, never a zero);
- the THRESHOLDS used, which are PROVISIONAL until evaluated against outcomes.

A recommendation is never an opportunity by itself: a person creates the opportunity, and its qualification and
prioritisation then apply. Nothing here estimates a missing figure.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

PROVISIONAL = True
THRESHOLDS: dict[str, Decimal | int] = {
    "capacity_high_utilisation": Decimal("0.85"),   # booked / bookable at or above this: capacity is tight
    "capacity_low_utilisation": Decimal("0.50"),    # at or below this with falling demand: allotment under-used
    "demand_rising": Decimal("0.10"),               # chargeable kg change vs the preceding period
    "demand_falling": Decimal("-0.10"),
    "funnel_min_sessions": 5,                       # fewer quote-request sessions than this: too few to judge friction
    "funnel_low_booking_rate": Decimal("0.20"),     # booked / quote-request sessions below this: friction
    "integration_failures_min": 3,                  # integration failures per channel and period worth a review
}


def _thr(*keys: str) -> dict[str, str]:
    return {k: str(THRESHOLDS[k]) for k in keys}


def _dec(v: Any) -> Decimal | None:
    return None if v is None else Decimal(str(v))


# ------------------------------------------------------------------ capacity and trade lanes
def lane_recommendation(lane: str, *, utilisation: Decimal | None, utilisation_reason: str | None, booked_kg: Any, capacity_kg: Any,
                        trend: Decimal | None, previous_kg: Any, current_kg: Any, period: str, comparison_period: str,
                        sources: list[dict[str, Any]]) -> dict[str, Any]:
    """Capacity recommendation for one directional lane from utilisation (same basis and period) and the demand trend."""
    missing: list[str] = []
    if utilisation is None:
        missing.append(f"utilisation: {utilisation_reason or 'not computable'}")
    if trend is None:
        missing.append("demand trend: no chargeable weight in the preceding period of equal length" if not previous_kg else
                       "demand trend: current chargeable weight unknown")
    inputs = {"utilisation": None if utilisation is None else str(utilisation), "booked_chargeable_kg": None if booked_kg is None else str(booked_kg),
              "bookable_capacity_kg": None if capacity_kg is None else str(capacity_kg), "trend": None if trend is None else str(trend),
              "current_chargeable_kg": None if current_kg is None else str(current_kg),
              "previous_chargeable_kg": None if previous_kg is None else str(previous_kg), "period": period,
              "comparison_period": comparison_period, "units": "kg (chargeable); ratio for utilisation"}
    base = {"lane": lane, "key": f"cl|{lane}|{period}", "inputs": inputs, "sources": sources, "missing": missing,
            "thresholds": _thr("capacity_high_utilisation", "capacity_low_utilisation", "demand_rising", "demand_falling"),
            "provisional": PROVISIONAL}
    if utilisation is None:
        return base | {"action": None, "kind": "insufficient_data",
                       "why": "no recommendation: utilisation needs bookable capacity on the same basis and period as the bookings"}
    hi, lo = THRESHOLDS["capacity_high_utilisation"], THRESHOLDS["capacity_low_utilisation"]
    rising, falling = THRESHOLDS["demand_rising"], THRESHOLDS["demand_falling"]
    if utilisation >= hi and (trend is None or trend >= 0):                       # type: ignore[operator]
        why = f"utilisation {utilisation:.2%} is at or above {hi:.0%}" + (f" and demand changed {trend:+.2%}" if trend is not None else
                                                                          " (demand trend unknown)")
        return base | {"action": "Seek additional bookable capacity or an allotment on this lane", "kind": "add_capacity", "why": why,
                       "strength": "strong" if trend is not None and trend >= rising else "indicative"}        # type: ignore[operator]
    if utilisation <= lo and trend is not None and trend <= falling:               # type: ignore[operator]
        return base | {"action": "Review the allotment: capacity is under-used and demand is falling", "kind": "review_allotment",
                       "why": f"utilisation {utilisation:.2%} is at or below {lo:.0%} and demand changed {trend:+.2%}", "strength": "strong"}
    return base | {"action": None, "kind": "monitor",
                   "why": f"utilisation {utilisation:.2%}" + (f", demand {trend:+.2%}" if trend is not None else ", demand trend unknown")
                          + ": within the provisional thresholds; no change proposed"}


def lane_priority_facts(rec: dict[str, Any], *, snapshots: int, currencies: list[str], bookings_with_revenue: int, bookings: int) -> dict[str, Any]:
    """Anchors (0-4) for the capacity-lanes scoring model, from the recommendation's inputs. Unknown stays None."""
    util = _dec(rec["inputs"]["utilisation"])
    trend = _dec(rec["inputs"]["trend"])
    spare = None if util is None else (Decimal("1") - util)
    spare_anchor = None if spare is None else (0 if spare <= 0 else 1 if spare < Decimal("0.05") else 2 if spare < Decimal("0.15")
                                               else 3 if spare < Decimal("0.30") else 4)
    trend_anchor = None if trend is None else (0 if trend < Decimal("-0.30") else 1 if trend < Decimal("-0.10") else 2 if trend <= Decimal("0.10")
                                               else 3 if trend <= Decimal("0.30") else 4)
    cap_anchor = 0 if snapshots == 0 else 1 if snapshots == 1 else 2 if snapshots == 2 else 3
    if not bookings:
        yld = None
    elif len(currencies) > 1:
        yld = 0
    elif bookings_with_revenue == 0:
        yld = 1
    elif bookings_with_revenue < bookings:
        yld = 2 if bookings_with_revenue * 2 < bookings else 3
    else:
        yld = 4
    return {"spare_capacity_anchor": spare_anchor, "spare_capacity_reason": "unknown" if spare is None else f"{spare:.2%} of bookable capacity unsold",
            "booking_trend_anchor": trend_anchor, "booking_trend_reason": "unknown" if trend is None else f"{trend:+.2%} vs the preceding period",
            "capacity_data_anchor": cap_anchor, "capacity_data_reason": f"{snapshots} capacity snapshot(s) for this lane",
            "yield_comparability_anchor": yld,
            "yield_comparability_reason": (f"{bookings_with_revenue} of {bookings} booking(s) carry revenue; currencies: {', '.join(currencies) or 'none'}"
                                           if bookings else "no bookings")}


# ------------------------------------------------------------------ trucking and gateways
def station_recommendation(station: str, name: str | None, options: list[dict[str, Any]], ship_date: date, gap: str | None,
                           sources: list[dict[str, Any]]) -> dict[str, Any]:
    """Coverage recommendation for one offline station from the feasibility of each feeder + connection."""
    feasible = [o for o in options if o["result"] == "feasible"]
    unresolved = [o for o in options if o["result"] == "unresolved"]
    base = {"station": station, "key": f"tg|{station}|{ship_date.isoformat()}", "ship_date": ship_date.isoformat(), "sources": sources,
            "inputs": {"feeders_and_connections_checked": len(options), "feasible": len(feasible), "unresolved": len(unresolved),
                       "units": "minutes for transit and cutoff; local times at each station"},
            "provisional": PROVISIONAL, "thresholds": {"max_connection_days": "2"}}
    if feasible:
        best = min(feasible, key=lambda o: (o["transit_minutes"] or 10**6, o["connection"] or ""))
        return base | {"action": f"Offer road-feeder coverage from {station}: {best['provider']} to {best['gateway']}, connecting to "
                                  f"{best['connection']}" + (f" ({best['destination']})" if best.get("destination") else ""),
                       "kind": "coverage_available", "why": best["reason"], "best_option": best,
                       "missing": [f"{o['provider']} → {o['connection']}: {o['reason']}" for o in unresolved]}
    if unresolved:
        return base | {"action": None, "kind": "insufficient_data",
                       "why": "no feeder is shown to make a connection: the missing transit time or cutoff must be supplied first",
                       "missing": [f"{o['provider']} → {o['connection']}: {o['reason']}" for o in unresolved]}
    return base | {"action": f"Coverage gap at {station}: no feasible road-feeder connection on {ship_date.isoformat()}; source a feeder "
                             "provider or a different gateway connection", "kind": "coverage_gap",
                   "why": gap or "; ".join(f"{o['provider']} → {o['connection']}: {o['reason']}" for o in options) or "no feeder recorded",
                   "missing": []}


# ------------------------------------------------------------------ technology and solutions
def solution_candidates(funnels: list[dict[str, Any]], failures: list[dict[str, Any]], adoption: list[dict[str, Any]],
                        combined: list[dict[str, Any]], period: str, sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Evidence-backed solution candidates from linked channel events. Every candidate cites its counts and period."""
    out: list[dict[str, Any]] = []
    common = {"period": period, "sources": sources, "provisional": PROVISIONAL}
    for f in funnels:
        ch = f["channel"]
        if f["status"] != "computed":
            out.append(common | {"key": f"ts|funnel|{ch}|{period}", "kind": "insufficient_data", "action": None, "channel": ch,
                                 "why": f"booking funnel for {ch} not computable", "missing": list(f.get("limitations") or []), "evidence": {},
                                 "thresholds": _thr("funnel_min_sessions", "funnel_low_booking_rate")})
            continue
        req, booked = int(f["stages"].get("quote_requests", 0)), int(f["stages"].get("booked", 0))
        if req < int(THRESHOLDS["funnel_min_sessions"]):
            out.append(common | {"key": f"ts|funnel|{ch}|{period}", "kind": "insufficient_data", "action": None, "channel": ch,
                                 "why": f"only {req} quote-request session(s) on {ch}: too few to judge friction",
                                 "missing": [f"at least {THRESHOLDS['funnel_min_sessions']} linked quote-request sessions"],
                                 "evidence": dict(f["stages"]), "thresholds": _thr("funnel_min_sessions", "funnel_low_booking_rate")})
            continue
        rate = (Decimal(booked) / Decimal(req)).quantize(Decimal("0.0001"))
        if rate < THRESHOLDS["funnel_low_booking_rate"]:                                    # type: ignore[operator]
            out.append(common | {"key": f"ts|funnel|{ch}|{period}", "kind": "booking_friction", "channel": ch,
                                 "action": f"Investigate booking friction on {ch}: {booked} of {req} quote-request sessions booked ({rate:.2%})",
                                 "why": f"session booking rate {rate:.2%} is below {THRESHOLDS['funnel_low_booking_rate']:.0%}",
                                 "evidence": dict(f["stages"]) | {"booking_rate": str(rate)}, "missing": list(f.get("limitations") or []),
                                 "thresholds": _thr("funnel_min_sessions", "funnel_low_booking_rate")})
    for fl in failures:
        n = int(fl["failures"])
        if n >= int(THRESHOLDS["integration_failures_min"]):
            out.append(common | {"key": f"ts|integration|{fl['channel']}|{period}", "kind": "integration_reliability", "channel": fl["channel"],
                                 "action": f"Review the {fl['channel']} integration: {n} integration failures in the period",
                                 "why": f"{n} failures ≥ {THRESHOLDS['integration_failures_min']}", "evidence": {"integration_failures": n},
                                 "missing": [], "thresholds": _thr("integration_failures_min")})
    for a in adoption:
        if a.get("adoption_gap"):
            out.append(common | {"key": f"ts|adoption|{a['forwarder_id']}|{period}", "kind": "digital_adoption", "forwarder": a["forwarder"],
                                 "action": f"Offer digital booking onboarding to {a['forwarder']}: {a['bookings']} booking(s), no digital-channel events",
                                 "why": "bookings in the period but no digital-channel activity",
                                 "evidence": {"bookings": int(a["bookings"]), "digital_events": int(a["digital_events"])}, "missing": [], "thresholds": {}})
    for c in combined:
        out.append(common | {"key": f"ts|combined|{c['forwarder_id']}|{period}", "kind": "combined_service", "forwarder": c["forwarder"],
                             "action": f"Offer {c['forwarder']} a combined air + road-feeder service via {', '.join(c['gateways'])}",
                             "why": "digitally active forwarder booking through gateways WFC also serves by road feeder",
                             "evidence": {"bookings_via_gateways": int(c["bookings_via_gateways"]), "gateways": list(c["gateways"])},
                             "missing": [], "thresholds": {}})
    order = {"booking_friction": 0, "integration_reliability": 1, "combined_service": 2, "digital_adoption": 3, "insufficient_data": 9}
    out.sort(key=lambda r: (order.get(r["kind"], 5), r["key"]))
    for i, r in enumerate(out, start=1):
        r["rank"] = i
        r["rank_reason"] = ("insufficient data: listed last, not ranked against evidence-backed candidates" if r["kind"] == "insufficient_data"
                            else f"ordered by kind ({r['kind']}): friction and reliability affect every booking on a channel; combined "
                                 "offers and onboarding concern one forwarder (provisional order)")
    return out


# ------------------------------------------------------------------ network development
def coverage_gaps(agreements: list[dict[str, Any]], verified: set[tuple[str, str]], on: date) -> list[dict[str, Any]]:
    """Contracted (territory, service) pairs that no WFC operating company can deliver: an in-force agreement names the
    territory and service, but no verified capability for that service exists at a station in that territory."""
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for a in agreements:
        if a.get("status") not in (None, "active") or (a.get("effective_from") and a["effective_from"] > on) or \
                (a.get("effective_to") and a["effective_to"] < on):
            continue
        for t in a["territories"] or []:
            for s in a["services"] or []:
                if (t, s) in verified or ("*", s) in verified:       # station-less verified capability is company-wide
                    continue
                g = out.setdefault((t, s), {"territory": t, "service": s, "airlines": [], "key": f"nd|gap|{t}|{s}"})
                if a["airline_name"] not in g["airlines"]:
                    g["airlines"].append(a["airline_name"])
    return [g | {"why": f"in-force agreement(s) with {', '.join(sorted(g['airlines']))} cover {g['service']} in {g['territory']}, but no WFC "
                        "company holds verified capability for it at a station there",
                 "action": f"Assess a partner, referral or acquisition research for {g['service']} in {g['territory']}"}
            for g in sorted(out.values(), key=lambda g: (-len(g["airlines"]), g["territory"], g["service"]))]


# ------------------------------------------------------------------ rank explanations for the ordered lists
# The orders below are rules, not weighted scores; they are provisional until WFC confirms them.
RANKING_RULES = {
    "account_growth": "actionable first, then fewest blockers, fewest unknowns, most bookings with the airline",
    "forwarder_sales": "needs review first, then dormant, then 12-month booking count",
    "outsourcing_training": "best WFC readiness first (ready, review required, blocked, no match), then earliest deadline",
    "service_operations": "severity (critical, high, medium, low), then earliest deadline",
}


def explain_ranks(module: str, rows: list[dict[str, Any]], reason: Any, missing: Any) -> list[dict[str, Any]]:
    """Number an already-ordered list and say, for each row, why it sits where it does and what is missing."""
    for i, r in enumerate(rows, start=1):
        r["rank"] = i
        r["rank_reason"] = f"{reason(r)} (order: {RANKING_RULES[module]}; provisional)"
        r["missing"] = [m for m in missing(r) if m]
    return rows
