"""Overview ordering and plain-language labels (28 Oct 2026 refocus). Framework-free.

Priority is an ORDER with a stated reason, not a score or a probability. Rule (provisional until WFC confirms it):
  1. live tender or procurement opportunities (open or revised) with a stated deadline still ahead, soonest first;
  2. commercial opportunities the team is tracking (new, reviewing or pursuing);
  3. records that need review before anyone relies on them (announced, unverified, contradictory, freight scope pending);
  4. market signals (potential only);
  5. closed, expired, cancelled, awarded and historical records.
Within a tier: more reviewed evidence first, then an existing relationship or available introduction, then the newest.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

RULE = ("provisional rule: live tenders by deadline, then tracked commercial opportunities, then records needing review, "
        "then market signals, then closed or historical; within each, reviewed evidence and relationship coverage first")

LIVE = ("open", "revised")
NEEDS_REVIEW = ("announced", "unverified", "contradictory", "unknown")
TERMINAL = ("cancelled", "awarded", "closed", "expired", "historical")

RECORD_TYPE_LABELS = {"tender": "Tender or procurement opportunity", "commercial": "Commercial opportunity",
                      "market_signal": "Market signal", "historical": "Historical intelligence", "excluded": "Excluded (outside freight scope)"}
TENDER_STATUS_LABELS = {"open": "Open", "revised": "Open (revised)", "announced": "Announced, current status unverified",
                        "unverified": "Unverified", "contradictory": "Conflicting sources: needs review", "expired": "Expired",
                        "cancelled": "Cancelled", "awarded": "Awarded", "closed": "Closed", "historical": "Historical",
                        "unknown": "Status not stated"}
PROGRESS = ("new", "reviewing", "pursuing", "on_hold", "closed")
PROGRESS_LABELS = {"new": "New", "reviewing": "Reviewing", "pursuing": "Pursuing", "on_hold": "On hold", "closed": "Closed"}

CATEGORY_LABELS = {
    "airline_representation": "Airline representation", "account_growth": "Account growth", "forwarder_sales": "Forwarder sales",
    "capacity_lanes": "Capacity and trade lanes", "service_operations": "Service and operations",
    "trucking_gateways": "Trucking and gateways", "outsourcing_training": "Outsourcing and training",
    "technology_solutions": "Technology and solutions", "network_development": "Network development",
}


def _as_dt(v: Any) -> datetime | None:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    try:
        d = datetime.fromisoformat(str(v))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def review_state(r: dict[str, Any]) -> str | None:
    """Why a record needs a person's review before anyone relies on it (None when it does not)."""
    st = r.get("tender_status")
    if st == "contradictory" or r.get("status_conflict") in ("true", True):
        return "Sources conflict on the status: review the evidence"
    if st == "announced":
        return "Announced; the current status is not confirmed by the source"
    if st == "unverified":
        return "Status not verified by a dated source"
    if r.get("classification") == "freight_candidate" or r.get("freight_scope") in ("mixed", "unclear", "conflicting"):
        return "Freight scope not yet established"
    if r.get("record_type") in ("tender", "market_signal") and int(r.get("reviewed_claims") or 0) == 0:
        return "Evidence not yet reviewed by a person"
    return None


def priority(r: dict[str, Any], now: datetime | None = None) -> tuple[tuple, str]:
    """(sort key, explanation) for one record from records_list."""
    now = now or datetime.now(timezone.utc)
    rt, st, prog = r.get("record_type"), r.get("tender_status"), r.get("progress")
    deadline = _as_dt(r.get("deadline_at") or r.get("deadline_utc"))
    days = None if deadline is None else (deadline - now).total_seconds() / 86400
    reasons: list[str] = []
    if prog == "closed" or rt == "historical" or st in TERMINAL:
        tier, reasons = 4, [RECORD_TYPE_LABELS.get(str(rt), str(rt)) + ("; " + TENDER_STATUS_LABELS.get(str(st), str(st)) if st else "")
                            + ("; closed" if prog == "closed" else "")]
    elif rt == "tender" and st in LIVE and days is not None and days >= 0:
        tier = 0
        reasons.append(f"Open tender, deadline in {int(days)} day(s)" if days >= 1 else "Open tender, deadline today")
    elif rt == "tender" and st in LIVE:
        tier = 1
        reasons.append("Open tender, no stated deadline")
    elif rt == "commercial" and prog in ("new", "reviewing", "pursuing"):
        tier = 1
        reasons.append(f"Commercial opportunity being tracked ({PROGRESS_LABELS.get(str(prog), str(prog)).lower()})")
    elif rt == "market_signal":
        tier = 3
        reasons.append("Market signal: potential only, nothing open to bid for yet")
    else:
        tier = 2
        reasons.append(review_state(r) or "Needs review")
    reviewed = int(r.get("reviewed_claims") or 0)
    if tier < 4:
        reasons.append("evidence reviewed by a person" if reviewed else "evidence not yet reviewed")
        cov = r.get("coverage") or "none"
        reasons.append({"existing_relationship": "existing relationship recorded", "introduction_available": "introduction available",
                        "people_confirmed": "people confirmed, no relationship yet", "candidates_only": "research candidates only",
                        "none": "no relationship research yet"}.get(cov, cov))
    cov_rank = {"existing_relationship": 0, "introduction_available": 1, "people_confirmed": 2, "candidates_only": 3}.get(r.get("coverage") or "", 4)
    created = _as_dt(r.get("created_at")) or now
    key = (tier, days if (tier == 0 and days is not None) else 10**6, 0 if reviewed else 1, cov_rank, -created.timestamp(), str(r.get("id")))
    return key, "; ".join(reasons)


def rank(records: list[dict[str, Any]], now: datetime | None = None) -> list[dict[str, Any]]:
    keyed = []
    for r in records:
        k, why = priority(r, now)
        r["priority_reason"] = why
        r["review_state"] = review_state(r)
        keyed.append((k, r))
    keyed.sort(key=lambda kr: kr[0])
    out = [r for _, r in keyed]
    for i, r in enumerate(out, start=1):
        r["priority_rank"] = i
    return out


# ------------------------------------------------------------------ the system's commercial interpretation (never a source fact)
_WHY = {
    "airline_representation": "A representation mandate (GSSA, GSA or cargo sales agency) for {org}{where}: WFC could bid to represent "
                              "the airline's cargo there, or extend an existing mandate.",
    "account_growth": "An airline WFC may already work with is active{where}: a possible expansion of territory or services.",
    "forwarder_sales": "Forwarder activity{where} that could become cargo bookings for airlines WFC represents.",
    "capacity_lanes": "A change in capacity or routes{where}: new space to sell, or a lane that may need representation or feeder support.",
    "service_operations": "A service or operations development{where} that could need handling, supervision or reservation support.",
    "trucking_gateways": "Road-feeder or gateway development{where}: a possible trucking or gateway service for WFC.",
    "outsourcing_training": "Outsourced services or training demand{where} that WFC's group companies could supply.",
    "technology_solutions": "A digital or technology change{where} that could open a solution or integration opportunity.",
    "network_development": "A coverage gap, partner or acquisition prospect{where} for WFC's network.",
}


def interpretation(record: dict[str, Any], countries: list[str]) -> dict[str, Any]:
    """What ATLAS infers about relevance to WFC, labelled as interpretation, with what remains unconfirmed."""
    where = f" in {', '.join(countries)}" if countries else ""
    org = record.get("organisation") or "the organisation named"
    rt = record.get("record_type")
    text = _WHY.get(str(record.get("module")), "A development that may be relevant to WFC{where}.").format(org=org, where=where)
    status = record.get("tender_status")
    if rt in ("tender", "historical") and status in TERMINAL:
        text = (f"The source states this tender is {TENDER_STATUS_LABELS.get(str(status), str(status)).lower()}: it cannot be bid for as "
                f"announced. What was relevant: {text[0].lower()}{text[1:]} Recorded people and relationships remain useful if it is "
                "reissued or for related work.")
    unconfirmed: list[str] = []
    if rt in ("market_signal", "commercial"):
        unconfirmed.append("No open tender or procurement is confirmed: this is potential, not a bid opportunity")
    rs = review_state(record)
    if rs:
        unconfirmed.append(rs)
    if not countries:
        unconfirmed.append("Geography not established by the source")
    if rt == "tender" and not (record.get("deadline_at") or record.get("deadline_utc") or record.get("deadline_info")):
        unconfirmed.append("No submission deadline stated")
    for g in record.get("gaps") or []:
        if isinstance(g, str) and g not in unconfirmed:
            unconfirmed.append(g)
    return {"label": "ATLAS interpretation (not a source fact)", "text": text, "unconfirmed": unconfirmed[:8],
            "category": CATEGORY_LABELS.get(str(record.get("module")), str(record.get("module"))),
            "record_type_label": RECORD_TYPE_LABELS.get(str(rt), str(rt))}
