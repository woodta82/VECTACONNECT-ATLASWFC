"""The nine capability areas (directive §9): each has a usable workflow and a
meaningful output, and says "Not connected" or "Insufficient data" when its
required inputs are missing, never zero.

| Area                      | Output here                                                            |
|---------------------------|------------------------------------------------------------------------|
| Airline representation    | discovery + opportunities (services.discovery / ingestion)             |
| Account growth            | supported territory/service expansion from agreements x capabilities  |
| Forwarder sales           | dormant / declining accounts, quote conversion, review priority        |
| Capacity and trade lanes  | directional trends, capacity changes, utilisation, per-currency yield  |
| Service and operations    | exceptions with owners and resolution history (ops_service)            |
| Trucking and gateways     | offline stations x feeders x gateway connections, feasibility          |
| Outsourcing and training  | verified demand matched to capability, resources and credentials       |
| Technology and solutions  | digital adoption gaps, booking friction, combined-service candidates   |
| Network development       | gaps, partners, referrals, acquisition research with evidence          |

Module candidates become opportunities only by a human action
(`create_module_opportunity`), with the internal record they came from as
provenance (`origin_ref`) and module-specific qualification checks.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Any, Sequence

from ..domain import import_docs
from ..domain import imports as im
from ..domain import metrics as mt
from ..domain import recommendations as rec
from ..domain.capability import CapabilityRecord, Credential, capability_readiness
from ..domain.channels import ChannelEvent, booking_funnel
from ..domain.coverage import Agreement, ThirdPartyAppointment, coverage_matrix, expansion_candidates
from ..domain.operations import FeederService, GatewayConnection, feeder_feasibility
from ..reference.geography import COUNTRIES
from ..repo.db import Database
from .audit import RequestMeta, audit


class ModuleRejected(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


def _loaded(db: Database, dataset: str) -> dict[str, Any]:
    """Freshness of one dataset, with its source of truth and refresh requirement (shown wherever the data is used)."""
    label = {"source_of_truth": im.CONTRACTS[dataset].source_of_truth, "refresh": import_docs.refresh_requirement(dataset)}
    r = db.one("dataset_freshness", name=f"Import: {dataset}")
    if r is None or r["last_success_at"] is None:
        return {"dataset": dataset, "status": "not_connected", "last_success_at": None} | label
    stale = bool(r["freshness_sla_hours"]) and (datetime.now(timezone.utc) - r["last_success_at"]).total_seconds() / 3600 > r["freshness_sla_hours"]
    return {"dataset": dataset, "status": "stale" if stale else "loaded", "last_success_at": r["last_success_at"]} | label


def _status(sources: list[dict[str, Any]], required: list[str]) -> tuple[str, list[str]]:
    missing = [s["dataset"] for s in sources if s["dataset"] in required and s["status"] == "not_connected"]
    if missing:
        return "not_connected", [f"{m}: not connected (import it under Data Sources and Imports)" for m in missing]
    return "ok", [f"{s['dataset']}: stale (older than its freshness SLA)" for s in sources if s["status"] == "stale"]


# ===================================================================== account growth


def account_growth(db: Database, on: date | None = None) -> dict[str, Any]:
    on = on or date.today()
    sources = [_loaded(db, d) for d in ("agreements", "capabilities", "training_credentials", "bookings")]
    status, gaps = _status(sources, ["agreements", "capabilities"])
    if status != "ok":
        return {"status": status, "candidates": [], "sources": sources, "gaps": gaps}
    agreements_rows = db.all("agreements_all")
    ags = [Agreement(a["airline_id"], a["operating_company"], frozenset(a["territories"] or []), frozenset(a["services"] or []),
                     a["effective_from"], a["effective_to"], a["exclusivity"], a["appointment_rights"], a["status"]) for a in agreements_rows]
    tps = [ThirdPartyAppointment(t["airline_id"], t["territory"], t["service"], t["holder"] or "unknown holder", t["exclusivity"], t["valid_to"])
           for t in db.all("third_party_all")]
    caps = [CapabilityRecord(c["operating_company"], c["service_code"], c["station"], c["status"], c["valid_from"], c["valid_to"])
            for c in db.all("capabilities_all", company=None)]
    creds = [Credential(c["operating_company"], c["credential_type"], c["expires_on"], c["station"], c["issued_on"])
             for c in db.all("credentials_all2")]
    requirements: dict[str, Sequence[str]] = {}
    for r in db.all("service_requirements_all"):
        requirements[r["service_code"]] = [*requirements.get(r["service_code"], []), r["credential_type"]]
    station_country = {r["iata_code"]: r["country"] for r in db.all("airports_brief")}
    # WFC footprint: countries where a company holds verified capability at a station, by service.
    footprint: dict[str, set[str]] = defaultdict(set)      # service -> countries
    station_in: dict[tuple[str, str, str], str] = {}        # (company, service, country) -> station
    for c in caps:
        if c.status == "verified" and c.station and station_country.get(c.station):
            footprint[c.service_code].add(station_country[c.station])
            station_in[(c.operating_company, c.service_code, station_country[c.station])] = c.station
    names = {a["airline_id"]: a["airline_name"] for a in agreements_rows}
    bookings_by_airline = {r["airline_id"]: int(r["n"]) for r in db.all("bookings_by_airline")}
    out = []
    for airline in sorted({a.airline for a in ags if a.in_force(on)}):
        mine = [a for a in ags if a.airline == airline and a.in_force(on)]
        for company in sorted({a.operating_company for a in mine}):
            services = sorted({s for a in mine if a.operating_company == company for s in a.services})
            covered_t = {t for a in mine for t in a.territories}
            territories = sorted({t for s in services for t in footprint.get(s, set())} - covered_t)
            if not territories:
                continue
            cells = coverage_matrix(airline, territories, services, ags, tps, on)
            for cand in expansion_candidates(cells, ags, caps, creds, operating_company=company,
                                             station_for_territory={t: station_in.get((company, services[0], t)) for t in territories},
                                             on=on, required_credentials=requirements):
                station = station_in.get((company, cand.service, cand.territory))
                out.append({
                    "key": f"ag|{airline}|{cand.territory}|{cand.service}|{company}", "airline_id": airline, "airline": names.get(airline),
                    "territory": cand.territory, "territory_name": COUNTRIES.get(cand.territory, (cand.territory,))[0],
                    "service": cand.service, "operating_company": company, "station": station, "actionable": cand.actionable,
                    "blockers": cand.blockers, "unknowns": cand.unknowns, "airline_bookings": bookings_by_airline.get(airline, 0),
                    "basis": "in-force agreement for this airline + verified capability at a WFC station in the territory",
                    "existing": db.scalar("opportunity_by_origin", ref=f"ag|{airline}|{cand.territory}|{cand.service}|{company}"),
                })
    out.sort(key=lambda r: (not r["actionable"], len(r["blockers"]), len(r["unknowns"]), -r["airline_bookings"], r["airline"] or "", r["territory"]))
    rec.explain_ranks("account_growth", out,
                      lambda r: (f"{'actionable' if r['actionable'] else 'not actionable'}; {len(r['blockers'])} blocker(s), "
                                 f"{len(r['unknowns'])} unknown(s); {r['airline_bookings']} booking(s) with the airline"),
                      lambda r: list(r["unknowns"]) + ([] if r["station"] else ["no WFC station in the territory"]))
    return {"status": "ok" if out else "insufficient_data", "candidates": out, "sources": sources,
            "gaps": gaps + ([] if out else ["No airline with an in-force agreement has a service WFC can deliver in a further territory"]),
            "method": "Candidates are territories where WFC holds verified capability for a service it already provides to the airline "
                      "under an in-force agreement. Appointment rights, third-party appointments, capability validity and credentials are "
                      "checked; nothing is inferred from public sources."}


# ===================================================================== forwarder sales


def forwarder_sales(db: Database, as_of: date | None = None, dormant_days: int = 90) -> dict[str, Any]:
    as_of = as_of or date.today()
    sources = [_loaded(db, d) for d in ("bookings", "quotes")]
    status, gaps = _status(sources, ["bookings"])
    if status != "ok":
        return {"status": status, "accounts": [], "sources": sources, "gaps": gaps}
    month_start = as_of.replace(day=1)
    prev_end = month_start - timedelta(days=1)
    prev_start = prev_end.replace(day=1)
    rows = []
    quotes_loaded = sources[1]["status"] != "not_connected"
    for acc in db.all("forwarder_accounts"):
        fid = acc["id"]
        pts = [(r["day"], r["kg"]) for r in db.all("forwarder_daily_weight", forwarder=fid)]
        first = pts[0][0] if pts else None
        cmp_ = mt.compare_periods(pts, prev_start, prev_end, as_of=as_of, data_start=first)
        review = mt.declining_account_review(fid, cmp_, lost_reasons={})
        last = acc["last_flight"]
        dormant = last is not None and (as_of - last).days > dormant_days
        q = db.one("forwarder_quote_stats", forwarder=fid, since=datetime.combine(as_of - timedelta(days=90), time(0), tzinfo=timezone.utc))
        decided = int(q["won"] or 0) + int(q["lost"] or 0) if q else 0
        conversion = (Decimal(int(q["won"])) / decided).quantize(Decimal("0.0001")) if (decided and q) else None
        price_losses = int(q["lost_price"] or 0) if q else 0
        b12 = int(db.scalar("forwarder_bookings_12m", forwarder=fid, since=as_of - timedelta(days=365)) or 0)
        reasons = []
        if dormant:
            reasons.append(f"dormant: no flight since {last.isoformat()} ({(as_of - last).days} days)")
        if review is not None:
            reasons.append(f"declining: chargeable weight {Decimal(review.figures['change_vs_previous']) * 100:.1f}% vs previous period"
                           + (f", {Decimal(review.figures['change_vs_year_ago']) * 100:.1f}% vs a year ago" if review.figures["change_vs_year_ago"] else ""))
        if conversion is not None and decided >= 5 and conversion < Decimal("0.25"):
            reasons.append(f"low quote conversion {conversion * 100:.0f}% ({decided} decided quotes, 90 days)")
        change = cmp_.change_vs_year_ago if cmp_.change_vs_year_ago is not None else cmp_.change_vs_previous
        rows.append({
            "forwarder_id": fid, "forwarder": acc["canonical_name"], "first_flight": acc["first_flight"], "last_flight": last,
            "dormant": dormant, "bookings_12m": b12, "comparison": cmp_.__dict__, "conversion": conversion,
            "decided_quotes": decided, "lost_on_price": price_losses, "review_reasons": reasons, "needs_review": bool(reasons),
            "facts": {"bookings_12m": b12,
                      "volume_change_anchor": 4 if dormant else (None if change is None else 3 if change < Decimal("-0.30") else
                                                                 2 if change < Decimal("-0.15") else 1 if change < Decimal("0.15") else 0),
                      "volume_change_reason": "dormant" if dormant else (f"{change * 100:.1f}% vs comparison period" if change is not None else
                                                                         "no comparable period"),
                      "conversion_anchor": None if conversion is None else (1 if conversion < Decimal("0.10") else 2 if conversion < Decimal("0.25")
                                                                            else 3 if conversion < Decimal("0.50") else 4),
                      "conversion_reason": f"{decided} decided quote(s) in 90 days" if decided else "no decided quotes" if quotes_loaded else "quotes not connected",
                      "lost_to_price_anchor": None if not decided else (0 if price_losses / decided > 0.75 else 1 if price_losses / decided > 0.5
                                                                        else 2 if price_losses / decided > 0.25 else 3 if price_losses else 4),
                      "lost_to_price_reason": f"{price_losses} of {decided} decided quote(s) lost on price" if decided else "no decided quotes"},
            "key": f"fs|{fid}|{month_start.isoformat()}",
            "existing": db.scalar("opportunity_by_origin", ref=f"fs|{fid}|{month_start.isoformat()}"),
        })
    rows.sort(key=lambda r: (not r["needs_review"], not r["dormant"], -r["bookings_12m"], r["forwarder"]))
    rec.explain_ranks("forwarder_sales", rows,
                      lambda r: ("; ".join(r["review_reasons"]) or "no review reason") + f"; {r['bookings_12m']} booking(s) in 12 months",
                      lambda r: (["quote conversion: quotes not connected" if not quotes_loaded else
                                  "quote conversion: no decided quotes in 90 days" if r["conversion"] is None else None,
                                  "comparison period: no comparable bookings" if r["comparison"].get("change_vs_previous") is None
                                  and r["comparison"].get("change_vs_year_ago") is None and not r["dormant"] else None]))
    if not quotes_loaded:
        gaps.append("quotes: not connected, so conversion is not available (not zero)")
    return {"status": "ok" if rows else "insufficient_data", "accounts": rows, "sources": sources, "gaps": gaps,
            "period": f"{prev_start.isoformat()} to {prev_end.isoformat()} vs comparison period", "as_of": as_of,
            "method": f"Dormant = no flight in {dormant_days} days. Declining = chargeable weight down 15% or more against the same "
                      "period last year (or the previous period when no prior-year data). Conversion = won / (won + lost) over 90 days; "
                      "open quotes excluded. Order: needs review, dormant, then 12-month volume."}


# ===================================================================== capacity and lanes


def capacity_lanes(db: Database, start: date, end: date) -> dict[str, Any]:
    sources = [_loaded(db, d) for d in ("bookings", "capacity")]
    status, gaps = _status(sources, ["bookings"])
    if status != "ok":
        return {"status": status, "lanes": [], "sources": sources, "gaps": gaps}
    span = (end - start).days + 1
    prev_end = start - timedelta(days=1)
    prev_start = prev_end - timedelta(days=span - 1)
    out = []
    for lane in db.all("lane_summary", start=start, end=end):
        prev = db.one("lane_period_weight", lane=lane["id"], start=prev_start, end=prev_end)
        cur_kg = lane["chargeable_kg"]
        prev_kg = prev["chargeable_kg"] if prev else None
        trend = None if (cur_kg is None or not prev_kg) else ((Decimal(cur_kg) - Decimal(prev_kg)) / Decimal(prev_kg)).quantize(Decimal("0.0001"))
        snaps = db.all("lane_capacity_series", lane=lane["id"])
        cap_change = None
        by_kind: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        for s in snaps:
            by_kind[(s["basis"], s["capacity_type"])].append(s)
        changes = []
        for (basis, ctype), series in by_kind.items():
            if len(series) >= 2:
                a, b = series[-2], series[-1]
                changes.append({"basis": basis, "type": ctype, "from": a["amount"], "to": b["amount"], "from_period": a["period_start"],
                                "to_period": b["period_start"],
                                "change": ((Decimal(b["amount"]) - Decimal(a["amount"])) / Decimal(a["amount"])).quantize(Decimal("0.0001"))
                                if a["amount"] else None})
        cap_change = changes or None
        rows = [mt.BookingRow(b["external_id"], mt.Lane(lane["origin"], lane["destination"]), b["flight_date"], b["status"], b["actual_weight_kg"],
                              b["chargeable_weight_kg"], b["volume_m3"], b["revenue"], b["currency"], None, b["fx_rate_to_reporting"],
                              b["fx_source"], b["fx_date"]) for b in db.all("lane_bookings", lane=lane["id"], start=start, end=end)]
        caps = [mt.CapacityRow(mt.Lane(lane["origin"], lane["destination"]), c["period_start"], c["period_end"], c["basis"], c["capacity_type"],
                               c["amount"]) for c in db.all("lane_capacity", lane=lane["id"], start=start, end=end)]
        util = mt.utilisation(rows, caps, mt.Lane(lane["origin"], lane["destination"]), start, end, "weight_kg", "bookable")
        money = mt.revenue_totals(rows, None)
        yields = {}
        for ccy, amount in (money.by_currency or {}).items():
            kg = sum((Decimal(r.chargeable_weight_kg) for r in rows if r.currency == ccy and r.status != "cancelled"
                      and r.chargeable_weight_kg is not None and r.revenue is not None), Decimal("0"))
            yields[ccy] = (Decimal(amount) / kg).quantize(Decimal("0.0001")) if kg else None
        lane_name = f"{lane['origin']}→{lane['destination']}"
        lane_sources = [{"dataset": s_["dataset"], "status": s_["status"], "last_success_at": s_["last_success_at"]} for s_ in sources] + \
            [{"dataset": "capacity", "snapshot": f"{c.period_start}..{c.period_end} {c.basis}/{c.capacity_type} {c.amount}"} for c in caps]
        recommendation = rec.lane_recommendation(
            lane_name, utilisation=util.value, utilisation_reason=util.reason, booked_kg=(util.detail or {}).get("numerator"),
            capacity_kg=(util.detail or {}).get("denominator"), trend=trend, previous_kg=prev_kg, current_kg=cur_kg,
            period=f"{start} to {end}", comparison_period=f"{prev_start} to {prev_end}", sources=lane_sources)
        currencies = sorted({r.currency for r in rows if r.currency and r.status != "cancelled" and r.revenue is not None})
        active = [r for r in rows if r.status != "cancelled"]
        recommendation["priority_facts"] = rec.lane_priority_facts(
            recommendation, snapshots=len(snaps), currencies=currencies, bookings_with_revenue=sum(1 for r in active if r.revenue is not None),
            bookings=len(active))
        recommendation["existing"] = db.scalar("opportunity_by_origin", ref=recommendation["key"])
        out.append({"lane_id": lane["id"], "lane": lane_name, "origin": lane["origin"],
                    "destination": lane["destination"], "chargeable_kg": cur_kg, "previous_kg": prev_kg, "trend": trend,
                    "bookings": lane["bookings"], "missing_chargeable": lane["missing_chargeable"],
                    "capacity_changes": cap_change, "utilisation": util.__dict__,
                    "yield_per_kg": yields or None, "yield_note": "per currency; currencies are never combined" if len(yields) > 1 else None,
                    "recommendation": recommendation})
    if sources[1]["status"] == "not_connected":
        gaps.append("capacity: not connected, so utilisation and capacity changes are not available (not zero)")
    recs = [x["recommendation"] for x in out if x["recommendation"]["action"]]
    order = {"add_capacity": 0, "review_allotment": 1}
    recs.sort(key=lambda r: (order.get(r["kind"], 9), -(Decimal(r["inputs"]["utilisation"]) if r["kind"] == "add_capacity" else
                                                        -Decimal(r["inputs"]["utilisation"])), r["lane"]))
    for i, r in enumerate(recs, start=1):
        r["rank"] = i
        r["rank_reason"] = (f"{r['kind']}: lanes needing capacity first (highest utilisation first), then under-used allotments "
                            "(lowest utilisation first); provisional thresholds")
    return {"status": "ok" if out else "insufficient_data", "lanes": out, "sources": sources, "gaps": gaps,
            "recommendations": recs, "units": {"weight": "kg (chargeable)", "utilisation": "ratio", "yield": "revenue per kg, per currency"},
            "period": f"{start} to {end}", "comparison_period": f"{prev_start} to {prev_end}",
            "method": "Directional lanes (A→B and B→A are separate). Trend compares chargeable kg with the preceding period of equal "
                      "length. Utilisation = booked chargeable kg / bookable capacity on the same basis and period. Yield = revenue / "
                      "chargeable kg per currency, only over bookings with both values."}


# ===================================================================== trucking and gateways


def trucking_gateways(db: Database, ship_date: date) -> dict[str, Any]:
    sources = [_loaded(db, d) for d in ("trucking", "gateway_connections")]
    stations = db.all("stations_offline")
    status, gaps = _status(sources, ["trucking", "gateway_connections"])
    if not stations:
        gaps.append("stations: no offline stations registered (Setup: stations)")
    if status != "ok":
        return {"status": status, "stations": [], "sources": sources, "gaps": gaps}
    feeders = db.all("feeders_list")
    out = []
    for st in stations:
        mine = [f for f in feeders if f["origin_station"] == st["code"]]
        options = []
        for f in mine:
            fs = FeederService(st["code"], f["gateway"], frozenset(f["departure_days"] or []), f["departure_time_local"], f["transit_minutes"])
            for c in db.all("gateway_connections_for2", gateway=f["gateway"]):
                gc = GatewayConnection(c["gateway"], frozenset(c["departure_days"] or []), c["departure_time_local"], c["connection_cutoff_minutes"])
                fz = feeder_feasibility(fs, gc, ship_date)
                options.append({"provider": f["provider"], "gateway": f["gateway"], "connection": c["flight_number"] or c["airline"] or "connection",
                                "destination": c["destination"], "result": fz.result, "reason": fz.reason, "connects_on": fz.connects_on,
                                "transit_minutes": f["transit_minutes"], "cutoff_minutes": c["connection_cutoff_minutes"]})
        options.sort(key=lambda o: ({"feasible": 0, "unresolved": 1, "infeasible": 2}[o["result"]], o["transit_minutes"] or 10**6))
        gap = None if mine else "no road feeder service recorded from this offline station"
        st_sources = [{"dataset": s_["dataset"], "status": s_["status"], "last_success_at": s_["last_success_at"]} for s_ in sources]
        recommendation = rec.station_recommendation(st["code"], st["name"], options, ship_date, gap, st_sources)
        recommendation["existing"] = db.scalar("opportunity_by_origin", ref=recommendation["key"])
        out.append({"station": st["code"], "name": st["name"], "country": st["country"],
                    "feasible": sum(o["result"] == "feasible" for o in options), "unresolved": sum(o["result"] == "unresolved" for o in options),
                    "options": options, "gap": gap, "recommendation": recommendation})
    out.sort(key=lambda s: (s["feasible"] > 0, s["station"]))
    return {"status": "ok" if out else "insufficient_data", "stations": out, "sources": sources, "gaps": gaps, "ship_date": ship_date,
            "method": "Each road feeder from an offline station is checked against every recorded connection at its gateway: the feeder "
                      "must run on the ship date, arrive before the connection cutoff and connect within 2 days. Unknown transit time or "
                      "cutoff gives 'unresolved', never feasible."}


# ===================================================================== outsourcing and training


def outsourcing_training(db: Database, on: date | None = None) -> dict[str, Any]:
    on = on or date.today()
    sources = [_loaded(db, d) for d in ("capabilities", "training_credentials")]
    status, gaps = _status(sources, ["capabilities"])
    demand = db.all("module_demand", module="outsourcing_training")
    if status != "ok":
        return {"status": status, "demand": [], "sources": sources, "gaps": gaps}
    caps = [CapabilityRecord(c["operating_company"], c["service_code"], c["station"], c["status"], c["valid_from"], c["valid_to"])
            for c in db.all("capabilities_all", company=None)]
    creds = [Credential(c["operating_company"], c["credential_type"], c["expires_on"], c["station"], c["issued_on"])
             for c in db.all("credentials_all2")]
    requirements: dict[str, list[str]] = defaultdict(list)
    for r in db.all("service_requirements_all"):
        requirements[r["service_code"]].append(r["credential_type"])
    station_country = {r["iata_code"]: r["country"] for r in db.all("airports_brief")}
    companies = sorted({c.operating_company for c in caps})
    out = []
    not_live = []
    for d in demand:
        # Verified demand only (28 Oct instruction, item 6): a live tender (open or revised), within the freight scope, and a
        # qualified record. Historical, excluded, contradictory, unverified or announced-only records are listed apart with why.
        why_not = _not_live_reason(d)
        if why_not:
            not_live.append({"opportunity_id": d["id"], "title": d["title"], "tender_status": d.get("tender_status"),
                             "freight_scope": d.get("freight_scope"), "classification": d["classification"], "why": why_not})
            continue
        svc = d["service"]
        countries = set(d["countries"] or [])
        matches = []
        for company in companies:
            stations: list[str | None] = sorted({c.station for c in caps if c.operating_company == company and c.service_code == svc
                                                 and c.station and station_country.get(c.station) in countries}) or [None]  # type: ignore[assignment]
            for st in stations:
                when = d["delivery_start"] or on
                res = capability_readiness(caps, creds, operating_company=company, service_code=svc or "", station=st, on=when,
                                           required_credentials=sorted(set(requirements.get(svc or "", [])) | set(d["required_credentials"] or [])))
                if res.matched_record is None and not res.unknowns:
                    continue
                matches.append({"operating_company": company, "station": st, "readiness": res.readiness, "blockers": res.blockers,
                                "unknowns": res.unknowns})
        order = {"ready": 0, "review_required": 1, "blocked": 2}
        matches.sort(key=lambda m: (order[str(m["readiness"])], str(m["operating_company"])))
        out.append({"opportunity_id": d["id"], "title": d["title"], "service": svc, "countries": sorted(countries),
                    "deadline_utc": d["deadline_utc"], "deadline": d["deadline_info"], "qualification_status": d["qualification_status"], "evidence": d["classification"],
                    "matches": matches, "gap": None if matches else f"no WFC company holds {svc or 'this service'} capability for these countries"})
    best = {"ready": 0, "review_required": 1, "blocked": 2}
    out.sort(key=lambda d: (best.get(str(d["matches"][0]["readiness"]), 3) if d["matches"] else 3,
                            d["deadline_utc"] is None, d["deadline_utc"] or datetime.max.replace(tzinfo=timezone.utc), str(d["title"])))
    rec.explain_ranks("outsourcing_training", out,
                      lambda d: (f"best match {d['matches'][0]['operating_company']} {d['matches'][0]['readiness']}" if d["matches"] else
                                 "no WFC match") + f"; deadline {d['deadline_utc'].date().isoformat() if d['deadline_utc'] else 'not stated'}",
                      lambda d: ([d["gap"]] if d["gap"] else list(d["matches"][0]["unknowns"])) + ([] if d["deadline_utc"] else ["deadline"]))
    return {"status": "ok" if out else "insufficient_data", "demand": out, "not_live": not_live, "sources": sources,
            "gaps": gaps + ([] if out else ["No verified outsourcing or training demand yet: run a discovery search for this capability area"]),
            "method": "Demand is an opportunity in this area backed by a supported tender. Each operating company is matched on verified "
                      "capability for the service (at a station in the delivery country, or company-wide), on the delivery date, with every "
                      "required credential held and current."}


def _not_live_reason(d: dict[str, Any]) -> str | None:
    if d.get("origin_ref"):
        return None                                   # an internal-record opportunity (not a tender): qualified by its own checks
    if d.get("classification") in ("excluded", "historical_record") or d.get("freight_scope") in ("passenger", "not_freight"):
        return f"not freight demand ({d.get('freight_scope') or d.get('classification')})"
    if d.get("classification") == "freight_candidate":
        return f"freight scope pending review ({d.get('freight_scope')})"
    st = d.get("tender_status")
    if st not in ("open", "revised"):
        return f"tender status '{st or 'unknown'}' is not live"
    return None


# ===================================================================== technology and solutions


def technology_solutions(db: Database, start: date, end: date) -> dict[str, Any]:
    sources = [_loaded(db, d) for d in ("channel_events", "bookings", "trucking")]
    status, gaps = _status(sources, ["channel_events", "bookings"])
    if status != "ok":
        return {"status": status, "adoption": [], "funnels": [], "combined": [], "sources": sources, "gaps": gaps}
    lo = datetime.combine(start, time(0), tzinfo=timezone.utc)
    hi = datetime.combine(end + timedelta(days=1), time(0), tzinfo=timezone.utc)
    adoption = db.all("digital_adoption", start=start, end=end, lo=lo, hi=hi)
    funnels = []
    for ch in db.all("channel_list"):
        evs = [ChannelEvent(e["event_type"], e["session_key"], e["booking_external_id"], e["occurred_at"], e["channel"])
               for e in db.all("channel_events_period", start=lo, end=hi, channel=ch["channel"])]
        f = booking_funnel(evs, lo, hi, ch["channel"])
        funnels.append({"channel": ch["channel"], "status": f.status, "stages": f.stages, "conversion": f.conversion,
                        "limitations": f.limitations})
    failures = db.all("integration_failures", start=lo, end=hi)
    combined = db.all("combined_service_candidates", start=start, end=end, lo=lo, hi=hi) if sources[2]["status"] != "not_connected" else []
    if sources[2]["status"] == "not_connected":
        gaps.append("trucking: not connected, so combined air + road feeder candidates are not available")
    t_sources = [{"dataset": s_["dataset"], "status": s_["status"], "last_success_at": s_["last_success_at"]} for s_ in sources]
    solutions = rec.solution_candidates(funnels, failures, adoption, combined, f"{start} to {end}", t_sources)
    for sol in solutions:
        sol["existing"] = db.scalar("opportunity_by_origin", ref=sol["key"])
    return {"status": "ok", "adoption": adoption, "funnels": funnels, "integration_failures": failures, "combined": combined,
            "solutions": solutions, "sources": sources, "gaps": gaps, "period": f"{start} to {end}",
            "method": "Adoption gap = forwarder with bookings in the period but no digital-channel events. Friction = funnel drop-off per "
                      "channel and integration failures. Combined-service candidate = forwarder active on the digital channel whose "
                      "bookings use a gateway WFC also serves by road feeder."}


# ===================================================================== network development


def network_development(db: Database, on: date | None = None) -> dict[str, Any]:
    """Coverage gaps derived from WFC's own records, plus the network candidates (partners, referrals, acquisition research)
    with their latest fit and evidence. Acquisition research is never scored, valued or counted in pipeline totals."""
    on = on or date.today()
    sources = [_loaded(db, d) for d in ("agreements", "capabilities")]
    status, gaps = _status(sources, ["agreements", "capabilities"])
    items = db.all("network_list", kind=None)
    if status != "ok":
        return {"status": status, "coverage_gaps": [], "candidates": items, "sources": sources, "gaps": gaps}
    station_country = {r["iata_code"]: r["country"] for r in db.all("airports_brief")}
    verified: set[tuple[str, str]] = set()
    for c in db.all("capabilities_all", company=None):
        if c["status"] != "verified" or (c["valid_from"] and c["valid_from"] > on) or (c["valid_to"] and c["valid_to"] < on):
            continue
        verified.add((station_country.get(c["station"], "?") if c["station"] else "*", c["service_code"]))
    derived = rec.coverage_gaps(db.all("agreements_all"), verified, on)
    existing = {(i.get("territory"), i.get("service")): i for i in items if i["kind"] == "coverage_gap"}
    for g in derived:
        cand = existing.get((g["territory"], g["service"]))
        g["candidate_id"] = str(cand["id"]) if cand else None
        g["sources"] = [{"dataset": s_["dataset"], "status": s_["status"], "last_success_at": s_["last_success_at"]} for s_ in sources]
    fit_order = {"strong": 0, "partial": 1, "weak": 2, "insufficient_evidence": 3}
    status_order = {"open": 0, "assessing": 1, "parked": 2, "closed": 3}
    ranked = sorted(items, key=lambda i: (i["kind"] == "acquisition_research", fit_order.get(str((i.get("latest_fit") or {}).get("result")), 4),
                                          -len(i.get("evidence") or []), status_order.get(str(i.get("status")), 9), str(i["id"])))
    for n, i in enumerate(ranked, start=1):
        fit = (i.get("latest_fit") or {}).get("result")
        i["rank"] = None if i["kind"] == "acquisition_research" else n
        i["rank_reason"] = ("acquisition research: kept separate, never ranked or valued" if i["kind"] == "acquisition_research" else
                            f"fit {fit or 'not assessed'}, {len(i.get('evidence') or [])} linked evidence record(s), status {i.get('status')} "
                            "(rules wfc-nd-rules-0.1, provisional)")
        i["missing"] = [] if fit else ["partner fit not assessed"]
    return {"status": "ok", "coverage_gaps": derived, "candidates": ranked, "sources": sources, "gaps": gaps, "provisional": True,
            "method": "A coverage gap is a territory and service named in an in-force WFC agreement for which no WFC company holds "
                      "verified capability at a station in that territory. Candidates are ordered by assessed fit, then evidence, then "
                      "status; acquisition research is listed separately and never ranked or valued."}


def network_gap_candidate(db: Database, key: str, meta: RequestMeta) -> dict[str, Any]:
    gap = next((g for g in network_development(db)["coverage_gaps"] if g["key"] == key), None)
    if gap is None:
        raise ModuleRejected(404, "coverage gap not found; refresh the network development view")
    if gap["candidate_id"]:
        raise ModuleRejected(409, "a network candidate already exists for this gap")
    with db.transaction() as tx:
        territory = tx.scalar("territory_ensure_country", code=gap["territory"], name=COUNTRIES.get(gap["territory"], (gap["territory"],))[0])
        service = tx.scalar("service_by_code", code=gap["service"])
        nid = tx.scalar("network_insert", kind="coverage_gap", org=None, territory=territory, service=service,
                        title=f"Coverage gap: {gap['service']} in {gap['territory']} ({', '.join(gap['airlines'])})")
        audit(tx, "network_candidate_added", meta, entity_type="network_candidate", entity_id=str(nid), detail={"from": key})
    return {"id": str(nid)}


# ===================================================================== module opportunities


@dataclass
class ModuleOpportunity:
    module: str
    origin_ref: str
    title: str
    airline_id: str | None = None
    organisation_id: str | None = None
    service_code: str | None = None
    operating_company: str | None = None
    station: str | None = None
    countries: tuple[str, ...] = ()
    facts: dict[str, Any] | None = None
    checks: tuple[tuple[str, str, bool, str], ...] = ()     # (code, result, blocking, rationale)
    notes: str | None = None


def create_module_opportunity(db: Database, mo: ModuleOpportunity, meta: RequestMeta) -> dict[str, Any]:
    from .ingestion import recompute_qualification

    with db.transaction() as tx:
        existing = tx.scalar("opportunity_by_origin", ref=mo.origin_ref)
        if existing is not None:
            raise ModuleRejected(409, "an opportunity already exists for this record")
        company = tx.scalar("company_by_name", name=mo.operating_company) if mo.operating_company else None
        service = tx.scalar("service_by_code", code=mo.service_code) if mo.service_code else None
        station = tx.scalar("airport_id", code=mo.station) if mo.station else None
        territory = None
        if len(mo.countries) == 1 and mo.countries[0] in COUNTRIES:
            territory = tx.scalar("territory_ensure_country", code=mo.countries[0], name=COUNTRIES[mo.countries[0]][0])
        opp = str(tx.scalar("opportunity_insert_module", module=mo.module, key=mo.origin_ref, title=mo.title, airline=mo.airline_id,
                            org=mo.organisation_id, territory=territory, service=service, company=company, station=station,
                            origin=mo.origin_ref, facts=mo.facts or {}, notes=mo.notes))
        for c in mo.countries:
            tx.run("opportunity_geo_internal", opp=opp, country=c)
        tx.run("check_upsert", id=opp, code="existence", result="pass", blocking=True,
               rationale=f"derived from internal records ({mo.origin_ref.split('|')[0]})", evidence=[])
        for code, result, blocking, why in mo.checks:
            tx.run("check_upsert", id=opp, code=code, result=result, blocking=blocking, rationale=why, evidence=[])
        tx.run("opportunity_history_add", id=opp, field="qualification_status", **{"from": None}, to="incomplete",
               reason=f"created from {mo.origin_ref}", session_ref=meta.session_ref)
        status = recompute_qualification(tx, opp, session_ref=meta.session_ref)
        audit(tx, "module_opportunity_created", meta, entity_type="opportunity", entity_id=opp, detail={"module": mo.module, "origin": mo.origin_ref})
    return {"opportunity_id": opp, "qualification_status": status}


def opportunity_from_account_growth(db: Database, key: str, meta: RequestMeta) -> dict[str, Any]:
    cand = next((c for c in account_growth(db)["candidates"] if c["key"] == key), None)
    if cand is None:
        raise ModuleRejected(404, "candidate not found (records may have changed); refresh the account growth view")
    rights = "pass" if not any("consent" in u or "rights" in u for u in cand["unknowns"]) and not any("prohibit" in b for b in cand["blockers"]) else \
        ("fail" if any("prohibit" in b for b in cand["blockers"]) else "unknown")
    terr = "fail" if any("exclusive" in b for b in cand["blockers"]) else ("unknown" if any("exclusivity" in u for u in cand["unknowns"]) else "pass")
    breadth = 3
    return create_module_opportunity(db, ModuleOpportunity(
        "account_growth", key, f"{cand['airline']}: extend {cand['service']} to {cand['territory_name']}", airline_id=cand["airline_id"],
        service_code=cand["service"], operating_company=cand["operating_company"], station=cand["station"], countries=(cand["territory"],),
        facts={"airline_bookings": cand["airline_bookings"], "service_breadth": breadth,
               "service_breadth_reason": "same service the airline already buys from WFC, new territory",
               "record_basis": 4 if cand["airline_bookings"] else 3,
               "record_basis_reason": "agreement + capability" + (" + bookings" if cand["airline_bookings"] else "")},
        checks=(("appointment_rights", rights, True, "; ".join(cand["blockers"] + cand["unknowns"]) or "existing agreement may be extended"),
                ("territory_conflict", terr, True, "third-party appointments checked for this territory")),
        notes=cand["basis"]), meta)


def opportunity_from_forwarder(db: Database, key: str, meta: RequestMeta) -> dict[str, Any]:
    acc = next((a for a in forwarder_sales(db)["accounts"] if a["key"] == key), None)
    if acc is None:
        raise ModuleRejected(404, "account not found; refresh the forwarder sales view")
    fresh = _loaded(db, "bookings")["status"]
    return create_module_opportunity(db, ModuleOpportunity(
        "forwarder_sales", key, f"Account review: {acc['forwarder']}", organisation_id=acc["forwarder_id"], facts=acc["facts"],
        checks=(("data_current", "pass" if fresh == "loaded" else "fail", True, f"bookings data {fresh}"),),
        notes="; ".join(acc["review_reasons"]) or "account review"), meta)


def assign_exception_owner(db: Database, exception_id: str, person_id: str | None, meta: RequestMeta) -> None:
    with db.transaction() as tx:
        if tx.scalar("exception_set_owner", id=exception_id, person=person_id) is None:
            raise ModuleRejected(404, "exception not found")
        tx.run("task_set_owner_for_source", source_type="operational_exception", source_id=exception_id, owner=person_id)
        tx.run("exception_history_add", id=exception_id, **{"from": None}, to="owner_changed",
               note=f"owner: {tx.scalar('person_name', id=person_id) if person_id else 'unassigned'}")
        audit(tx, "exception_owner_assigned", meta, entity_type="operational_exception", entity_id=exception_id)


def acknowledge_exception(db: Database, exception_id: str, note: str, meta: RequestMeta) -> None:
    with db.transaction() as tx:
        if tx.scalar("exception_acknowledge", id=exception_id) is None:
            raise ModuleRejected(409, "exception not found or not open")
        tx.run("exception_history_add", id=exception_id, **{"from": "open"}, to="acknowledged", note=note)
        audit(tx, "exception_acknowledged", meta, entity_type="operational_exception", entity_id=exception_id)


def opportunity_from_capacity(db: Database, key: str, start: date, end: date, meta: RequestMeta) -> dict[str, Any]:
    r = next((x["recommendation"] for x in capacity_lanes(db, start, end)["lanes"] if x["recommendation"]["key"] == key), None)
    if r is None or not r["action"]:
        raise ModuleRejected(404, "no capacity recommendation with an action for this lane and period; refresh the capacity view")
    fresh = all(s_.get("status") == "loaded" for s_ in r["sources"] if "status" in s_)
    origin, destination = r["lane"].split("→")
    countries = tuple(sorted({c for c in (db.scalar("airport_country", code=origin), db.scalar("airport_country", code=destination)) if c}))
    return create_module_opportunity(db, ModuleOpportunity(
        "capacity_lanes", key, f"{r['lane']}: {r['action']}", countries=countries,
        facts=r["priority_facts"] | {"recommendation": {k: r[k] for k in ("kind", "why", "inputs", "thresholds")}},
        checks=(("data_current", "pass" if fresh else "fail", True, "bookings and capacity imports within their freshness SLA" if fresh
                 else "a source dataset is stale or not connected"),),
        notes=r["why"]), meta)


def opportunity_from_trucking(db: Database, key: str, ship_date: date, meta: RequestMeta) -> dict[str, Any]:
    r = next((x["recommendation"] for x in trucking_gateways(db, ship_date)["stations"] if x["recommendation"]["key"] == key), None)
    if r is None or not r["action"]:
        raise ModuleRejected(404, "no coverage recommendation with an action for this station; refresh the trucking view")
    country = db.scalar("station_country", code=r["station"])
    return create_module_opportunity(db, ModuleOpportunity(
        "trucking_gateways", key, r["action"][:300], service_code="TRUCKING" if db.scalar("service_by_code", code="TRUCKING") else None,
        countries=(country,) if country else (),
        facts={"recommendation": {k: r.get(k) for k in ("kind", "why", "inputs", "best_option")},
               "best_authority_anchor": 4, "best_authority_reason": "WFC's own trucking and gateway records",
               "contradicting_evidence_anchor": 4, "contradicting_evidence_reason": "internal records; no contradicting record"},
        checks=(("feasibility", "pass" if r["kind"] == "coverage_available" else "review_required", True, r["why"][:500]),),
        notes=r["why"]), meta)


def opportunity_from_solution(db: Database, key: str, start: date, end: date, meta: RequestMeta) -> dict[str, Any]:
    r = next((x for x in technology_solutions(db, start, end).get("solutions", []) if x["key"] == key), None)
    if r is None or not r["action"]:
        raise ModuleRejected(404, "no solution candidate with an action for this key; refresh the technology view")
    org = db.scalar("forwarder_by_name", name=r["forwarder"]) if r.get("forwarder") else None
    return create_module_opportunity(db, ModuleOpportunity(
        "technology_solutions", key, r["action"][:300], organisation_id=org,
        facts={"solution": {k: r.get(k) for k in ("kind", "why", "evidence", "period", "thresholds")},
               "best_authority_anchor": 4, "best_authority_reason": "WFC's own channel analytics and booking records",
               "contradicting_evidence_anchor": 4, "contradicting_evidence_reason": "internal records; no contradicting record"},
        checks=(("evidence_measured", "pass", True, f"{r['kind']}: {r['why']}"[:500]),),
        notes=r["why"]), meta)
