"""Technology and solutions: booking funnel (module 8) and network fit (module 9).

The funnel is computed only from linked events: a quote request and quote
must share a session key, and a booking must reference a quoted booking
id, with timestamps in order and inside the period. If the linkage fields
are missing, the result is `instrumentation_missing` with the gap stated,
never an estimated funnel.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Sequence


@dataclass(frozen=True)
class ChannelEvent:
    event_type: Literal["search", "quote_request", "quote", "booking", "integration_failure"]
    session_key: str | None
    booking_ref: str | None
    occurred_at: datetime
    channel: str


@dataclass
class FunnelResult:
    status: Literal["computed", "instrumentation_missing", "no_data"]
    stages: dict[str, int] = field(default_factory=dict)
    conversion: dict[str, str] = field(default_factory=dict)
    limitations: list[str] = field(default_factory=list)


def booking_funnel(events: Sequence[ChannelEvent], start: datetime, end: datetime, channel: str) -> FunnelResult:
    ev = [e for e in events if e.channel == channel and start <= e.occurred_at < end]
    if not ev:
        return FunnelResult("no_data", limitations=["no channel events for this channel and period"])
    limitations: list[str] = []
    q_req = [e for e in ev if e.event_type == "quote_request"]
    quotes = [e for e in ev if e.event_type == "quote"]
    bookings = [e for e in ev if e.event_type == "booking"]
    if q_req and all(e.session_key is None for e in q_req):
        limitations.append("quote_request events carry no session_key")
    if quotes and all(e.booking_ref is None and e.session_key is None for e in quotes):
        limitations.append("quote events carry neither session_key nor booking reference")
    if bookings and all(e.booking_ref is None for e in bookings):
        limitations.append("booking events carry no booking reference")
    if not q_req or not quotes or not bookings:
        missing = [n for n, evs in (("quote_request", q_req), ("quote", quotes), ("booking", bookings)) if not evs]
        limitations.append(f"no {', '.join(missing)} events instrumented")
    if limitations:
        return FunnelResult("instrumentation_missing", limitations=limitations)

    req_time: dict[str, datetime] = {}
    for e in q_req:
        if e.session_key and (e.session_key not in req_time or e.occurred_at < req_time[e.session_key]):
            req_time[e.session_key] = e.occurred_at
    quoted: dict[str, datetime] = {}
    quoted_refs: dict[str, datetime] = {}
    for e in quotes:
        if e.session_key in req_time and e.occurred_at >= req_time[e.session_key]:
            quoted[e.session_key] = min(quoted.get(e.session_key, e.occurred_at), e.occurred_at)
            if e.booking_ref:
                quoted_refs[e.booking_ref] = e.occurred_at
    booked = {e.booking_ref for e in bookings if e.booking_ref in quoted_refs and e.occurred_at >= quoted_refs[e.booking_ref]}
    unlinked = len(bookings) - len(booked)
    if unlinked:
        limitations.append(f"{unlinked} booking(s) could not be linked to a quote and are excluded")
    stages = {"quote_requests": len(req_time), "quoted": len(quoted), "booked": len(booked)}

    def ratio(a: int, b: int) -> str:
        return "n/a" if b == 0 else f"{a / b:.4f}"

    return FunnelResult("computed", stages, {"quote_rate": ratio(len(quoted), len(req_time)),
                                             "booking_rate": ratio(len(booked), len(quoted))}, limitations)


# --------------------------------------------------------------------- network development


@dataclass(frozen=True)
class PartnerClaim:
    claim_type: str          # e.g. 'serves_territory', 'offers_service'
    value: str               # territory or service code
    status: Literal["unverified", "supported", "contradicted"]
    claim_id: str


@dataclass
class FitAssessment:
    result: Literal["strong", "partial", "weak", "insufficient_evidence"]
    covered_gaps: list[str]
    unsupported: list[str]
    evidence_claim_ids: list[str]
    rationale: list[str]
    valuation: None = None   # never invented


def partner_fit(gaps: Sequence[tuple[str, str]], claims: Sequence[PartnerClaim]) -> FitAssessment:
    """`gaps` = (territory, service) pairs WFC does not cover. A partner
    covers a gap only with SUPPORTED claims for both the territory and the
    service. Unverified claims are listed, never counted."""
    supported_t = {c.value for c in claims if c.claim_type == "serves_territory" and c.status == "supported"}
    supported_s = {c.value for c in claims if c.claim_type == "offers_service" and c.status == "supported"}
    used = [c.claim_id for c in claims if c.status == "supported"]
    unsupported = [f"{c.claim_type}={c.value} ({c.status})" for c in claims if c.status != "supported"]
    covered = [f"{t}/{s}" for t, s in gaps if t in supported_t and s in supported_s]
    rationale = [f"{len(covered)} of {len(gaps)} coverage gaps addressed by supported claims"]
    if not used:
        return FitAssessment("insufficient_evidence", [], unsupported, [], rationale + ["no supported claims about the partner"])
    if not gaps:
        return FitAssessment("weak", [], unsupported, used, rationale + ["no open coverage gaps to address"])
    share = len(covered) / len(gaps)
    result: Literal["strong", "partial", "weak"] = "strong" if share >= 0.5 else "partial" if covered else "weak"
    return FitAssessment(result, covered, unsupported, used, rationale)
