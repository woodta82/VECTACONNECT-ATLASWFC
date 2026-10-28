"""Executive Briefing — Phase 3.1.

Assembles the seven sections of the daily briefing. **Zero AI calls, zero
cost, target under 1.5 seconds.**

That constraint drives the design. A briefing that costs money cannot run
daily under manual-only AI discipline; one that takes eleven seconds
loses to email. So every section reads stored, pre-computed data —
`ExecutiveFocus` for priorities, `ChangeEvent` for movement, existing
Phase 2 tables for everything else.

Where the AI *could* add value — a written narrative summary — it is
offered as an explicit, costed action rather than run automatically. The
briefing works completely without it.

Section order is fixed and matches the executive hierarchy: decision
first, supporting detail last.
"""
from __future__ import annotations

import json
import logging
import time
from datetime import date, datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models import Contact, Opportunity, ScanRun
from ..models_memory import AssumptionLedger, ChangeEvent, ExecutiveFocus, Materiality
from ..models_phase2 import (
    CommercialValue,
    OpportunityEvidence,
    PursuitPriority,
    QualificationAssessment,
    QualificationBlocker,
    QualificationChecklistItem,
    ScoreAssessment,
)
from ..taxonomy import QUALIFICATION_STATE_LABELS, VERTICAL_V2_INFO
from ..timeutils import as_aware, utcnow
from . import change_detector, focus_service, profile_service

logger = logging.getLogger("atlas.briefing")

# Slow-briefing threshold. The design budget is 1.5s; anything past this
# is logged so a regression surfaces before an executive notices it.
SLOW_SECTION_MS = 300


def _safe_section(name: str, fn, fallback):
    """Runs one briefing section in isolation.

    The briefing is the landing page. Without this, a single malformed row
    in market intelligence takes down priorities, risks and everything
    else — the executive opens ATLAS and sees a 500 instead of the two
    things they needed. A degraded section is recoverable; a blank page is
    not.

    Failures are logged with the section name so the cause is findable,
    and the section reports its own failure rather than silently returning
    empty, which would look like "nothing to report".
    """
    started = time.perf_counter()
    try:
        result = fn()
        elapsed_ms = (time.perf_counter() - started) * 1000
        if elapsed_ms > SLOW_SECTION_MS:
            logger.warning("Briefing section '%s' took %.0fms", name, elapsed_ms)
        return result
    except Exception:  # noqa: BLE001 — one section must never break the page
        logger.exception("Briefing section '%s' failed", name)
        return fallback


def _label(mapping: dict, key: str | None, field: str = "label") -> str | None:
    if not key:
        return None
    entry = mapping.get(key)
    return entry.get(field, key) if isinstance(entry, dict) else (entry or key)


# ---------------------------------------------- 1. executive summary

def executive_summary(db: Session, since: datetime) -> dict:
    """The header an executive reads before anything else: what changed,
    what needs attention, what can wait."""
    summary = change_detector.change_summary(db, since)

    focus_rows = (
        db.query(ExecutiveFocus).filter(ExecutiveFocus.is_actionable.is_(True)).all()
    )
    act_now = sum(1 for f in focus_rows if f.band == "act_now")
    this_week = sum(1 for f in focus_rows if f.band == "this_week")

    deadlines_30 = (
        db.query(Opportunity)
        .filter(
            Opportunity.deadline.is_not(None),
            Opportunity.deadline >= date.today(),
            Opportunity.deadline <= date.today() + timedelta(days=30),
        )
        .count()
    )

    stale = sum(
        1
        for e in change_detector.changes_since(db, since, limit=200)
        if e.event_type == "went_stale"
    )

    awaiting = (
        db.query(QualificationAssessment)
        .filter(QualificationAssessment.state == "verification_required")
        .count()
    )

    # A briefing names things; a status report counts them. "2
    # opportunities need action" tells an executive nothing they can act
    # on — "Saudi Coach Education needs action today, the consultation
    # closes in 9 days" does. So the headline leads with the single most
    # pressing item by name, and only then summarises the rest.
    #
    # Composed, not generated: this must cost nothing and run instantly.
    top = focus_service.top_focus(db, limit=1)
    lines: list[str] = []

    if top:
        opp, focus = top[0]
        if focus.band in ("act_now", "this_week"):
            urgency = ""
            if opp.deadline:
                days = (opp.deadline - date.today()).days
                if days <= 30:
                    urgency = f" — {days} days to the deadline"
            lines.append(
                f"{opp.title} needs your attention"
                f"{' today' if focus.band == 'act_now' else ' this week'}{urgency}."
            )

    remaining = max(0, (act_now + this_week) - (1 if lines else 0))
    if remaining:
        lines.append(
            f"{remaining} other opportunit{'y' if remaining == 1 else 'ies'} "
            f"also need{'s' if remaining == 1 else ''} a decision."
        )
    elif not lines:
        lines.append("Nothing requires immediate executive action.")

    if summary["high_materiality"]:
        significant = [
            e for e in change_detector.changes_since(db, since, limit=20)
            if e.materiality == Materiality.HIGH.value
        ]
        if significant:
            lines.append(f"Most significant change: {significant[0].summary.lower()}.")
    elif summary["total"]:
        lines.append(f"{summary['total']} minor change(s) since your last review.")

    if stale:
        lines.append(
            f"{stale} qualified opportunit{'y is' if stale == 1 else 'ies are'} "
            "going stale through inactivity."
        )
    if awaiting:
        lines.append(
            f"{awaiting} cannot progress until qualification is completed."
        )

    nothing_outstanding = (
        act_now == 0 and this_week == 0 and stale == 0 and summary["high_materiality"] == 0
    )
    if nothing_outstanding:
        lines = [
            "Nothing further requires your attention today.",
            "Pipeline is current, no deadlines are imminent, and nothing is going stale.",
        ]

    return {
        "headline": " ".join(lines),
        # Step 7 of the executive workflow is "leave the platform". A
        # product designed for short sessions should say plainly when it
        # is finished, rather than inviting further browsing.
        "is_complete": nothing_outstanding,
        "completion_message": (
            "You are up to date. Next review tomorrow, or when a scan is run."
            if nothing_outstanding else None
        ),
        "changes_since": since.isoformat(),
        "counts": {
            "material_changes": summary["total"],
            "significant_changes": summary["high_materiality"],
            "act_now": act_now,
            "this_week": this_week,
            "deadlines_30_days": deadlines_30,
            "going_stale": stale,
            "awaiting_qualification": awaiting,
        },
        "what_can_wait": _what_can_wait(db),
    }


def _what_can_wait(db: Session) -> list[dict]:
    """Explicitly naming what does NOT need attention is as useful as
    naming what does — it is what lets an executive stop looking."""
    rows = (
        db.query(Opportunity, ExecutiveFocus)
        .join(ExecutiveFocus, ExecutiveFocus.opportunity_id == Opportunity.id)
        .filter(ExecutiveFocus.is_actionable.is_(False))
        .limit(5)
        .all()
    )
    return [
        {"id": o.id, "title": o.title, "reason": f.suppression_reason}
        for o, f in rows
    ]


# ------------------------------------------------ 2. today's priorities

def todays_priorities(db: Session, limit: int = 5) -> list[dict]:
    """Decision Cards, ranked by Focus. The recommendation appears before
    the supporting metrics — enforced by field order in the payload, which
    the frontend renders in sequence."""
    rows = focus_service.top_focus(db, limit=limit)
    if not rows:
        return []

    # Batched, not per-card. The previous version issued five queries
    # inside the loop plus more inside the helpers — roughly forty round
    # trips for five cards, against a 1.5-second budget for the whole
    # page. These five queries cover every card regardless of count.
    ids = [opp.id for opp, _ in rows]

    scores_by_opp: dict[str, dict] = {}
    for s in db.query(ScoreAssessment).filter(ScoreAssessment.opportunity_id.in_(ids)).all():
        scores_by_opp.setdefault(s.opportunity_id, {})[s.dimension] = s

    priorities = {
        p.opportunity_id: p
        for p in db.query(PursuitPriority).filter(PursuitPriority.opportunity_id.in_(ids)).all()
    }
    qualifications = {
        q.opportunity_id: q
        for q in db.query(QualificationAssessment)
        .filter(QualificationAssessment.opportunity_id.in_(ids))
        .all()
    }
    values = {
        v.opportunity_id: v
        for v in db.query(CommercialValue).filter(CommercialValue.opportunity_id.in_(ids)).all()
    }
    evidence_by_opp: dict[str, list] = {}
    for e in db.query(OpportunityEvidence).filter(OpportunityEvidence.opportunity_id.in_(ids)).all():
        evidence_by_opp.setdefault(e.opportunity_id, []).append(e)

    contacts_by_opp: dict[str, list] = {}
    for contact in db.query(Contact).filter(Contact.opportunity_id.in_(ids)).all():
        contacts_by_opp.setdefault(contact.opportunity_id, []).append(contact)

    # Qualification detail, batched by assessment. `_next_action` needs the
    # first unanswered mandatory item and the first unresolved blocker —
    # both were per-card lookups.
    assessment_ids = [q.id for q in qualifications.values()]
    unanswered_by_assessment: dict[str, object] = {}
    blockers_by_assessment: dict[str, object] = {}
    if assessment_ids:
        for item in (
            db.query(QualificationChecklistItem)
            .filter(
                QualificationChecklistItem.assessment_id.in_(assessment_ids),
                QualificationChecklistItem.answer == "unknown",
                QualificationChecklistItem.is_mandatory.is_(True),
            )
            .all()
        ):
            unanswered_by_assessment.setdefault(item.assessment_id, item)
        for blocker in (
            db.query(QualificationBlocker)
            .filter(
                QualificationBlocker.assessment_id.in_(assessment_ids),
                QualificationBlocker.failure_type == "remediable_blocker",
                QualificationBlocker.is_resolved.is_(False),
            )
            .all()
        ):
            blockers_by_assessment.setdefault(blocker.assessment_id, blocker)

    # The Commercial Profile is identical for every card — fetching it per
    # card was pure waste.
    profile_context = {
        "exclusions_checked": True,
        "min_viable": (
            profile_service.get_active_profile(db).min_viable_contract_value
            if profile_service.get_active_profile(db) else None
        ),
    }

    out: list[dict] = []
    for opp, focus in rows:
        scores = scores_by_opp.get(opp.id, {})
        priority = priorities.get(opp.id)
        qualification = qualifications.get(opp.id)
        value = values.get(opp.id)
        evidence = evidence_by_opp.get(opp.id, [])
        contacts = contacts_by_opp.get(opp.id, [])

        risk = scores.get("risk")
        out.append(
            {
                # --- DECISION FIRST -----------------------------------
                "recommended_decision": _provisional_decision(db, opp, qualification, value, profile_context),
                "why_this_matters": focus.explanation,
                "confidence": _confidence(scores, evidence),
                # --- identity -----------------------------------------
                "id": opp.id,
                "title": opp.title,
                "classification": opp.classification,
                "primary_vertical_label": _label(VERTICAL_V2_INFO, opp.primary_vertical),
                # --- focus --------------------------------------------
                "focus_score": focus.score,
                "focus_band": focus.band,
                "focus_band_label": focus.band_label,
                "focus_delta": focus.delta,
                "primary_drivers": (focus.primary_drivers or "").split(", "),
                # --- supporting metrics -------------------------------
                "strategic_alignment": scores["strategic_alignment"].score if "strategic_alignment" in scores else None,
                "commercial_value": _value_summary(value),
                "win_probability": scores["win_probability"].score if "win_probability" in scores else None,
                "risk": {
                    "score": None if (risk and risk.risk_established is False) else (risk.score if risk else None),
                    "label": "Risk not established" if (risk and risk.risk_established is False)
                             else (str(risk.score) if risk else "Not scored"),
                    "established": bool(risk.risk_established) if risk else False,
                },
                "relationship_status": _relationship_status_from(contacts),
                "qualification_state": qualification.state if qualification else "not_assessed",
                "qualification_label": QUALIFICATION_STATE_LABELS.get(
                    qualification.state if qualification else "not_assessed"
                ),
                # --- action -------------------------------------------
                "opportunity_cost_of_waiting": _cost_of_waiting(opp, focus),
                "required_relationships": _required_relationships_from(contacts),
                "supporting_evidence": _evidence_summary(evidence),
                "recommended_next_action": _next_action_from(
                    opp,
                    unanswered_by_assessment.get(qualification.id) if qualification else None,
                    blockers_by_assessment.get(qualification.id) if qualification else None,
                    contacts,
                ),
                "owner": opp.owner_name,
                "target_date": _target_date(opp),
                "deadline": opp.deadline.isoformat() if opp.deadline else None,
                "pursuit_priority": priority.final_score if priority else None,
                "priority_restricted": bool(priority.qualification_restricted or priority.coverage_restricted)
                if priority else False,
                "score_reconciliation": _reconcile(focus, priority),
            }
        )
    return out


def _provisional_decision(db: Session, opp: Opportunity,
                          qualification: QualificationAssessment | None,
                          value: CommercialValue | None,
                          profile_context: dict | None = None) -> dict:
    """A rule-derived posture.

    The full Commercial Strategy Engine lands in 3.4. This is a deliberate
    subset using rules that are already unambiguous — exclusions, value
    floor, qualification state — so a card always carries a decision
    rather than an empty field. It never guesses: where the rules are
    silent it says "review", which is honest.
    """
    excluded, reason = profile_service.is_excluded(
        db, region=opp.region.value if opp.region else None,
        commercial_type=opp.primary_commercial_type,
    )
    if excluded:
        return {"posture": "decline", "label": "Decline", "basis": reason}

    monetary = None
    if value:
        monetary = value.published_contract_value or value.estimated_vecta_revenue
    meets, threshold_reason = profile_service.meets_value_threshold(db, monetary)
    if not meets:
        return {"posture": "decline", "label": "Decline", "basis": threshold_reason}

    state = qualification.state if qualification else "not_assessed"
    if state == "disqualified":
        return {"posture": "decline", "label": "Decline", "basis": "Failed qualification"}
    if state in ("not_assessed", "verification_required"):
        return {"posture": "verify", "label": "Verify first",
                "basis": "Qualification incomplete — cannot recommend a pursuit posture yet"}
    if state == "conditionally_qualified":
        return {"posture": "pursue_with_conditions", "label": "Pursue — resolve blockers",
                "basis": "Qualified subject to remediable blockers"}
    return {"posture": "pursue", "label": "Pursue", "basis": "Qualified"}


def _confidence(scores: dict, evidence: list) -> str:
    """Mechanical, from evidence quality and score coverage — never the
    model's self-assessment."""
    tier_1 = sum(1 for e in evidence if e.source_tier == "tier_1")
    coverage = [s.coverage_percent for s in scores.values()] or [0]
    avg_coverage = sum(coverage) / len(coverage)
    if tier_1 >= 1 and avg_coverage >= 80:
        return "high"
    if evidence and avg_coverage >= 50:
        return "medium"
    return "low"


def _value_summary(value: CommercialValue | None) -> dict:
    if value is None:
        return {"amount": None, "label": "No value recorded", "is_estimate": False}
    if value.published_contract_value:
        return {"amount": value.published_contract_value, "currency": value.currency,
                "label": f"{value.currency} {value.published_contract_value:,.0f} (published)",
                "is_estimate": False}
    if value.estimated_contract_min and value.estimated_contract_max:
        return {
            "amount": (value.estimated_contract_min + value.estimated_contract_max) / 2,
            "currency": value.currency,
            "label": f"{value.currency} {value.estimated_contract_min:,.0f}–{value.estimated_contract_max:,.0f} (estimate)",
            "is_estimate": True,
        }
    return {"amount": None, "label": value.value_status.replace("_", " ").title(),
            "is_estimate": value.value_status == "estimated_range"}


def _relationship_status(db: Session, opportunity_id: str) -> dict:
    """Convenience wrapper for callers that do not already hold the
    contacts. The batched card path uses `_relationship_status_from`."""
    return _relationship_status_from(
        db.query(Contact).filter_by(opportunity_id=opportunity_id).all()
    )


def _relationship_status_from(contacts: list) -> dict:
    """Relationship position, INFERRED from contact role text until 3.2
    supplies the stakeholder model.

    Deliberately capped at `moderate`. Seniority here is keyword-matched
    against a role string — "Head of Facilities" reads as senior access
    and "Directeur Général" does not. A false `strong` is the one that
    would actually mislead a decision, so it is unreachable by inference;
    only verified stakeholder data (3.2) can produce it.

    Every response carries `is_inferred` and a `basis`, because an
    unlabelled inference presented beside evidence-backed scores is
    exactly the failure this platform exists to avoid.
    """
    inferred_basis = "Inferred from contact role text — not verified"

    if not contacts:
        return {
            "level": "unknown", "label": "Unknown",
            "detail": "No contacts mapped",
            "is_inferred": False,
            "basis": "No contact records exist",
        }

    strongest = max((c.relevance_score or 0) for c in contacts)
    senior = any(
        kw in (c.role or "").lower()
        for c in contacts
        for kw in ("director", "minister", "head", "chief", "secretary general")
    )
    if senior or strongest >= 50:
        return {
            "level": "moderate", "label": "Moderate (inferred)",
            "detail": f"{len(contacts)} contact(s) mapped",
            "is_inferred": True, "basis": inferred_basis,
            "cap_note": "Cannot be rated Strong without verified stakeholder data",
        }
    return {
        "level": "weak", "label": "Weak (inferred)",
        "detail": f"{len(contacts)} contact(s), no senior access identified",
        "is_inferred": True, "basis": inferred_basis,
    }


def _cost_of_waiting(opp: Opportunity, focus: ExecutiveFocus) -> dict:
    """What is lost by doing nothing this week. The field that converts an
    interesting card into an acted-upon one."""
    if opp.deadline:
        days = (opp.deadline - date.today()).days
        if days <= 7:
            return {"severity": "high",
                    "summary": f"Deadline in {days} days — the window closes this week."}
        if days <= 30:
            return {"severity": "medium",
                    "summary": f"Deadline in {days} days — preparation time is being consumed."}
    if focus.band == "act_now":
        return {"severity": "high", "summary": focus.explanation or "Immediate attention required."}
    if focus.band == "this_week":
        return {"severity": "medium", "summary": focus.explanation or "Attention needed this week."}
    return {"severity": "low", "summary": "No material cost to waiting a short period."}


def _required_relationships(db: Session, opportunity_id: str) -> list[dict]:
    """Wrapper — the batched card path uses `_required_relationships_from`."""
    return _required_relationships_from(
        db.query(Contact).filter_by(opportunity_id=opportunity_id).all()
    )


def _required_relationships_from(contacts: list) -> list[dict]:
    """Which relationships the pursuit needs, and whether VECTA has them.

    Phase 3.1 works from `Contact`; 3.2 replaces this with the stakeholder
    model. Each entry states whether it is held or missing, so a card can
    show the gap rather than only the count.
    """
    def held(*keywords: str) -> Contact | None:
        for c in contacts:
            role = (c.role or "").lower()
            if any(k in role for k in keywords):
                return c
        return None

    required = [
        ("decision_maker", "Decision-maker",
         ("director", "minister", "head", "chief", "secretary general")),
        ("procurement", "Procurement contact", ("procure", "tender", "commercial")),
        ("technical", "Technical influencer", ("technical", "performance", "coach")),
    ]
    out = []
    for key, label, keywords in required:
        match = held(*keywords)
        out.append(
            {
                "role": key,
                "label": label,
                "status": "held" if match else "missing",
                "contact_name": match.name if match else None,
                "is_inferred": bool(match),   # matched on role text, not verified
            }
        )
    return out


def _evidence_summary(evidence: list) -> dict:
    """Compact evidence position for the card.

    The card asks for a decision, so the evidence supporting it belongs on
    the card — not one click away. Full records remain on the detail page.
    """
    if not evidence:
        return {
            "total": 0, "tier_1": 0, "validated": 0,
            "label": "No evidence", "strongest_source": None,
            "sufficient_for_decision": False,
        }
    tier_1 = sum(1 for e in evidence if e.source_tier == "tier_1")
    validated = sum(1 for e in evidence if e.url_validation_status in ("valid", "archived"))
    strongest = next((e for e in evidence if e.source_tier == "tier_1"), evidence[0])
    if tier_1 and validated:
        label = f"Tier 1 verified ({len(evidence)} sources)"
    elif tier_1:
        label = f"Tier 1, URL not reviewed ({len(evidence)})"
    else:
        label = f"No Tier 1 source ({len(evidence)})"
    return {
        "total": len(evidence),
        "tier_1": tier_1,
        "validated": validated,
        "label": label,
        "strongest_source": {
            "publisher": strongest.publisher,
            "tier": strongest.source_tier,
            "url": strongest.url,
            "validation": strongest.url_validation_status,
        },
        "sufficient_for_decision": bool(tier_1 and validated),
    }


def _reconcile(focus, priority) -> str | None:
    """Explains divergence between Executive Focus and Pursuit Priority.

    They answer different questions — "where should I spend today" versus
    "how good is this opportunity" — and usually agree. When they diverge
    sharply, that IS the insight, and leaving it silent invites the
    reasonable question "which number is right?".
    """
    if priority is None:
        return None
    gap = focus.score - priority.final_score
    if abs(gap) < 30:
        return None
    if gap < 0:
        return (
            f"High-value opportunity (Pursuit Priority {priority.final_score}) but low Focus "
            f"({focus.score}) — {focus.suppression_reason or 'little that executive action changes right now'}."
        )
    return (
        f"Modest opportunity (Pursuit Priority {priority.final_score}) but high Focus "
        f"({focus.score}) — time-critical or several open actions."
    )


def _next_action_from(opp: Opportunity, unanswered, blocker, contacts: list) -> str:
    """Pure function over pre-fetched data — no queries.

    A recommendation of "review this opportunity" is not an action, so
    this always names something specific drawn from whatever is actually
    blocking.
    """
    if unanswered is not None:
        return f"Answer qualification check: {unanswered.item_label}"
    if blocker is not None:
        return blocker.message
    if opp.requires_human_review and opp.human_review_reason:
        return f"Review: {opp.human_review_reason[:140]}"
    if not contacts:
        return "Identify the decision-maker and procurement contact"
    return "Confirm next engagement and set a decision date"


def _next_action(db: Session, opp: Opportunity,
                 qualification: QualificationAssessment | None,
                 focus: ExecutiveFocus) -> str:
    """One specific action, drawn from whatever is actually blocking.

    A recommendation of "review this opportunity" is not an action.
    """
    if qualification:
        unanswered = (
            db.query(QualificationChecklistItem)
            .filter_by(assessment_id=qualification.id, answer="unknown", is_mandatory=True)
            .first()
        )
        if unanswered:
            return f"Answer qualification check: {unanswered.item_label}"
        blocker = (
            db.query(QualificationBlocker)
            .filter_by(assessment_id=qualification.id, failure_type="remediable_blocker",
                       is_resolved=False)
            .first()
        )
        if blocker:
            return blocker.message

    if opp.requires_human_review and opp.human_review_reason:
        return f"Review: {opp.human_review_reason[:140]}"

    contacts = db.query(Contact).filter_by(opportunity_id=opp.id).count()
    if contacts == 0:
        return "Identify the decision-maker and procurement contact"

    return "Confirm next engagement and set a decision date"


def _target_date(opp: Opportunity) -> str | None:
    """Computed, not blank. A recommendation with no date is an
    observation."""
    if opp.deadline:
        lead = 14 if (opp.deadline - date.today()).days > 21 else 3
        return (opp.deadline - timedelta(days=lead)).isoformat()
    return (date.today() + timedelta(days=14)).isoformat()


# --------------------------------------------------- 3. what changed

def what_changed(db: Session, since: datetime, limit: int = 20) -> list[dict]:
    events = change_detector.changes_since(db, since, limit=limit)
    out = []
    for e in events:
        opp = db.get(Opportunity, e.opportunity_id) if e.opportunity_id else None
        out.append(
            {
                "id": e.id,
                "event_type": e.event_type,
                "materiality": e.materiality,
                "summary": e.summary,
                "detail": e.detail,
                "delta": e.delta,
                "occurred_at": e.occurred_at.isoformat() if e.occurred_at else None,
                "triggered_by": e.triggered_by,
                "opportunity_id": e.opportunity_id,
                "opportunity_title": opp.title if opp else None,
            }
        )
    return out


# ---------------------------------------------- 4. relationship watchlist

def relationship_watchlist(db: Session, limit: int = 5) -> list[dict]:
    """Relationships needing attention — Sprint 2.

    Replaces the Sprint 1 placeholder, which inferred seniority from
    contact role text. This reads the real stakeholder model: health,
    momentum, influence and the specific action that would help.

    Falls back to the inference when no stakeholders are mapped yet, so a
    fresh install still says something useful rather than nothing.
    """
    from ..models_relationship import Stakeholder
    from . import relationship_service

    if db.query(Stakeholder).count() == 0:
        return _legacy_relationship_watchlist(db, limit)

    out: list[dict] = []

    # Where an hour changes an outcome — not simply who is weakest.
    for entry in relationship_service.where_to_invest_time(db, limit=limit):
        out.append(
            {
                "stakeholder_id": entry["stakeholder_id"],
                "name": entry["name"],
                "role": entry["role"],
                "organisation": entry["organisation"],
                "attention_score": entry["attention_score"],
                "health_score": entry["health_score"],
                "health_band": entry["health_band"],
                "momentum": entry["momentum"],
                "momentum_state": entry["momentum_state"],
                "why": entry["why"],
                "recommended_engagement": entry["recommended_action"],
                "expected_commercial_benefit": entry["expected_benefit"],
                "opportunities": entry["opportunities"],
                "is_inferred": False,
            }
        )
    return out


def coverage_exposure(db: Session, limit: int = 3) -> list[dict]:
    """Opportunities where executive focus is high and relationship
    coverage is thin — the most dangerous combination in the pipeline,
    and one nothing else surfaces."""
    from ..models_relationship import Stakeholder
    from . import relationship_service

    if db.query(Stakeholder).count() == 0:
        return []
    return relationship_service.coverage_across_pipeline(db, limit=limit)


def relationship_gaps(db: Session, limit: int = 4) -> list[dict]:
    """Missing decision-makers on live opportunities.

    The highest-value relationship output in the briefing: someone you
    have not identified cannot be engaged, and nothing else notices their
    absence.
    """
    from ..models_relationship import Stakeholder
    from . import relationship_service

    if db.query(Stakeholder).count() == 0:
        return []
    return relationship_service.who_are_we_missing(db, limit=limit)


def _legacy_relationship_watchlist(db: Session, limit: int) -> list[dict]:
    """Sprint 1 fallback, used only before any stakeholder is mapped.

    Explicitly marked inferred — it reads seniority from contact role
    text, which is crude and must not be presented as verified.
    """
    rows = (
        db.query(Opportunity, ExecutiveFocus)
        .join(ExecutiveFocus, ExecutiveFocus.opportunity_id == Opportunity.id)
        .filter(ExecutiveFocus.is_actionable.is_(True))
        .order_by(ExecutiveFocus.score.desc())
        .limit(limit * 3)
        .all()
    )
    out: list[dict] = []
    for opp, focus in rows:
        status = _relationship_status(db, opp.id)
        if status["level"] == "strong":
            continue
        win = (
            db.query(ScoreAssessment)
            .filter_by(opportunity_id=opp.id, dimension="win_probability")
            .first()
        )
        headroom = (100 - win.score) if win else 40
        out.append(
            {
                "opportunity_id": opp.id,
                "opportunity_title": opp.title,
                "name": None,
                "current_strength": status["label"],
                "why": status["detail"],
                "recommended_engagement": "Map the stakeholder landscape for this opportunity",
                "expected_commercial_benefit": f"Up to +{round(headroom * 0.25)} win probability points",
                "focus_score": focus.score,
                "is_inferred": True,
            }
        )
        if len(out) >= limit:
            break
    return out


# ------------------------------------------------ 5. market intelligence

def market_intelligence(db: Session, since: datetime, limit: int = 6) -> list[dict]:
    """Developments by market, filtered to the Commercial Profile.

    Filtering is the point: an executive does not need to know that
    something happened in a market VECTA has decided not to enter.
    """
    rows = (
        db.query(
            Opportunity.region,
            Opportunity.market,
            func.count(Opportunity.id).label("count"),
        )
        .filter(Opportunity.created_at >= since)
        .group_by(Opportunity.region, Opportunity.market)
        .all()
    )

    out: list[dict] = []
    for region, market, count in rows:
        region_value = region.value if region else None
        tier = profile_service.region_tier(db, region_value, market)
        excluded, _ = profile_service.is_excluded(db, region=region_value)
        if excluded:
            continue
        out.append(
            {
                "region": region_value,
                "market": market,
                "new_opportunities": count,
                "profile_tier": tier,
                "is_priority": tier == 1 if tier else False,
                "relevance": (
                    "Tier 1 priority market" if tier == 1
                    else f"Tier {tier} market" if tier
                    else "Not a stated priority — review whether it should be"
                ),
            }
        )

    # Priority markets first; unprofiled activity still surfaces, because
    # "we are seeing activity somewhere we have no view" is itself useful.
    out.sort(key=lambda m: (m["profile_tier"] or 9, -m["new_opportunities"]))
    return out[:limit]


# --------------------------------------------------- 6. executive risks

def executive_risks(db: Session, limit: int = 8) -> list[dict]:
    """Highest-priority risks across the five categories, each with
    severity, evidence, mitigation and owner."""
    risks: list[dict] = []

    # --- delivery capacity ---
    capacity = profile_service.capacity_status(db)
    if capacity.get("strained"):
        risks.append(
            {
                "category": "delivery_capacity",
                "severity": "high",
                "summary": f"Delivery capacity {capacity['label']}",
                "evidence": "Commercial Profile capacity vs current workload",
                "mitigation": "Review committed pursuits; defer or partner on the lowest-value",
                "owner": None,
            }
        )

    # --- evidence quality ---
    unverified = (
        db.query(Opportunity)
        .filter(Opportunity.classification == "confirmed_opportunity",
                Opportunity.requires_human_review.is_(True))
        .count()
    )
    if unverified:
        risks.append(
            {
                "category": "qualification",
                "severity": "high",
                "summary": f"{unverified} confirmed opportunit{'y' if unverified == 1 else 'ies'} flagged for review",
                "evidence": "Evidence enforcement flagged these during scanning",
                "mitigation": "Verify sources before relying on the classification",
                "owner": None,
            }
        )

    # --- risk not established ---
    unestablished = (
        db.query(ScoreAssessment)
        .filter(ScoreAssessment.dimension == "risk",
                ScoreAssessment.risk_established.is_(False))
        .count()
    )
    if unestablished:
        risks.append(
            {
                "category": "commercial",
                "severity": "medium",
                "summary": f"Risk not established on {unestablished} opportunit{'y' if unestablished == 1 else 'ies'}",
                "evidence": "Insufficient risk-factor coverage — the score is suppressed rather than shown low",
                "mitigation": "Complete risk assessment before committing pursuit resources",
                "owner": None,
            }
        )

    # --- stale / relationship ---
    stale_events = [
        e for e in change_detector.changes_since(db, utcnow() - timedelta(days=7), limit=100)
        if e.event_type == "went_stale"
    ]
    if stale_events:
        risks.append(
            {
                "category": "operational",
                "severity": "high",
                "summary": f"{len(stale_events)} qualified opportunit{'y' if len(stale_events)==1 else 'ies'} going stale",
                "evidence": "No activity for 14+ days on qualified work",
                "mitigation": "Set a next action and owner, or formally defer",
                "owner": None,
            }
        )

    unmapped = (
        db.query(Opportunity, ExecutiveFocus)
        .join(ExecutiveFocus, ExecutiveFocus.opportunity_id == Opportunity.id)
        .outerjoin(Contact, Contact.opportunity_id == Opportunity.id)
        .filter(ExecutiveFocus.is_actionable.is_(True), Contact.id.is_(None))
        .count()
    )
    if unmapped:
        risks.append(
            {
                "category": "relationship",
                "severity": "medium",
                "summary": f"{unmapped} active opportunit{'y has' if unmapped == 1 else 'ies have'} no mapped contacts",
                "evidence": "No contact records linked",
                "mitigation": "Identify decision-maker and procurement contacts",
                "owner": None,
            }
        )

    # --- assumptions ---
    overdue = (
        db.query(AssumptionLedger)
        .filter(AssumptionLedger.status == "active",
                AssumptionLedger.affects_recommendation.is_(True),
                AssumptionLedger.review_due_at.is_not(None),
                AssumptionLedger.review_due_at < utcnow())
        .count()
    )
    if overdue:
        risks.append(
            {
                "category": "commercial",
                "severity": "high",
                "summary": f"{overdue} assumption(s) past review, affecting live recommendations",
                "evidence": "Assumption ledger review dates",
                "mitigation": "Re-verify or invalidate — a recommendation resting on a stale assumption is indefensible",
                "owner": None,
            }
        )

    order = {"high": 0, "medium": 1, "low": 2}
    risks.sort(key=lambda r: order.get(r["severity"], 3))
    return risks[:limit]


# ----------------------------------------------------- 7. advisor prompts

def advisor_prompts(db: Session) -> list[dict]:
    """Suggested questions, each with whether the data can answer it.

    Offering a question ATLAS cannot answer well is worse than not
    offering it — the first confidently thin answer costs more trust than
    a narrow scope costs utility.
    """
    has_focus = db.query(ExecutiveFocus).count() > 0
    has_history = db.query(ChangeEvent).count() > 0
    has_contacts = db.query(Contact).count() > 0

    return [
        {"question": "What should I focus on today?", "available": has_focus},
        {"question": "What changed overnight?", "available": has_history},
        {"question": "Which opportunity deserves immediate attention?", "available": has_focus},
        {"question": "Which opportunities have improved?", "available": has_history},
        {"question": "Which opportunities are deteriorating?", "available": has_history},
        {"question": "Which relationship should I strengthen?", "available": has_contacts},
    ]


# ------------------------------------------------------------ assembly

def build_briefing(db: Session, since: datetime | None = None,
                   priority_limit: int = 5) -> dict:
    """The complete briefing. Sections are ordered as the executive
    hierarchy requires and returned in that order."""
    since = since or (utcnow() - timedelta(days=1))

    profile_state = profile_service.completeness(db)
    last_scan = db.query(ScanRun).order_by(ScanRun.started_at.desc()).first()
    scan_age_days = None
    if last_scan and last_scan.started_at:
        scan_age_days = (utcnow() - as_aware(last_scan.started_at)).days

    started = time.perf_counter()

    degraded_summary = {
        "headline": "Part of your briefing could not be prepared. The sections below are current.",
        "is_complete": False,
        "completion_message": None,
        "changes_since": since.isoformat(),
        "counts": {},
        "what_can_wait": [],
    }

    sections = {
        "1_executive_summary": _safe_section(
            "executive_summary", lambda: executive_summary(db, since), degraded_summary
        ),
        "2_todays_priorities": _safe_section(
            "todays_priorities", lambda: todays_priorities(db, limit=priority_limit), []
        ),
        "3_what_changed": _safe_section("what_changed", lambda: what_changed(db, since), []),
        "4_relationship_watchlist": _safe_section(
            "relationship_watchlist", lambda: relationship_watchlist(db), []
        ),
        "4b_relationship_gaps": _safe_section(
            "relationship_gaps", lambda: relationship_gaps(db), []
        ),
        "4c_coverage_exposure": _safe_section(
            "coverage_exposure", lambda: coverage_exposure(db), []
        ),
        "5_market_intelligence": _safe_section(
            "market_intelligence", lambda: market_intelligence(db, since), []
        ),
        "6_executive_risks": _safe_section("executive_risks", lambda: executive_risks(db), []),
        "7_advisor": _safe_section("advisor", lambda: advisor_prompts(db), []),
    }

    elapsed_ms = round((time.perf_counter() - started) * 1000)
    if elapsed_ms > 1500:
        logger.warning("Briefing exceeded the 1.5s budget: %dms", elapsed_ms)

    return {
        "generated_at": utcnow().isoformat(),
        "since": since.isoformat(),
        "ai_calls_used": 0,          # the briefing is always free
        "generation_ms": elapsed_ms,
        "sections": sections,
        "profile": {
            "version": profile_state["version"],
            "completeness_percent": profile_state["percent"],
            "incomplete_sections": [
                s["label"] for s in profile_state["sections"] if not s["complete"]
            ],
        },
        "scanning": {
            "last_scan_days_ago": scan_age_days,
            "suggest_scan": scan_age_days is None or scan_age_days >= 7,
            "estimated_cost_usd": 0.50,
        },
    }
