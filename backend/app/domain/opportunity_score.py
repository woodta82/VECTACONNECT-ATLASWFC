"""Opportunity score out of 100 for the Control panel (29 Oct 2026). Framework-free.

A transparent points score built from facts ATLAS already holds about a record. It is NOT a probability of winning and NOT a
value estimate: it says how actionable and how well-placed an opportunity looks today, and every point is explained.
Provisional weights until WFC confirms them:

  Stage                   30  open tender with a deadline ahead 30; open tender, no deadline 22; commercial opportunity being
                              pursued 26, reviewed 20, new 16; record needing review 10; market signal 8
  Time to respond         15  stated deadline 21+ days away 15; 8-20 days 10; 1-7 days 5; today 2; no stated deadline 5
  Evidence reviewed       16  3 or more claims reviewed by a person 16; 1-2 claims 12; none 0
  Scope and status clear   4  freight scope established and no conflicting status 4
  Relationship position   25  existing relationship 25; introduction available 20; people confirmed 12; research candidates 6;
                              no research 0
  Source freshness        10  latest source within 30 days 10; 31-90 days 6; 91-180 days 3; older or undated 0

Closed, historical, excluded, cancelled, awarded and expired records are not scored (they are not actionable).

This is separate from the versioned four-dimension assessment in app.domain.scoring (attractiveness, evidence confidence,
readiness, risk), which stays uncombined. The Control panel score was asked for on 29 Oct 2026 as one number out of 100 per
opportunity; it is built only from the record facts listed above and shows its breakdown wherever it appears.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.domain import overview as ov

WEIGHTS = {"stage": 30, "timing": 15, "evidence": 16, "clarity": 4, "relationships": 25, "freshness": 10}
assert sum(WEIGHTS.values()) == 100

BANDS = (("strong", "Strong", 75), ("promising", "Promising", 55), ("developing", "Developing", 35), ("early", "Early", 0))

RULE = ("Provisional points score out of 100: stage 30, time to respond 15, evidence reviewed 16, scope and status clear 4, "
        "relationship position 25, source freshness 10. Not a probability of winning.")

_COVERAGE = {"existing_relationship": (25, "Existing relationship recorded"), "introduction_available": (20, "Introduction available"),
             "people_confirmed": (12, "People confirmed, no relationship yet"), "candidates_only": (6, "Research candidates only"),
             "none": (0, "No relationship research yet")}


def band(score: int) -> tuple[str, str]:
    for key, label, floor in BANDS:
        if score >= floor:
            return key, label
    return "early", "Early"


def scorable(r: dict[str, Any]) -> bool:
    return (r.get("record_type") not in ("historical", "excluded") and r.get("progress") != "closed"
            and (r.get("tender_status") or "") not in ov.TERMINAL)


def score(r: dict[str, Any], now: datetime | None = None) -> dict[str, Any] | None:
    """{score, band, band_label, components[{key,label,points,max,reason}]} for one records_list row, or None when not scored."""
    if not scorable(r):
        return None
    now = now or datetime.now(timezone.utc)
    rt, st, prog = r.get("record_type"), r.get("tender_status"), r.get("progress")
    deadline = ov._as_dt(r.get("deadline_at") or r.get("deadline_utc"))
    days = None if deadline is None else (deadline - now).total_seconds() / 86400
    comps: list[dict[str, Any]] = []

    def add(key: str, label: str, pts: int, reason: str) -> None:
        comps.append({"key": key, "label": label, "points": pts, "max": WEIGHTS[key], "reason": reason})

    # Stage
    if rt == "tender" and st in ov.LIVE and days is not None and days >= 0:
        add("stage", "Stage", 30, "Open tender with a stated deadline ahead")
    elif rt == "tender" and st in ov.LIVE:
        add("stage", "Stage", 22, "Open tender, no stated deadline" if days is None else "Open tender, stated deadline has passed")
    elif rt == "commercial" and prog in ("new", "reviewing", "pursuing"):
        pts = {"pursuing": 26, "reviewing": 20, "new": 16}[prog]
        add("stage", "Stage", pts, f"Commercial opportunity, {ov.PROGRESS_LABELS[prog].lower()}")
    elif rt == "market_signal":
        add("stage", "Stage", 8, "Market signal: potential only, nothing open to bid for yet")
    else:
        add("stage", "Stage", 10, ov.review_state(r) or "Needs review")

    # Time to respond
    if days is None or days < 0:
        add("timing", "Time to respond", 5, "No stated deadline" if days is None else "Stated deadline has passed")
    elif days >= 21:
        add("timing", "Time to respond", 15, f"Deadline in {int(days)} days")
    elif days >= 8:
        add("timing", "Time to respond", 10, f"Deadline in {int(days)} days")
    elif days >= 1:
        add("timing", "Time to respond", 5, f"Deadline in {int(days)} day(s): little time")
    else:
        add("timing", "Time to respond", 2, "Deadline today")

    # Evidence reviewed by a person
    reviewed = int(r.get("reviewed_claims") or 0)
    if reviewed >= 3:
        add("evidence", "Evidence reviewed", 16, f"{reviewed} claims reviewed by a person")
    elif reviewed >= 1:
        add("evidence", "Evidence reviewed", 12, f"{reviewed} claim(s) reviewed by a person")
    else:
        add("evidence", "Evidence reviewed", 0, "Evidence not yet reviewed by a person")

    # Scope and status clear
    scope_open = r.get("classification") == "freight_candidate" or r.get("freight_scope") in ("mixed", "unclear", "conflicting")
    conflict = st == "contradictory" or r.get("status_conflict") in ("true", True)
    if scope_open or conflict:
        add("clarity", "Scope and status clear", 0, "Sources conflict on the status" if conflict else "Freight scope not yet established")
    else:
        add("clarity", "Scope and status clear", 4, "Freight scope established; no conflicting status")

    # Relationship position
    pts, why = _COVERAGE.get(r.get("coverage") or "none", (0, "No relationship research yet"))
    add("relationships", "Relationship position", pts, why)

    # Source freshness
    src = ov._as_dt(r.get("source_date"))
    age = None if src is None else (now - src).total_seconds() / 86400
    if age is None:
        add("freshness", "Source freshness", 0, "Source date not stated")
    elif age <= 30:
        add("freshness", "Source freshness", 10, f"Latest source {max(0, int(age))} day(s) old")
    elif age <= 90:
        add("freshness", "Source freshness", 6, f"Latest source {int(age)} days old")
    elif age <= 180:
        add("freshness", "Source freshness", 3, f"Latest source {int(age)} days old")
    else:
        add("freshness", "Source freshness", 0, f"Latest source {int(age)} days old")

    total = sum(c["points"] for c in comps)
    key, label = band(total)
    return {"score": total, "band": key, "band_label": label, "components": comps}
