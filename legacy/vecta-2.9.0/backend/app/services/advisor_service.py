"""Executive AI Advisor (read-only) — Phase 3.1.

A strategic adviser, not a chatbot. Three properties make that difference
real rather than a matter of tone:

**1. The response is a typed structure, not prose.** Six named fields,
rendered in fixed order, each capped at 40 words. "Avoid long
conversational answers" becomes a guarantee rather than a prompt
instruction the model may ignore on a verbose day.

**2. Answers are computed, not generated.** Every question below is
answered from stored data — focus scores, change events, score history.
No AI call, no cost, instant. The advisor is available as often as you
like, which is what makes it usable in a two-minute morning read.

**3. Every claim carries its kind.** Verified fact, AI interpretation,
assumption, prediction, recommendation — the same vocabulary as the rest
of the platform. An advisor that blurs those would undo the discipline
Phase 2 exists to enforce.

Scope is deliberately restricted to a known set of questions. An open
text box invites questions the data cannot support, and one confidently
thin answer costs more trust than a narrow scope costs utility.
"""
from __future__ import annotations

import logging

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from ..models import Contact, Opportunity
from ..models_memory import ChangeEvent, ExecutiveFocus, ScoreHistory
from ..models_phase2 import (
    OpportunityEvidence,
    PursuitPriority,
    QualificationAssessment,
    ScoreAssessment,
)
from ..timeutils import utcnow
from ..vocabulary import ADVISOR_SECTION_WORD_LIMIT, claim_label
from . import briefing_service, change_detector, focus_service, profile_service

logger = logging.getLogger("atlas.advisor")



def _clip(text: str, limit: int = ADVISOR_SECTION_WORD_LIMIT) -> str:
    """Hard word cap. Structural brevity, not requested brevity."""
    words = (text or "").split()
    if len(words) <= limit:
        return text
    return " ".join(words[:limit]).rstrip(",;.") + "…"


def _claim(text: str, kind: str, source: str | None = None) -> dict:
    """Every statement carries its classification and, where relevant, its
    source. This is what separates the advisor from a chatbot."""
    return {
        "text": _clip(text),
        "kind": kind,
        "kind_label": claim_label(kind),
        "source": source,
    }


def _response(question: str, *, recommendation: dict, key_reasons: list[dict],
              supporting_evidence: list[dict], risks: list[dict],
              assumptions: list[dict], suggested_actions: list[dict],
              answerable: bool = True, unanswerable_reason: str | None = None,
              models: list[str] | None = None,
              confidence: dict | None = None) -> dict:
    """The fixed six-section shape. Always the same order, always all six
    keys present — an absent section renders as "none", which is itself
    information."""
    from ..readiness_index import cite

    # Every recommendation cites the models behind it. Advice with no
    # citation is opinion, and the platform's whole claim is that its
    # advice is not opinion.
    citations = cite(*(models or []))

    return {
        "question": question,
        "answerable": answerable,
        "unanswerable_reason": unanswerable_reason,
        "generated_at": utcnow().isoformat(),
        "profile_version": None,   # set by the caller
        "ai_calls_used": 0,
        "intelligence_models": citations,
        "confidence": confidence,
        "sections": {
            "1_recommendation": recommendation,
            "2_key_reasons": key_reasons,
            "3_supporting_evidence": supporting_evidence,
            "4_risks": risks,
            "5_assumptions": assumptions,
            "6_suggested_actions": suggested_actions,
        },
    }


def _no_data(question: str, reason: str) -> dict:
    """Saying "I cannot answer that yet" is a better answer than a thin
    one. The first confidently-wrong response costs more trust than a
    dozen honest refusals."""
    return _response(
        question,
        recommendation=_claim(f"No recommendation available — {reason}", "verified_fact"),
        key_reasons=[], supporting_evidence=[], risks=[], assumptions=[],
        suggested_actions=[],
        answerable=False, unanswerable_reason=reason,
        models=["DCS"],
    )


# ------------------------------------------- Q1: what should I focus on?

def what_should_i_focus_on(db: Session) -> dict:
    question = "What should I focus on today?"
    top = focus_service.top_focus(db, limit=3)
    if not top:
        return _no_data(question, "no opportunities have an Executive Focus score yet")

    opp, focus = top[0]
    others = top[1:]

    reasons = [_claim(focus.explanation or focus.band_label, "ai_interpretation")]
    for driver in (focus.primary_drivers or "").split(", ")[:2]:
        if driver:
            reasons.append(_claim(f"Driver: {driver}", "ai_interpretation"))

    evidence = []
    summary = briefing_service._evidence_summary(
        db.query(OpportunityEvidence).filter_by(opportunity_id=opp.id).all()
    )
    evidence.append(
        _claim(f"{opp.title}: {summary['label']}", "verified_fact",
               source=(summary.get("strongest_source") or {}).get("url"))
    )

    risks = []
    if opp.deadline:
        days = (opp.deadline - utcnow().date()).days
        if days <= 14:
            risks.append(_claim(f"Deadline in {days} days — the window is closing.", "verified_fact"))
    if opp.requires_human_review:
        risks.append(_claim(f"Flagged for review: {opp.human_review_reason}", "verified_fact"))

    assumptions = []
    if focus.is_actionable and not db.query(Contact).filter_by(opportunity_id=opp.id).count():
        assumptions.append(
            _claim("Relationship position unknown — no contacts mapped, so access is unverified.",
                   "assumption")
        )

    actions = [_claim(briefing_service._next_action(
        db, opp,
        db.query(QualificationAssessment).filter_by(opportunity_id=opp.id).first(),
        focus), "recommendation")]
    for other, other_focus in others:
        actions.append(_claim(f"Then: {other.title} ({other_focus.band_label})", "recommendation"))

    return _response(
        question,
        recommendation=_claim(
            f"Focus on {opp.title} — {focus.band_label}, Executive Focus {focus.score}.",
            "recommendation",
        ),
        key_reasons=reasons,
        supporting_evidence=evidence,
        risks=risks,
        assumptions=assumptions,
        suggested_actions=actions,
        models=["EFS", "DCS"],
    )


# ----------------------------------------------- Q2: what changed overnight?

def what_changed(db: Session, since: datetime | None = None) -> dict:
    question = "What changed overnight?"
    since = since or (utcnow() - timedelta(days=1))
    events = change_detector.changes_since(db, since, limit=20)
    if not events:
        return _response(
            question,
            recommendation=_claim("Nothing material changed. No action required.", "verified_fact"),
            key_reasons=[], supporting_evidence=[], risks=[], assumptions=[],
            suggested_actions=[],
            models=["EFS"],
        )

    high = [e for e in events if e.materiality == "high"]
    reasons = [_claim(e.summary, "verified_fact") for e in (high or events)[:3]]

    risks = [
        _claim(e.summary, "verified_fact")
        for e in events
        if e.event_type in ("went_stale", "assumption_invalidated", "deadline_approaching")
    ][:3]

    return _response(
        question,
        recommendation=_claim(
            f"{len(events)} material change(s), {len(high)} significant. "
            f"{'Review the significant ones first.' if high else 'Nothing urgent.'}",
            "recommendation",
        ),
        key_reasons=reasons,
        supporting_evidence=[
            _claim(f"{e.summary} ({e.occurred_at.strftime('%d %b') if e.occurred_at else ''})",
                   "verified_fact")
            for e in events[:3]
        ],
        risks=risks,
        assumptions=[],
        suggested_actions=[
            _claim(f"Open: {e.summary}", "recommendation") for e in (high or events)[:2]
        ],
        models=["EFS"],
    )


# --------------------------------- Q3: which deserves immediate attention?

def immediate_attention(db: Session) -> dict:
    question = "Which opportunity deserves immediate attention?"
    rows = (
        db.query(Opportunity, ExecutiveFocus)
        .join(ExecutiveFocus, ExecutiveFocus.opportunity_id == Opportunity.id)
        .filter(ExecutiveFocus.is_actionable.is_(True), ExecutiveFocus.band == "act_now")
        .order_by(ExecutiveFocus.score.desc())
        .all()
    )
    if not rows:
        return _response(
            question,
            recommendation=_claim(
                "Nothing requires immediate attention. The highest-focus items can wait this week.",
                "recommendation",
            ),
            key_reasons=[_claim("No opportunity is in the 'Act now' band.", "verified_fact")],
            supporting_evidence=[], risks=[], assumptions=[], suggested_actions=[],
            models=["EFS"],
        )

    opp, focus = rows[0]
    priority = db.query(PursuitPriority).filter_by(opportunity_id=opp.id).first()
    reconciliation = briefing_service._reconcile(focus, priority)

    reasons = [_claim(focus.explanation or "", "ai_interpretation")]
    if reconciliation:
        reasons.append(_claim(reconciliation, "ai_interpretation"))

    return _response(
        question,
        recommendation=_claim(f"{opp.title} — Executive Focus {focus.score}, act now.",
                              "recommendation"),
        key_reasons=reasons,
        supporting_evidence=[
            _claim(f"Deadline {opp.deadline.isoformat()}" if opp.deadline
                   else "No deadline recorded", "verified_fact")
        ],
        risks=[_claim(briefing_service._cost_of_waiting(opp, focus)["summary"], "verified_fact")],
        assumptions=[],
        suggested_actions=[
            _claim(briefing_service._next_action(
                db, opp,
                db.query(QualificationAssessment).filter_by(opportunity_id=opp.id).first(),
                focus), "recommendation")
        ],
        models=["EFS", "RCI"],
    )


# --------------------------------------- Q4/Q5: improving / deteriorating

def _moved(db: Session, since: datetime, improving: bool) -> list[tuple[Opportunity, ScoreHistory]]:
    rows = (
        db.query(Opportunity, ScoreHistory)
        .join(ScoreHistory, ScoreHistory.opportunity_id == Opportunity.id)
        .filter(ScoreHistory.recorded_at >= since,
                ScoreHistory.delta_from_previous.is_not(None))
        .all()
    )
    filtered = [
        (o, h) for o, h in rows
        if (h.delta_from_previous > 0) == improving and abs(h.delta_from_previous) >= 5
    ]
    filtered.sort(key=lambda r: abs(r[1].delta_from_previous), reverse=True)
    return filtered[:5]


def improving(db: Session, since: datetime | None = None) -> dict:
    question = "Which opportunities have improved?"
    since = since or (utcnow() - timedelta(days=7))
    moves = _moved(db, since, improving=True)
    if not moves:
        return _no_data(question, "no score improvements recorded in the period")

    return _response(
        question,
        recommendation=_claim(
            f"{len(moves)} opportunit{'y has' if len(moves)==1 else 'ies have'} improved. "
            f"Strongest: {moves[0][0].title}.",
            "recommendation",
        ),
        key_reasons=[
            _claim(f"{o.title}: {h.dimension.replace('_',' ')} +{h.delta_from_previous}",
                   "verified_fact")
            for o, h in moves[:3]
        ],
        supporting_evidence=[
            _claim(f"{h.dimension.replace('_',' ')} now {h.score} ({h.change_reason})",
                   "verified_fact")
            for _, h in moves[:2]
        ],
        risks=[],
        assumptions=[
            _claim("Improvement reflects rescoring, not necessarily new external activity.",
                   "assumption")
        ],
        suggested_actions=[
            _claim(f"Reassess pursuit posture for {moves[0][0].title}.", "recommendation")
        ],
        models=["EFS", "RMI"],
    )


def deteriorating(db: Session, since: datetime | None = None) -> dict:
    question = "Which opportunities are deteriorating?"
    since = since or (utcnow() - timedelta(days=7))
    moves = _moved(db, since, improving=False)

    stale = [
        e for e in change_detector.changes_since(db, since, limit=100)
        if e.event_type == "went_stale"
    ]

    if not moves and not stale:
        return _response(
            question,
            recommendation=_claim("Nothing is deteriorating. No action required.", "verified_fact"),
            key_reasons=[], supporting_evidence=[], risks=[], assumptions=[],
            suggested_actions=[],
            models=["RMI"],
        )

    headline = (
        f"{moves[0][0].title} has fallen {abs(moves[0][1].delta_from_previous)} points."
        if moves else f"{len(stale)} opportunit{'y is' if len(stale)==1 else 'ies are'} going stale."
    )

    return _response(
        question,
        recommendation=_claim(f"Attention needed. {headline}", "recommendation"),
        key_reasons=[
            _claim(f"{o.title}: {h.dimension.replace('_',' ')} {h.delta_from_previous}",
                   "verified_fact")
            for o, h in moves[:2]
        ] + [_claim(e.summary, "verified_fact") for e in stale[:2]],
        supporting_evidence=[
            _claim(f"{h.change_reason}: {h.change_note or 'no note recorded'}", "verified_fact")
            for _, h in moves[:2]
        ],
        risks=[
            _claim("Opportunities rarely fail loudly — they lapse. Inactivity is the risk here.",
                   "ai_interpretation")
        ] if stale else [],
        assumptions=[],
        suggested_actions=[
            _claim(f"Set a next action and owner for {o.title}.", "recommendation")
            for o, _ in moves[:1]
        ] + [
            _claim("Formally defer anything not being actively worked.", "recommendation")
        ] if stale else [],
        models=["EFS", "RMI"],
    )


# ------------------------------- Q6: which relationship should I strengthen?

def relationship_to_strengthen(db: Session) -> dict:
    question = "Which relationship should I strengthen?"
    watchlist = briefing_service.relationship_watchlist(db, limit=3)
    if not watchlist:
        return _no_data(question, "no relationship gaps identified on active opportunities")

    top = watchlist[0]
    return _response(
        question,
        recommendation=_claim(
            f"{top['recommended_engagement']} — {top['opportunity_title']}.", "recommendation"
        ),
        key_reasons=[
            _claim(f"Relationship position: {top['current_strength']}.", "ai_interpretation"),
            _claim(f"Executive Focus {top['focus_score']} on this opportunity.", "verified_fact"),
        ],
        supporting_evidence=[
            _claim(f"{top['contacts_mapped']} contact(s) mapped.", "verified_fact")
        ],
        risks=[
            _claim(
                f"No engagement for {top['last_engagement_days']} days."
                if top.get("last_engagement_days") else "Engagement recency unknown.",
                "verified_fact",
            )
        ],
        assumptions=[
            _claim(
                "Relationship position is inferred from contact role text, not verified "
                "stakeholder data. Full mapping arrives in Phase 3.2.",
                "assumption",
            )
        ],
        suggested_actions=[
            _claim(top["expected_commercial_benefit"], "recommendation"),
            _claim("Log the engagement once made, so the position is evidenced.", "recommendation"),
        ],
        models=["RCI", "RMI"],
    )


# ---------------------------------------------------------------- registry

QUESTIONS = {
    "focus_today": ("What should I focus on today?", what_should_i_focus_on),
    "what_changed": ("What changed overnight?", what_changed),
    "immediate_attention": ("Which opportunity deserves immediate attention?", immediate_attention),
    "improving": ("Which opportunities have improved?", improving),
    "deteriorating": ("Which opportunities are deteriorating?", deteriorating),
    "relationship": ("Which relationship should I strengthen?", relationship_to_strengthen),
}


def ask(db: Session, question_key: str, since: datetime | None = None) -> dict:
    """Answers one of the known questions.

    Restricted by design: the registry is the whole surface. An open text
    box would invite questions the data cannot support, and the first
    confidently thin answer would cost more trust than this narrowness
    costs utility.
    """
    entry = QUESTIONS.get(question_key)
    if entry is None:
        return _no_data(
            question_key,
            f"unknown question. Available: {', '.join(QUESTIONS)}",
        )
    label, handler = entry
    try:
        result = handler(db, since) if handler in (what_changed, improving, deteriorating) else handler(db)
    except TypeError:
        result = handler(db)
    result["profile_version"] = profile_service.active_version(db)
    return result


def available_questions(db: Session) -> list[dict]:
    """Questions plus whether the data can answer them, so the UI never
    offers one that would return an empty response."""
    has_focus = db.query(ExecutiveFocus).count() > 0
    has_history = db.query(ScoreHistory).count() > 0
    has_changes = db.query(ChangeEvent).count() > 0
    has_contacts = db.query(Contact).count() > 0

    availability = {
        "focus_today": has_focus,
        "what_changed": has_changes,
        "immediate_attention": has_focus,
        "improving": has_history,
        "deteriorating": has_history or has_changes,
        "relationship": has_focus,
    }
    return [
        {"key": key, "question": label, "available": availability.get(key, False)}
        for key, (label, _) in QUESTIONS.items()
    ]
