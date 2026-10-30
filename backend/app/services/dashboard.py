"""The Dashboard (30 Oct 2026, item 2): the first screen, simple and operational. What deserves attention, what changed, who is
relevant, what to do next. Four clickable summaries, a compact priority table, a short recent-changes list; the geographic visuals
as supporting context; score distributions, breakdowns and technical metrics behind an expandable detail. Opportunities and market
signals are never mixed: a company listing or a news article is not buying demand.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

from ..domain import assessment as asm
from ..domain import control_panel as cp
from ..domain import overview as ov
from ..domain import relationships as rel
from ..reference.geography import COUNTRIES
from ..repo.db import Database

RECENT_DAYS = 14


def _at(v: Any) -> datetime:
    return ov._as_dt(v) or datetime.min.replace(tzinfo=timezone.utc)


def _due(v: Any) -> date | None:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    try:
        return datetime.fromisoformat(str(v)).date()
    except ValueError:
        return None


def is_live(r: dict[str, Any]) -> bool:
    """Live: not historical or out of scope, not closed, tender not in a terminal status. The Dashboard and `/records?live=true` share it."""
    return r["record_type"] not in ("historical", "excluded") and r.get("progress") != "closed" and (r.get("tender_status") or "") not in ov.TERMINAL


def research_state(db: Database) -> dict[str, dict[str, Any]]:
    """opportunity id -> {state, state_label, tally, completed, failed, pending} for opportunities whose staged research has been run — the
    same overall state and counts as the research file (assessment.overall). Absent: not started."""
    by: dict[str, list[dict[str, Any]]] = {}
    for s in db.all("stages_all_opportunities"):
        by.setdefault(str(s["entity_id"]), []).append(s)
    totals = {str(r["entity_id"]): {k: int(r[k] or 0) for k in ("completed", "failed", "pending", "total")} for r in db.all("stage_items_totals_opportunities")}
    queued = {str(r["opportunity_id"]): int(r["n"]) for r in db.all("rdoc_queued_by_opportunity")}
    out = {}
    for oid, st in by.items():
        t = totals.get(oid, {"completed": 0, "failed": 0, "pending": 0, "total": 0})
        q = queued.get(oid, 0)
        out[oid] = {**t, "pages_queued": q, **asm.overall(st, {**t, "pending": t["pending"] + q})}
        if q:
            out[oid]["tally"] += f"; {q} page(s) queued to read"
    return out


def attention(r: dict[str, Any], research: dict[str, str], now: datetime) -> list[str]:
    """Why a live opportunity needs attention: no usable relationship, a next action due within 14 days, or research left incomplete.
    The Dashboard's fourth summary and `/records?needs=attention` share it, so the count and the list always match."""
    why = []
    if r.get("coverage") in ("none", "candidates_only"):
        why.append("no usable relationship")
    if r.get("next_action") and _due(r.get("next_action_due")) and _due(r["next_action_due"]) <= (now + timedelta(days=14)).date():
        why.append("next action due")
    state = (research.get(str(r["id"])) or {}).get("state")
    if state == "incomplete":
        why.append("research incomplete")
    if state in ("failed", "complete_with_failures"):
        why.append("research failures unresolved")
    return why


def build(db: Database, ranked: list[dict[str, Any]], *, scope: str, airports: list[dict[str, Any]], now: datetime | None = None,
          link_query: dict[str, str] | None = None) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    week = now - timedelta(days=RECENT_DAYS)
    lq = "".join(f"&{k}={v}" for k, v in sorted((link_query or {}).items()) if v)
    live = [r for r in ranked if is_live(r)]
    opps = [r for r in live if r["record_type"] in ("tender", "commercial")]
    signals = [r for r in live if r["record_type"] == "market_signal"]
    soon = sorted([r for r in opps if r.get("deadline_at") and now <= _at(r["deadline_at"]) <= now + timedelta(days=30)], key=lambda r: _at(r["deadline_at"]))
    research = research_state(db)
    needing = [(r, attention(r, research, now)) for r in opps]
    needing = [(r, w) for r, w in needing if w]
    gaps = [r for r, w in needing if "no usable relationship" in w]
    due = [r for r, w in needing if "next action due" in w]
    recent = sorted([r for r in ranked if r["record_type"] != "excluded" and _at(r["created_at"]) >= week], key=lambda r: _at(r["created_at"]), reverse=True)
    cs = db.one("cp_company_summary") or {}
    researched_companies = int((db.one("companies_researched_count") or {}).get("n") or 0)
    incomplete_research = {k for k, v in research.items() if v["state"] in ("incomplete", "failed", "complete_with_failures")}
    opp_airports = {str(r["opportunity_id"]): r["codes"] for r in db.all("opp_airport_codes")}
    panel = cp.build([dict(r) for r in ranked], COUNTRIES.get, now)

    def row(r: dict[str, Any]) -> dict[str, Any]:
        return {"id": r["id"], "kind": r["kind"], "title": r["title"], "organisation": r.get("organisation"), "organisation_id": r.get("organisation_id"),
                "countries_named": r.get("countries_named") or [], "airports": opp_airports.get(str(r["id"]), []),
                "record_type": r["record_type"], "record_type_label": r.get("record_type_label"), "tender_status_label": r.get("tender_status_label"),
                "progress": r.get("progress"), "progress_label": ov.PROGRESS_LABELS.get(r.get("progress") or "", None) if r.get("progress") else None,
                "coverage": r.get("coverage"), "coverage_label": rel.COVERAGE_LABELS.get(r.get("coverage") or "none", "Nobody identified"),
                "deadline_at": r.get("deadline_at"), "next_action": r.get("next_action") or _recommended(r, (research.get(str(r["id"])) or {}).get("state")), "next_action_due": r.get("next_action_due"),
                "next_action_is_recommendation": not r.get("next_action"), "research_incomplete": str(r["id"]) in incomplete_research,
                "research": (research.get(str(r["id"])) or {}).get("state", "not_started"),
                "research_label": (research.get(str(r["id"])) or {}).get("state_label", "Research not started"),
                "research_tally": (research.get(str(r["id"])) or {}).get("tally"),
                "priority_reason": ov.priority(r, now)[1], "category": r.get("category")}

    priority = [row(r) for r in opps[:12]]
    summaries = [
        {"key": "priority", "title": "Priority opportunities", "count": len(opps), "link": f"/opportunities?types=tender,commercial&live=true{lq}",
         "detail": f"{sum(1 for r in opps if r['record_type'] == 'tender')} tender(s), {sum(1 for r in opps if r['record_type'] == 'commercial')} commercial; "
                   f"{len(signals)} market signal(s) kept apart", "items": [{"id": r["id"], "title": r["title"], "detail": r["priority_reason"]} for r in priority[:4]]},
        {"key": "deadlines", "title": "Deadlines approaching", "count": len(soon), "link": f"/opportunities?types=tender,commercial&live=true&deadline_days=30{lq}",
         "detail": f"{len(soon)} stated deadline(s) within 30 days", "items": [{"id": r["id"], "title": r["title"], "detail": _at(r["deadline_at"]).strftime("%d %b %Y")} for r in soon[:4]]},
        {"key": "researched", "title": "Companies and people researched", "count": researched_companies,
         "link": "/companies?state=researched&scope=all",
         "detail": f"{researched_companies} companies researched ({int(cs.get('verified') or 0)} verified, {int(cs.get('awaiting_verification') or 0)} supplied awaiting verification); "
                   f"{int(cs.get('people_identified') or 0)} people identified ({int(cs.get('people_confirmed') or 0)} confirmed). A fuller profile is research completeness, not a stronger opportunity.",
         "secondary": [{"label": "People", "link": "/relationships", "count": int(cs.get("people_identified") or 0)},
                       {"label": "Awaiting verification", "link": "/companies?state=awaiting_verification&scope=all", "count": int(cs.get("awaiting_verification") or 0)}],
         "items": [{"id": c["country"], "title": COUNTRIES.get(c["country"], (c["country"],))[0], "detail": f"{c['companies']} companies, {c['verified']} verified",
                    "link": f"/companies?country={c['country']}&scope=all"} for c in db.all("cp_companies_by_country")[:4]]},
        {"key": "gaps", "title": "Research gaps and next actions", "count": len(needing),
         "link": f"/opportunities?types=tender,commercial&live=true&needs=attention{lq}",
         "detail": f"{len(gaps)} without a usable relationship; {len(due)} with a next action due within 14 days; "
                   f"{sum(1 for _, w in needing if 'research incomplete' in w)} with pending research; "
                   f"{sum(1 for _, w in needing if 'research failures unresolved' in w)} with unresolved research failures",
         "items": [{"id": r["id"], "title": r["title"], "detail": r.get("next_action") or "; ".join(w)} for r, w in needing[:4]]},
    ]
    changes = db.all("overview_changes", limit=10)
    for c in changes:
        c["label"] = _change_label(c)
    return {
        "scope": scope, "airports": airports, "generated_at": now,
        "summaries": summaries, "priority": priority,
        "signals": [row(r) for r in signals[:6]], "signals_total": len(signals),
        "recent_changes": changes, "recent": [row(r) for r in recent[:6]],
        "geo": {"by_region": panel["by_region"], "by_country": panel["by_country"][:12], "markets": panel["totals"]["markets"]},
        "detail": {"totals": panel["totals"], "score_bands": panel["score_bands"], "score_deciles": panel["score_deciles"], "score_components": panel["score_components"],
                   "by_category": panel["by_category"], "by_market": panel["by_market"], "rule": panel["rule"], "market_rule": panel["market_rule"]},
        "rule": "Opportunities (tenders and commercial) are shown apart from market signals; a company listing or a news article is never shown as confirmed demand. "
                "The priority order is a provisional points view, not a probability of winning. Research completeness is shown apart and never moves an "
                "opportunity up: a fuller profile or an available e-mail is not a stronger opportunity.",
    }


def _recommended(r: dict[str, Any], research: str | None = None) -> str:
    if research in ("failed", "complete_with_failures"):
        return "Retry the organisations whose research failed"
    if research == "incomplete":
        return "Continue the research (work is pending)"
    cov = r.get("coverage") or "none"
    if cov == "none":
        return "Research relationships (nobody identified yet)"
    if cov == "candidates_only":
        return "Confirm the identity and role of the research candidates"
    if cov == "people_confirmed":
        return "Record who at WFC knows them, or find an introduction route"
    if r.get("record_type") == "tender" and (r.get("tender_status") or "") in ("unverified", "announced"):
        return "Confirm the notice on the issuer's official channel"
    return "Decide whether to pursue and set the next action"


def _change_label(c: dict[str, Any]) -> str:
    f = c.get("field")
    if f == "record_type":
        return f"became a {ov.RECORD_TYPE_LABELS.get(c.get('to_value') or '', c.get('to_value'))}".replace("a Commercial", "a commercial")
    if f == "progress":
        return f"progress {ov.PROGRESS_LABELS.get(c.get('to_value') or '', c.get('to_value'))}"
    if f == "tender_status":
        return f"tender status {ov.TENDER_STATUS_LABELS.get(c.get('to_value') or '', c.get('to_value'))}"
    if f == "deadline":
        return "deadline changed"
    return f or "changed"

