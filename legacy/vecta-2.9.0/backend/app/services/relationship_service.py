"""Relationship Intelligence service — Sprint 2.

Organised around the six executive questions rather than around CRUD.
That is the difference between a relationship module and a relationship
intelligence engine: a module stores people; this one answers

    1. Who matters most?
    2. Who are we missing?
    3. Which relationships are improving?
    4. Which relationships are at risk?
    5. Where should I invest my time this week?
    6. How do relationships affect our likelihood of success?

Question 5 is the one that justifies the sprint. It deliberately does NOT
rank by health — a strong relationship needs nothing done to it. It ranks
by where an hour of executive time changes an outcome, which is the same
logic as Executive Focus applied to people.

All computed. No AI calls.
"""
from __future__ import annotations

import json
import logging
from collections import deque
from datetime import date, datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import relationship_health as engine
from ..models import Contact, Opportunity, Organisation
from ..models_memory import ExecutiveFocus
from ..models_phase2 import ScoreAssessment
from ..models_relationship import (
    Engagement,
    IntroductionPath,
    OpportunityStakeholder,
    RelationshipEdge,
    RelationshipHealth,
    RelationshipHealthHistory,
    Stakeholder,
    StakeholderMilestone,
)
from ..timeutils import as_aware, utcnow
from . import profile_service

logger = logging.getLogger("atlas.relationships")

# Roles whose absence on a live opportunity is a material gap.
CRITICAL_ROLES = ("economic_buyer", "budget_holder", "procurement_authority")

MAX_INTRODUCTION_HOPS = 3
VIABLE_PATH_MIN_STRENGTH = 40


# ═══════════════════════════════ health ═══════════════════════════════

def _engagement_stats(db: Session, stakeholder_id: str) -> dict:
    """Everything the health engine needs, in one pass."""
    year_ago = utcnow() - timedelta(days=365)
    engagements = (
        db.query(Engagement)
        .filter(Engagement.stakeholder_id == stakeholder_id)
        .order_by(Engagement.occurred_at.desc())
        .all()
    )
    recent = [e for e in engagements if as_aware(e.occurred_at) >= year_ago]

    outbound = [e for e in recent if e.was_initiated_by_vecta]
    replied = [e for e in outbound if e.received_response]

    return {
        "last_engagement": as_aware(engagements[0].occurred_at) if engagements else None,
        "count_12m": len(recent),
        "sent": len(outbound),
        "replied": len(replied),
        "positive": sum(1 for e in recent if e.outcome == "positive"),
        "neutral": sum(1 for e in recent if e.outcome == "neutral"),
        "negative": sum(1 for e in recent if e.outcome == "negative"),
        "overdue_followups": sum(
            1 for e in engagements
            if e.follow_up_due and not e.follow_up_completed and e.follow_up_due < date.today()
        ),
        "has_scheduled": any(
            e.follow_up_due and not e.follow_up_completed and e.follow_up_due >= date.today()
            for e in engagements
        ),
    }


def compute_health_for(db: Session, stakeholder: Stakeholder) -> dict:
    """Assembles the seven health factors from stored data."""
    stats = _engagement_stats(db, stakeholder.id)

    links = (
        db.query(OpportunityStakeholder)
        .filter_by(stakeholder_id=stakeholder.id)
        .all()
    )
    highest_focus = None
    if links:
        focus_rows = (
            db.query(ExecutiveFocus)
            .filter(ExecutiveFocus.opportunity_id.in_([l.opportunity_id for l in links]))
            .all()
        )
        if focus_rows:
            highest_focus = max(f.score for f in focus_rows)

    org = (
        db.get(Organisation, stakeholder.organisation_id)
        if stakeholder.organisation_id else None
    )
    tier = profile_service.region_tier(db, stakeholder.region, stakeholder.market)
    is_strategic = _is_strategic_account(db, stakeholder.organisation_name)

    components = {
        "recency": engine.recency_component(stats["last_engagement"]),
        "frequency": engine.frequency_component(stats["count_12m"]),
        "responsiveness": engine.responsiveness_component(stats["sent"], stats["replied"]),
        "meeting_outcomes": engine.meeting_outcome_component(
            stats["positive"], stats["neutral"], stats["negative"]
        ),
        "influence": engine.influence_component(
            stakeholder.stakeholder_type, stakeholder.decision_authority
        ),
        "opportunity_alignment": engine.opportunity_alignment_component(
            len(links), highest_focus
        ),
        "strategic_value": engine.strategic_value_component(
            is_strategic, tier, org.org_type.value if org and org.org_type else None
        ),
    }
    result = engine.compute_health(components)
    result["_stats"] = stats
    return result


def _is_strategic_account(db: Session, organisation_name: str | None) -> bool:
    if not organisation_name:
        return False
    from ..models_profile import ProfilePriorityAccount

    profile = profile_service.get_active_profile(db)
    if profile is None:
        return False
    return (
        db.query(ProfilePriorityAccount)
        .filter_by(profile_id=profile.id)
        .filter(ProfilePriorityAccount.organisation_name.ilike(organisation_name))
        .first()
        is not None
    )


def persist_health(db: Session, stakeholder: Stakeholder, result: dict) -> RelationshipHealth:
    """Stores health, appends to history, and computes momentum from the
    series. History is what makes momentum possible at all."""
    stats = result.pop("_stats", {})

    existing = db.query(RelationshipHealth).filter_by(stakeholder_id=stakeholder.id).first()
    previous = existing.score if existing else None

    db.add(
        RelationshipHealthHistory(
            stakeholder_id=stakeholder.id,
            score=result["score"],
            band=result["band"],
            at_risk=result["at_risk"],
            influence_score=stakeholder.influence_level,
            trust_level=stakeholder.trust_level,
            days_since_engagement=(
                (utcnow() - stats["last_engagement"]).days
                if stats.get("last_engagement") else None
            ),
            change_reason="recompute",
        )
    )
    db.flush()

    series = [
        h.score
        for h in db.query(RelationshipHealthHistory)
        .filter_by(stakeholder_id=stakeholder.id)
        .order_by(RelationshipHealthHistory.recorded_at.asc())
        .all()
    ]

    influence = engine.influence_component(
        stakeholder.stakeholder_type, stakeholder.decision_authority
    )["score"]
    days_since = (
        (utcnow() - stats["last_engagement"]).days if stats.get("last_engagement") else None
    )

    momentum = engine.compute_momentum(
        series,
        at_risk=result["at_risk"],
        influence_score=influence,
        days_since_engagement=days_since,
        overdue_followups=stats.get("overdue_followups", 0),
        has_scheduled_engagement=stats.get("has_scheduled", False),
    )

    if existing:
        db.delete(existing)
        db.flush()

    row = RelationshipHealth(
        stakeholder_id=stakeholder.id,
        score=result["score"],
        band=result["band"],
        band_label=result["band_label"],
        at_risk=result["at_risk"],
        at_risk_reason=result["at_risk_reason"],
        previous_score=previous,
        delta=(result["score"] - previous) if previous is not None else None,
        trend_direction=momentum["state"],
        explanation=engine.explain(result),
        contributions_json=json.dumps(result["contributions"]),
        improvement_levers_json=json.dumps(result["improvement_levers"]),
        model_version=result["model_version"],
    )
    db.add(row)
    db.flush()
    return row


def recompute_all(db: Session) -> dict:
    """Recomputes health and momentum across every stakeholder."""
    computed = at_risk = critical = 0
    for stakeholder in db.query(Stakeholder).all():
        result = compute_health_for(db, stakeholder)
        row = persist_health(db, stakeholder, result)
        computed += 1
        if row.at_risk:
            at_risk += 1
        if row.trend_direction == "critical":
            critical += 1
    db.flush()
    logger.info("Recomputed %d relationship health scores", computed)
    return {"computed": computed, "at_risk": at_risk, "critical": critical}


def _momentum_batch(db: Session, stakeholders: list[Stakeholder]) -> dict[str, dict]:
    """Momentum for many stakeholders in a fixed number of queries.

    `_momentum_for` issues three queries per stakeholder plus the
    engagement scan inside `_engagement_stats` — roughly six. Across two
    hundred stakeholders that is over a thousand round trips for a single
    briefing section, which will not hold under production load.

    This batches the same computation into four queries regardless of
    stakeholder count.
    """
    if not stakeholders:
        return {}
    ids = [s.id for s in stakeholders]

    history: dict[str, list[int]] = {}
    for row in (
        db.query(RelationshipHealthHistory)
        .filter(RelationshipHealthHistory.stakeholder_id.in_(ids))
        .order_by(RelationshipHealthHistory.recorded_at.asc())
        .all()
    ):
        history.setdefault(row.stakeholder_id, []).append(row.score)

    healths = {
        h.stakeholder_id: h
        for h in db.query(RelationshipHealth)
        .filter(RelationshipHealth.stakeholder_id.in_(ids))
        .all()
    }

    engagements: dict[str, list] = {}
    for e in (
        db.query(Engagement)
        .filter(Engagement.stakeholder_id.in_(ids))
        .order_by(Engagement.occurred_at.desc())
        .all()
    ):
        engagements.setdefault(e.stakeholder_id, []).append(e)

    today = date.today()
    out: dict[str, dict] = {}
    for s in stakeholders:
        rows = engagements.get(s.id, [])
        last = as_aware(rows[0].occurred_at) if rows else None
        overdue = sum(
            1 for e in rows
            if e.follow_up_due and not e.follow_up_completed and e.follow_up_due < today
        )
        scheduled = any(
            e.follow_up_due and not e.follow_up_completed and e.follow_up_due >= today
            for e in rows
        )
        health = healths.get(s.id)
        series = history.get(s.id) or ([health.score] if health else [])
        influence = engine.influence_component(
            s.stakeholder_type, s.decision_authority
        )["score"]
        out[s.id] = engine.compute_momentum(
            series,
            at_risk=bool(health and health.at_risk),
            influence_score=influence,
            days_since_engagement=(utcnow() - last).days if last else None,
            overdue_followups=overdue,
            has_scheduled_engagement=scheduled,
        )
    return out


def _momentum_for(db: Session, stakeholder: Stakeholder) -> dict:
    """Momentum from stored history — no recomputation."""
    series = [
        h.score
        for h in db.query(RelationshipHealthHistory)
        .filter_by(stakeholder_id=stakeholder.id)
        .order_by(RelationshipHealthHistory.recorded_at.asc())
        .all()
    ]
    health = db.query(RelationshipHealth).filter_by(stakeholder_id=stakeholder.id).first()
    stats = _engagement_stats(db, stakeholder.id)
    influence = engine.influence_component(
        stakeholder.stakeholder_type, stakeholder.decision_authority
    )["score"]
    return engine.compute_momentum(
        series or ([health.score] if health else []),
        at_risk=bool(health and health.at_risk),
        influence_score=influence,
        days_since_engagement=(
            (utcnow() - stats["last_engagement"]).days if stats["last_engagement"] else None
        ),
        overdue_followups=stats["overdue_followups"],
        has_scheduled_engagement=stats["has_scheduled"],
    )


# ══════════════════ the six executive questions ══════════════════

def who_matters_most(db: Session, limit: int = 10) -> list[dict]:
    """Q1. Ranked by commercial consequence, not by how well we know them.

    Someone we have never met can matter most — that is precisely the
    case worth surfacing, and a contact list sorted by interaction count
    would bury it.
    """
    rows = db.query(Stakeholder).all()
    scored = []
    for s in rows:
        influence = engine.influence_component(s.stakeholder_type, s.decision_authority)
        links = db.query(OpportunityStakeholder).filter_by(stakeholder_id=s.id).count()
        health = db.query(RelationshipHealth).filter_by(stakeholder_id=s.id).first()

        # Consequence, not familiarity.
        importance = influence["score"] * 0.6 + min(100, links * 30) * 0.25
        if _is_strategic_account(db, s.organisation_name):
            importance += 15

        scored.append(
            {
                "stakeholder_id": s.id,
                "name": s.full_name,
                "role": s.role_title,
                "organisation": s.organisation_name,
                "stakeholder_type": s.stakeholder_type,
                "decision_authority": s.decision_authority,
                "importance": round(min(100, importance)),
                "influence_note": influence["note"],
                "linked_opportunities": links,
                "health_score": health.score if health else None,
                "health_band": health.band_label if health else "Not assessed",
                "is_known": bool(s.last_engagement_at),
                "why": (
                    f"{influence['note']}"
                    + (f", linked to {links} opportunit{'y' if links == 1 else 'ies'}" if links else
                       ", not yet linked to an opportunity")
                ),
            }
        )
    scored.sort(key=lambda r: -r["importance"])
    return scored[:limit]


def who_are_we_missing(db: Session, limit: int = 10) -> list[dict]:
    """Q2. Gaps on live opportunities.

    The most valuable output in the whole service: a decision-maker you
    have not identified cannot be engaged, and nothing else in ATLAS
    notices their absence.
    """
    gaps: list[dict] = []

    live = (
        db.query(Opportunity, ExecutiveFocus)
        .join(ExecutiveFocus, ExecutiveFocus.opportunity_id == Opportunity.id)
        .filter(ExecutiveFocus.is_actionable.is_(True))
        .order_by(ExecutiveFocus.score.desc())
        .all()
    )

    for opp, focus in live:
        links = (
            db.query(OpportunityStakeholder, Stakeholder)
            .join(Stakeholder, Stakeholder.id == OpportunityStakeholder.stakeholder_id)
            .filter(OpportunityStakeholder.opportunity_id == opp.id)
            .all()
        )
        present = {s.stakeholder_type for _, s in links}

        for role in CRITICAL_ROLES:
            if role in present:
                continue
            label = role.replace("_", " ")
            gaps.append(
                {
                    "opportunity_id": opp.id,
                    "opportunity_title": opp.title,
                    "missing_role": role,
                    "missing_label": label.title(),
                    "severity": "high" if role == "economic_buyer" else "medium",
                    "focus_score": focus.score,
                    "why_it_matters": (
                        f"No {label} identified on an opportunity with Executive Focus "
                        f"{focus.score}. This cannot be engaged until they are found."
                    ),
                    "recommended_action": f"Identify the {label} for {opp.title}",
                }
            )

        if not links:
            gaps.append(
                {
                    "opportunity_id": opp.id,
                    "opportunity_title": opp.title,
                    "missing_role": "any",
                    "missing_label": "All stakeholders",
                    "severity": "high",
                    "focus_score": focus.score,
                    "why_it_matters": "No stakeholders mapped at all.",
                    "recommended_action": f"Map the stakeholder landscape for {opp.title}",
                }
            )

    order = {"high": 0, "medium": 1, "low": 2}
    gaps.sort(key=lambda g: (order.get(g["severity"], 3), -g["focus_score"]))
    return gaps[:limit]


def improving_relationships(db: Session, limit: int = 10) -> list[dict]:
    """Q3. Where investment is working — worth knowing so it continues."""
    stakeholders = db.query(Stakeholder).all()
    momenta = _momentum_batch(db, stakeholders)
    healths = {
        h.stakeholder_id: h
        for h in db.query(RelationshipHealth)
        .filter(RelationshipHealth.stakeholder_id.in_([s.id for s in stakeholders]))
        .all()
    } if stakeholders else {}

    out = []
    for s in stakeholders:
        momentum = momenta[s.id]
        if momentum["state"] != "improving":
            continue
        health = healths.get(s.id)
        out.append(
            {
                "stakeholder_id": s.id,
                "name": s.full_name,
                "organisation": s.organisation_name,
                "health_score": health.score if health else None,
                "momentum": momentum["label"],
                "slope": momentum["slope"],
                "explanation": momentum["explanation"],
                "is_provisional": momentum["is_provisional"],
            }
        )
    out.sort(key=lambda r: -(r["slope"] or 0))
    return out[:limit]


def relationships_at_risk(db: Session, limit: int = 10) -> list[dict]:
    """Q4. Declining or critical, ordered by commercial consequence."""
    stakeholders = db.query(Stakeholder).all()
    momenta = _momentum_batch(db, stakeholders)
    ids = [s.id for s in stakeholders]
    healths = {
        h.stakeholder_id: h
        for h in db.query(RelationshipHealth).filter(RelationshipHealth.stakeholder_id.in_(ids)).all()
    } if ids else {}
    link_counts: dict[str, int] = {}
    if ids:
        for link in db.query(OpportunityStakeholder).filter(
            OpportunityStakeholder.stakeholder_id.in_(ids)
        ).all():
            link_counts[link.stakeholder_id] = link_counts.get(link.stakeholder_id, 0) + 1

    out = []
    for s in stakeholders:
        momentum = momenta[s.id]
        health = healths.get(s.id)
        if momentum["state"] not in ("declining", "critical") and not (health and health.at_risk):
            continue
        influence = engine.influence_component(s.stakeholder_type, s.decision_authority)
        links = link_counts.get(s.id, 0)
        out.append(
            {
                "stakeholder_id": s.id,
                "name": s.full_name,
                "organisation": s.organisation_name,
                "role": s.role_title,
                "health_score": health.score if health else None,
                "health_band": health.band_label if health else "Not assessed",
                "momentum": momentum["label"],
                "momentum_state": momentum["state"],
                "at_risk_reason": health.at_risk_reason if health else None,
                "explanation": momentum["explanation"],
                "influence": influence["note"],
                "linked_opportunities": links,
                "recommended_action": _recommended_action(s, health, momentum),
                "priority": momentum["priority"],
            }
        )
    out.sort(key=lambda r: (r["priority"], -(r["linked_opportunities"] or 0)))
    return out[:limit]


def where_to_invest_time(db: Session, limit: int = 5) -> list[dict]:
    """Q5. The question that justifies the sprint.

    Ranked by where an hour changes an outcome — NOT by health. A strong
    relationship needs nothing done to it; a declining high-influence one
    needs a call today.
    """
    stakeholders = db.query(Stakeholder).all()
    ids = [s.id for s in stakeholders]
    momenta = _momentum_batch(db, stakeholders)
    healths = {
        h.stakeholder_id: h
        for h in db.query(RelationshipHealth).filter(RelationshipHealth.stakeholder_id.in_(ids)).all()
    } if ids else {}
    links_by_stakeholder: dict[str, list] = {}
    if ids:
        for link, opp in (
            db.query(OpportunityStakeholder, Opportunity)
            .join(Opportunity, Opportunity.id == OpportunityStakeholder.opportunity_id)
            .filter(OpportunityStakeholder.stakeholder_id.in_(ids))
            .all()
        ):
            links_by_stakeholder.setdefault(link.stakeholder_id, []).append((link, opp))

    out = []
    for s in stakeholders:
        health = healths.get(s.id)
        if health is None:
            continue
        momentum = momenta[s.id]
        influence = engine.influence_component(s.stakeholder_type, s.decision_authority)
        priority = engine.combined_priority(health.score, momentum, influence["score"])
        links = links_by_stakeholder.get(s.id, [])
        out.append(
            {
                "stakeholder_id": s.id,
                "name": s.full_name,
                "role": s.role_title,
                "organisation": s.organisation_name,
                "attention_score": priority,
                "health_score": health.score,
                "health_band": health.band_label,
                "momentum": momentum["label"],
                "momentum_state": momentum["state"],
                "why": momentum["explanation"],
                "influence": influence["note"],
                "opportunities": [{"id": o.id, "title": o.title} for _, o in links],
                "recommended_action": _recommended_action(s, health, momentum),
                "expected_benefit": _expected_benefit(db, s, health, links),
            }
        )
    out.sort(key=lambda r: -r["attention_score"])
    return out[:limit]


def relationship_impact_on_success(db: Session, opportunity_id: str) -> dict:
    """Q6. How relationships affect this pursuit's odds.

    Win Probability already weights `relationship_strength` (13%) and
    `decision_maker_access` (12%). This quantifies the headroom those two
    factors represent — turning "relationships matter" into a number an
    executive can weigh against other calls on their time.
    """
    opp = db.get(Opportunity, opportunity_id)
    if opp is None:
        return {"available": False, "reason": "Opportunity not found"}

    links = (
        db.query(OpportunityStakeholder, Stakeholder)
        .join(Stakeholder, Stakeholder.id == OpportunityStakeholder.stakeholder_id)
        .filter(OpportunityStakeholder.opportunity_id == opportunity_id)
        .all()
    )
    win = (
        db.query(ScoreAssessment)
        .filter_by(opportunity_id=opportunity_id, dimension="win_probability")
        .first()
    )

    present_roles = {s.stakeholder_type for _, s in links}
    missing = [r for r in CRITICAL_ROLES if r not in present_roles]

    healths = []
    for _, s in links:
        h = db.query(RelationshipHealth).filter_by(stakeholder_id=s.id).first()
        if h:
            healths.append(h.score)
    mean_health = round(sum(healths) / len(healths)) if healths else 0

    # 25% of Win Probability is relationship-derived.
    headroom = (100 - win.score) if win else 40
    available = round(headroom * 0.25)
    coverage = round((len(CRITICAL_ROLES) - len(missing)) / len(CRITICAL_ROLES) * 100)

    return {
        "available": True,
        "opportunity_id": opportunity_id,
        "opportunity_title": opp.title,
        "current_win_probability": win.score if win else None,
        "stakeholders_mapped": len(links),
        "influence_coverage_percent": coverage,
        "missing_critical_roles": [
            {"role": r, "label": r.replace("_", " ").title()} for r in missing
        ],
        "mean_relationship_health": mean_health,
        "relationship_headroom_points": available,
        "summary": (
            f"Relationships account for roughly a quarter of Win Probability. "
            f"With {coverage}% influence coverage and mean health {mean_health}, "
            f"up to {available} points are available from relationship work."
            + (f" {len(missing)} critical role(s) unmapped." if missing else "")
        ),
        "biggest_lever": (
            f"Identify the {missing[0].replace('_',' ')}"
            if missing
            else "Deepen the weakest mapped relationship"
        ),
    }


# ═══════════════════════ supporting computations ═══════════════════════

def _recommended_action(stakeholder: Stakeholder, health, momentum: dict) -> str:
    """One specific action. "Review this relationship" is not an action."""
    if momentum["state"] == "critical":
        return f"Call {stakeholder.full_name} this week — high-influence relationship failing"
    if health and health.at_risk:
        return f"Re-engage {stakeholder.full_name} — {health.at_risk_reason or 'has gone quiet'}"
    if momentum["leading_penalty"] > 0:
        return f"Schedule contact with {stakeholder.full_name} and close overdue follow-ups"
    if health and health.score < 40:
        return f"Invest in {stakeholder.full_name} — relationship is weak"
    if not stakeholder.last_engagement_at:
        return f"Make first contact with {stakeholder.full_name}"
    return f"Maintain regular contact with {stakeholder.full_name}"


def _expected_benefit(db: Session, stakeholder: Stakeholder, health, links: list) -> str:
    """What strengthening this relationship is worth, in win-probability
    terms — so the recommendation can be weighed, not just followed."""
    if not links:
        return "No linked opportunity — strategic investment only"
    influence = engine.influence_component(
        stakeholder.stakeholder_type, stakeholder.decision_authority
    )["score"]
    headroom = 100 - (health.score if health else 0)
    gain = round(headroom * 0.25 * (influence / 100))
    titles = ", ".join(o.title for _, o in links[:2])
    return f"Up to +{gain} win probability points on {titles}"


def find_introduction_paths(db: Session, target_stakeholder_id: str,
                            max_hops: int = MAX_INTRODUCTION_HOPS) -> list[dict]:
    """Breadth-first search from VECTA to a target, over relationship edges.

    Capped at three hops and scored by the weakest link — a chain is only
    as good as its weakest introduction, and a four-hop path is a
    theoretical connection rather than a usable one.
    """
    edges = db.query(RelationshipEdge).all()
    adjacency: dict[str, list[RelationshipEdge]] = {}
    for e in edges:
        key = f"{e.from_type}:{e.from_id or 'vecta'}"
        adjacency.setdefault(key, []).append(e)

    start = "vecta:vecta"
    target = f"stakeholder:{target_stakeholder_id}"

    paths: list[dict] = []
    queue: deque = deque([(start, [], 100)])
    visited: set[str] = set()

    while queue:
        node, path, weakest = queue.popleft()
        if len(path) >= max_hops:
            continue
        for edge in adjacency.get(node, []):
            next_node = f"{edge.to_type}:{edge.to_id}"
            if next_node in visited:
                continue
            new_weakest = min(weakest, edge.strength)
            new_path = path + [
                {
                    "from": node,
                    "to": next_node,
                    "edge_type": edge.edge_type,
                    "strength": edge.strength,
                    "via": edge.owner_name,
                }
            ]
            if next_node == target:
                paths.append(
                    {
                        "hops": len(new_path),
                        "weakest_link": new_weakest,
                        "is_viable": new_weakest >= VIABLE_PATH_MIN_STRENGTH,
                        "path": new_path,
                    }
                )
            else:
                visited.add(next_node)
                queue.append((next_node, new_path, new_weakest))

    # Fewest hops first, then strongest weakest-link.
    paths.sort(key=lambda p: (p["hops"], -p["weakest_link"]))
    return paths


def influence_graph(db: Session, opportunity_id: str | None = None) -> dict:
    """Nodes and edges for the relationship network.

    Returned as data rather than a rendered layout — the visualisation is
    a presentation concern, and computing positions server-side would
    couple the two.
    """
    query = db.query(Stakeholder)
    if opportunity_id:
        ids = [
            l.stakeholder_id
            for l in db.query(OpportunityStakeholder)
            .filter_by(opportunity_id=opportunity_id)
            .all()
        ]
        query = query.filter(Stakeholder.id.in_(ids)) if ids else query.filter(False)

    stakeholders = query.all()
    nodes = [{"id": "vecta", "type": "vecta", "label": "VECTA Sports", "group": "internal"}]
    organisations: set[str] = set()

    for s in stakeholders:
        health = db.query(RelationshipHealth).filter_by(stakeholder_id=s.id).first()
        nodes.append(
            {
                "id": s.id,
                "type": "stakeholder",
                "label": s.full_name,
                "role": s.role_title,
                "organisation": s.organisation_name,
                "stakeholder_type": s.stakeholder_type,
                "posture": s.posture,
                "group": s.posture,
                "influence": engine.influence_component(
                    s.stakeholder_type, s.decision_authority
                )["score"],
                "health": health.score if health else None,
                "health_band": health.band_label if health else "Not assessed",
                "is_known": bool(s.last_engagement_at),
            }
        )
        if s.organisation_name and s.organisation_name not in organisations:
            organisations.add(s.organisation_name)
            nodes.append(
                {
                    "id": f"org:{s.organisation_name}",
                    "type": "organisation",
                    "label": s.organisation_name,
                    "group": "organisation",
                }
            )

    node_ids = {n["id"] for n in nodes}
    edges = []
    for e in db.query(RelationshipEdge).all():
        source = e.from_id or "vecta"
        if source in node_ids and e.to_id in node_ids:
            edges.append(
                {
                    "source": source,
                    "target": e.to_id,
                    "type": e.edge_type,
                    "strength": e.strength,
                    "is_vecta": e.is_vecta_relationship,
                }
            )

    # Organisation membership, so the graph shows structure not just contacts.
    for s in stakeholders:
        if s.organisation_name:
            edges.append(
                {
                    "source": s.id,
                    "target": f"org:{s.organisation_name}",
                    "type": "employed_by",
                    "strength": 100,
                    "is_vecta": False,
                }
            )

    return {
        "nodes": nodes,
        "edges": edges,
        "stakeholder_count": len(stakeholders),
        "unknown_count": sum(1 for s in stakeholders if not s.last_engagement_at),
    }


def relationship_timeline(db: Session, stakeholder_id: str) -> dict:
    """Engagements and milestones merged chronologically.

    Milestones are separated in the model precisely so they can be
    emphasised here — four material moments buried among two hundred
    emails make "how did this evolve?" unanswerable.
    """
    engagements = (
        db.query(Engagement)
        .filter_by(stakeholder_id=stakeholder_id)
        .order_by(Engagement.occurred_at.desc())
        .limit(100)
        .all()
    )
    milestones = (
        db.query(StakeholderMilestone)
        .filter_by(stakeholder_id=stakeholder_id)
        .order_by(StakeholderMilestone.occurred_at.desc())
        .all()
    )
    history = (
        db.query(RelationshipHealthHistory)
        .filter_by(stakeholder_id=stakeholder_id)
        .order_by(RelationshipHealthHistory.recorded_at.asc())
        .all()
    )

    items = []
    for e in engagements:
        items.append(
            {
                "kind": "engagement",
                "type": e.engagement_type,
                "occurred_at": e.occurred_at.isoformat() if e.occurred_at else None,
                "summary": e.summary,
                "outcome": e.outcome,
                "commitment": e.commitment_made,
                "follow_up": e.follow_up_action,
                "follow_up_overdue": bool(
                    e.follow_up_due and not e.follow_up_completed
                    and e.follow_up_due < date.today()
                ),
                "is_milestone": False,
            }
        )
    for m in milestones:
        items.append(
            {
                "kind": "milestone",
                "type": m.milestone_type,
                "occurred_at": m.occurred_at.isoformat() if m.occurred_at else None,
                "summary": m.summary,
                "influence_change": (
                    f"{m.influence_before} → {m.influence_after}"
                    if m.influence_before is not None and m.influence_after is not None
                    else None
                ),
                "trust_change": (
                    f"{m.trust_before} → {m.trust_after}"
                    if m.trust_before and m.trust_after else None
                ),
                "is_milestone": True,
            }
        )

    items.sort(key=lambda i: i["occurred_at"] or "", reverse=True)

    return {
        "stakeholder_id": stakeholder_id,
        "items": items,
        "health_series": [
            {
                "score": h.score,
                "band": h.band,
                "recorded_at": h.recorded_at.isoformat() if h.recorded_at else None,
            }
            for h in history
        ],
        "milestone_count": len(milestones),
        "engagement_count": len(engagements),
    }


# ═════════════════ Relationship Coverage Index (Sprint 2.1) ═════════════════

# Maps stakeholder types onto the coverage roles. `operational_champion`
# has no stakeholder_type of its own — it is a posture (champion) rather
# than a position, which is why posture is modelled separately.
_ROLE_SOURCES = {
    "economic_buyer": ("economic_buyer",),
    "budget_holder": ("budget_holder",),
    "procurement_authority": ("procurement_authority",),
    "technical_evaluator": ("technical_evaluator", "technical_influencer"),
    "political_sponsor": ("political_sponsor", "programme_sponsor"),
}


def _engagement_state(db: Session, stakeholder: Stakeholder,
                      link: OpportunityStakeholder | None,
                      health: RelationshipHealth | None) -> str:
    """Which of the five coverage states this stakeholder occupies.

    Identification alone is not coverage — a mapped contact nobody has
    spoken to does not improve win probability, and scoring it as though
    it does would reward data entry over engagement.
    """
    posture = (link.posture if link else None) or stakeholder.posture
    if posture == "champion" and health and health.score >= 60:
        return "advocating"

    engagements = (
        db.query(Engagement).filter_by(stakeholder_id=stakeholder.id).count()
    )
    if engagements == 0 and not stakeholder.last_engagement_at:
        return "identified"
    if health and health.score >= 60:
        return "engaged"
    return "contacted"


def compute_coverage_index(db: Session, opportunity_id: str) -> dict:
    """RCI for one opportunity, assembled from the stakeholder model."""
    from .. import coverage_index as cov

    opp = db.get(Opportunity, opportunity_id)
    if opp is None:
        return {"available": False, "reason": "Opportunity not found"}

    links = (
        db.query(OpportunityStakeholder, Stakeholder)
        .join(Stakeholder, Stakeholder.id == OpportunityStakeholder.stakeholder_id)
        .filter(OpportunityStakeholder.opportunity_id == opportunity_id)
        .all()
    )

    by_type: dict[str, tuple] = {}
    champions: list[tuple] = []
    healths: list[int] = []
    declining = 0
    latest_engagement: datetime | None = None

    for link, s in links:
        health = db.query(RelationshipHealth).filter_by(stakeholder_id=s.id).first()
        momentum = _momentum_for(db, s)
        if health:
            healths.append(health.score)
        if momentum["state"] in ("declining", "critical"):
            declining += 1
        if s.last_engagement_at:
            aware = as_aware(s.last_engagement_at)
            if latest_engagement is None or aware > latest_engagement:
                latest_engagement = aware

        record = (s, link, health, momentum)
        by_type.setdefault(s.stakeholder_type, record)
        if (link.posture or s.posture) == "champion":
            champions.append(record)

    role_states: list[dict] = []
    for role in cov.COVERAGE_ROLES:
        key = role["key"]
        record = None
        if key == "operational_champion":
            record = champions[0] if champions else None
        else:
            for source_type in _ROLE_SOURCES.get(key, (key,)):
                if source_type in by_type:
                    record = by_type[source_type]
                    break

        if record is None:
            role_states.append({"role": key, "state": "unknown"})
            continue

        s, link, health, momentum = record
        role_states.append(
            {
                "role": key,
                "state": _engagement_state(db, s, link, health),
                "health_score": health.score if health else None,
                "momentum_state": momentum["state"],
                "stakeholder_name": s.full_name,
            }
        )

    # A warm route only counts toward coverage if it reaches an unmapped
    # critical role — an introduction to someone already engaged adds
    # nothing.
    warm_available = False
    unknown_critical = [
        r["role"] for r in role_states
        if r["state"] == "unknown"
        and any(c["key"] == r["role"] and c["critical"] for c in cov.COVERAGE_ROLES)
    ]
    if unknown_critical:
        warm_available = _has_warm_route(db, opportunity_id)

    days_since = (
        (utcnow() - latest_engagement).days if latest_engagement else None
    )
    result = cov.compute_coverage(
        role_states,
        warm_introduction_available=warm_available,
        days_since_any_engagement=days_since,
        mean_health=round(sum(healths) / len(healths)) if healths else None,
        declining_count=declining,
    )

    days_to_deadline = (
        (opp.deadline - date.today()).days if opp.deadline else None
    )
    result["available"] = True
    result["opportunity_id"] = opportunity_id
    result["opportunity_title"] = opp.title
    result["stakeholders_mapped"] = len(links)
    result["days_to_deadline"] = days_to_deadline
    result["pursuit_recommendation"] = cov.pursuit_recommendation(result, days_to_deadline)
    return result


def _has_warm_route(db: Session, opportunity_id: str) -> bool:
    """Is there any viable introduction path into this opportunity's
    ecosystem? Cheap check — the full path search runs on demand."""
    cached = (
        db.query(IntroductionPath)
        .filter_by(opportunity_id=opportunity_id, is_viable=True)
        .first()
    )
    if cached:
        return True
    return (
        db.query(RelationshipEdge)
        .filter(RelationshipEdge.is_vecta_relationship.is_(True),
                RelationshipEdge.strength >= VIABLE_PATH_MIN_STRENGTH)
        .first()
        is not None
    )


def coverage_across_pipeline(db: Session, limit: int = 10) -> list[dict]:
    """RCI for every actionable opportunity, worst first.

    Answers "where are we exposed?" across the pipeline rather than one
    opportunity at a time.
    """
    rows = (
        db.query(Opportunity, ExecutiveFocus)
        .join(ExecutiveFocus, ExecutiveFocus.opportunity_id == Opportunity.id)
        .filter(ExecutiveFocus.is_actionable.is_(True))
        .order_by(ExecutiveFocus.score.desc())
        .limit(limit * 2)
        .all()
    )
    out = []
    for opp, focus in rows:
        coverage = compute_coverage_index(db, opp.id)
        if not coverage.get("available"):
            continue
        out.append(
            {
                "opportunity_id": opp.id,
                "opportunity_title": opp.title,
                "focus_score": focus.score,
                "coverage_score": coverage["score"],
                "coverage_band": coverage["band_label"],
                "explanation": coverage["explanation"],
                "missing_critical": coverage["missing_critical"],
                "gap_counts": coverage["gap_counts"],
                "biggest_lever": coverage["biggest_lever"],
                "pursuit_recommendation": coverage["pursuit_recommendation"],
                # Exposure is the product of how much we care and how
                # little we cover — a high-focus opportunity with thin
                # coverage is the most dangerous combination.
                "exposure": round(focus.score * (100 - coverage["score"]) / 100),
            }
        )
    out.sort(key=lambda r: -r["exposure"])
    return out[:limit]
