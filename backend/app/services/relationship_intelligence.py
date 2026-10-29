"""Relationship intelligence to the ATLAS v1.0 parameters (29 Oct 2026): health, momentum, the five questions, the impact of
relationships on an opportunity's score, stakeholder judgements and outreach drafts.

Everything here is computed on read from recorded facts (engagements and their outcomes, the team's stakeholder judgements,
opportunity links, the discovery briefs). Nothing is stored as a score, so a change in the record changes the answer at
once and nothing goes stale. Outreach is drafted, never sent: a person edits, sends and records it as sent.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from ..ai import extraction as ai_extraction
from ..config import Settings
from ..domain import opportunity_score as sc
from ..domain import overview as ov
from ..domain import relationship_health as rh
from ..domain import relationships as rel
from ..reference.geography import COUNTRIES
from ..repo.db import Database
from .audit import RequestMeta, audit


class IntelligenceRejected(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status, self.detail = status, detail


# ===================================================================== health per person
def _months_between(a: Any, b: datetime) -> int | None:
    d = rh._dt(a)
    return None if d is None else int((b - d).days // 30)


def _opp_score(link: dict[str, Any], now: datetime) -> int | None:
    r = dict(link, kind="opportunity", id=link["opportunity_id"], deadline_at=link.get("deadline_at"))
    s = sc.score(r, now)
    return s["score"] if s else None


def health_for(person: dict[str, Any], stats: dict[str, Any] | None, recent: list[dict[str, Any]], links: list[dict[str, Any]],
               scope_countries: set[str], now: datetime) -> dict[str, Any]:
    """Health, momentum, attention and the recommended action for one person from the recorded facts."""
    stats = stats or {}
    judged = (person.get("stakeholder_type") or "unknown") != "unknown" or (person.get("decision_authority") or "unknown") != "unknown"
    assessed = int(stats.get("total") or 0) > 0 or judged
    countries = [c for c in ([person.get("organisation_country")] + list(person.get("remit_countries") or [])) if c]
    live = [l for l in links if l.get("person_id") == person["id"]]
    best = max((s for s in (_opp_score(l, now) for l in live) if s is not None), default=None)
    comps = {
        "recency": rh.recency(stats.get("last_engagement"), now),
        "frequency": rh.frequency(int(stats.get("engagements_12m") or 0), _months_between(stats.get("first_engagement"), now)),
        "responsiveness": rh.responsiveness(int(stats.get("outbound") or 0), int(stats.get("answered") or 0)),
        "meeting_outcomes": rh.meeting_outcomes(int(stats.get("positive") or 0), int(stats.get("neutral") or 0), int(stats.get("negative") or 0)),
        "influence": rh.influence(person.get("stakeholder_type"), person.get("decision_authority")),
        "opportunity_alignment": rh.opportunity_alignment(len(live), best),
        "strategic_value": rh.strategic_value(bool(person.get("strategic_account")), any(c in scope_countries for c in countries),
                                              person.get("organisation_kind")),
    }
    h = rh.compute(comps, assessed=assessed)
    mom = rh.momentum(recent, now)
    inf = comps["influence"]["score"]
    return {"health": h, "explanation": rh.explain(h), "momentum": mom, "influence": comps["influence"],
            "attention": rh.attention(h, mom, inf), "recommended_action": rh.recommended_action(person, h, mom),
            "live_opportunities": [{"id": str(l["opportunity_id"]), "title": l["title"], "score": _opp_score(l, now)} for l in live]}


def person_health(db: Database, person_id: str, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    p = db.one("rel_person_get", id=person_id)
    if p is None:
        raise IntelligenceRejected(404, "Person not found")
    stats = db.one("rel_engagement_stats", id=person_id)
    recent = db.all("rel_engagements_recent", id=person_id)
    links = [l for l in db.all("rel_person_live_links_all") if str(l["person_id"]) == str(person_id)]
    scope = {r["code"] for r in db.all("saved_search_countries")}
    p["id"] = str(p["id"])
    out = health_for(p, stats, recent, [dict(l, person_id=str(l["person_id"])) for l in links], scope, now)
    out["stakeholder"] = {"type": p.get("stakeholder_type") or "unknown", "type_label": rh.STAKEHOLDER_TYPES.get(p.get("stakeholder_type") or "unknown"),
                          "decision_authority": p.get("decision_authority") or "unknown",
                          "decision_authority_label": rh.DECISION_AUTHORITY.get(p.get("decision_authority") or "unknown"),
                          "posture": p.get("posture") or "unknown", "posture_label": rh.POSTURES.get(p.get("posture") or "unknown"),
                          "basis": p.get("judgement_basis"), "by": p.get("judgement_by_label"), "at": p.get("judgement_at"),
                          "key_interests": p.get("key_interests"), "strategic_account": bool(p.get("strategic_account"))}
    return out


def _everyone(db: Database, now: datetime) -> list[dict[str, Any]]:
    people = db.all("rel_people_all_for_health")
    stats = {str(s["person_id"]): s for s in db.all("rel_engagement_stats_all")}
    recent: dict[str, list[dict[str, Any]]] = {}
    for e in db.all("rel_engagements_recent_all"):
        recent.setdefault(str(e["person_id"]), []).append(e)
    links = [dict(l, person_id=str(l["person_id"])) for l in db.all("rel_person_live_links_all")]
    scope = {r["code"] for r in db.all("saved_search_countries")}
    out = []
    for p in people:
        p["id"] = str(p["id"])
        h = health_for(p, stats.get(p["id"]), recent.get(p["id"], []), links, scope, now)
        out.append({"person_id": p["id"], "name": p["full_name"], "role": p.get("role_title"), "organisation": p.get("organisation"),
                    "state": p.get("state"), "state_label": rel.STATE_LABELS.get(p.get("state") or "", p.get("state")),
                    "stakeholder_type": p.get("stakeholder_type") or "unknown",
                    "stakeholder_label": rh.STAKEHOLDER_TYPES.get(p.get("stakeholder_type") or "unknown"),
                    "decision_authority": p.get("decision_authority") or "unknown", "posture": p.get("posture") or "unknown",
                    "relationship_owner": p.get("relationship_owner"), "next_action": p.get("next_action"), "next_action_due": p.get("next_action_due"),
                    "health_score": h["health"]["score"], "health_band": h["health"]["band"], "health_band_label": h["health"]["band_label"],
                    "at_risk": h["health"]["at_risk"], "explanation": h["explanation"], "momentum": h["momentum"]["label"],
                    "momentum_state": h["momentum"]["state"], "momentum_note": h["momentum"]["explanation"],
                    "influence_score": h["influence"]["score"], "influence_note": h["influence"]["note"], "attention": h["attention"],
                    "recommended_action": h["recommended_action"], "live_opportunities": h["live_opportunities"],
                    "strategic_account": bool(p.get("strategic_account")), "last_engagement": (stats.get(p["id"]) or {}).get("last_engagement")})
    return out


def health_index(db: Database, now: datetime | None = None) -> dict[str, dict[str, Any]]:
    """Health summary per person id, for lists."""
    now = now or datetime.now(timezone.utc)
    return {r["person_id"]: r for r in _everyone(db, now)}


# ===================================================================== the five questions
def questions(db: Database, now: datetime | None = None, limit: int = 8) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    everyone = _everyone(db, now)

    # 1. who matters most: commercial consequence, not familiarity
    def importance(r: dict[str, Any]) -> int:
        links = len(r["live_opportunities"])
        base = r["influence_score"] * 0.6 + min(100, links * 30) * 0.25 + (15 if r["strategic_account"] else 0)
        return round(min(100, base))
    matters = sorted(({**_slim(r), "importance": importance(r),
                       "why": r["influence_note"] + (f", linked to {len(r['live_opportunities'])} live opportunit{'y' if len(r['live_opportunities']) == 1 else 'ies'}"
                                                     if r["live_opportunities"] else ", not yet linked to a live opportunity"),
                       "is_known": r["last_engagement"] is not None} for r in everyone),
                     key=lambda x: (-x["importance"], x["name"]))[:limit]

    # 2. who are we missing: live opportunities without a critical stakeholder or without the capability area's target roles
    gaps: list[dict[str, Any]] = []
    for o in db.all("rel_live_opportunities_stakeholders"):
        types = set(o["stakeholder_types"] or [])
        roles_confirmed = set(o["roles_confirmed"] or [])
        s = sc.score({"kind": "opportunity", "id": o["id"], "record_type": o["record_type"], "tender_status": o["tender_status"],
                      "progress": o["progress"], "deadline_at": o.get("deadline_at"), "coverage": o["coverage"], "reviewed_claims": 0}, now)
        focus = s["score"] if s else 0
        if int(o["people"] or 0) == 0:
            gaps.append({"opportunity_id": str(o["id"]), "opportunity_title": o["title"], "missing": "any", "missing_label": "Nobody identified",
                         "severity": "high", "focus": focus, "why": "No person is linked to this live opportunity: it cannot be engaged until someone is found",
                         "recommended_action": f"Research relationships for {o['title']}, or run a contact discovery for the organisation"})
            continue
        for role in rh.CRITICAL_ROLES:
            if role not in types:
                label = rh.STAKEHOLDER_TYPES[role]
                gaps.append({"opportunity_id": str(o["id"]), "opportunity_title": o["title"], "missing": role, "missing_label": label,
                             "severity": "high" if role == "economic_buyer" else "medium", "focus": focus,
                             "why": f"No {label.lower()} judged on a live opportunity (score {focus})",
                             "recommended_action": f"Identify the {label.lower()} for {o['title']} and record the stakeholder judgement"})
        for tr in rel.target_roles(o["module"]):
            if tr.key not in roles_confirmed:
                gaps.append({"opportunity_id": str(o["id"]), "opportunity_title": o["title"], "missing": tr.key, "missing_label": tr.label,
                             "severity": "low", "focus": focus, "why": f"No confirmed {tr.label.lower()} on this opportunity",
                             "recommended_action": f"Confirm or find the {tr.label.lower()} for {o['title']}"})
    order = {"high": 0, "medium": 1, "low": 2}
    gaps.sort(key=lambda g: (order[g["severity"]], -g["focus"], g["opportunity_title"]))

    assessed = [r for r in everyone if r["health_score"] is not None]
    improving = sorted((_slim(r) | {"why": r["momentum_note"]} for r in assessed if r["momentum_state"] == "improving"),
                       key=lambda x: -(x["health_score"] or 0))[:limit]
    at_risk = sorted((_slim(r) | {"why": r["explanation"]} for r in assessed
                      if r["at_risk"] or r["momentum_state"] in ("declining", "dormant") or r["health_band"] in ("weak", "dormant")),
                     key=lambda x: (-x["influence_score"], x["health_score"] or 0))[:limit]
    invest = sorted((_slim(r) | {"why": r["momentum_note"] if r["momentum_state"] != "new" else r["explanation"],
                                 "expected_benefit": _benefit(r)} for r in everyone if r["health_score"] is not None or r["influence_score"] >= 70),
                    key=lambda x: -x["attention"])[:limit]
    return {"who_matters_most": matters, "who_are_we_missing": gaps[: limit * 2], "improving": improving, "at_risk": at_risk,
            "where_to_invest_time": invest,
            "totals": {"people": len(everyone), "assessed": len(assessed), "at_risk": sum(1 for r in assessed if r["at_risk"]),
                       "not_judged": sum(1 for r in everyone if r["stakeholder_type"] == "unknown")},
            "rule": ("Health: recency 24, frequency 16, responsiveness 14, meeting outcomes 14, influence 14, opportunity alignment 10, "
                     "strategic value 8, from recorded engagements and the team's stakeholder judgements; a high-influence relationship "
                     "that has gone quiet is capped at 40. Not a probability of winning; research states are unchanged by it."),
            "generated_at": now}


def _slim(r: dict[str, Any]) -> dict[str, Any]:
    keys = ("person_id", "name", "role", "organisation", "state", "state_label", "stakeholder_type", "stakeholder_label", "posture",
            "health_score", "health_band", "health_band_label", "at_risk", "momentum", "momentum_state", "influence_score", "influence_note",
            "attention", "recommended_action", "live_opportunities", "relationship_owner", "last_engagement")
    return {k: r.get(k) for k in keys}


def _benefit(r: dict[str, Any]) -> str:
    if r["live_opportunities"]:
        best = max((o["score"] or 0) for o in r["live_opportunities"])
        return f"Keeps a route into {len(r['live_opportunities'])} live opportunit{'y' if len(r['live_opportunities']) == 1 else 'ies'} (best score {best})"
    return "Builds a relationship that no live opportunity yet depends on"


# ===================================================================== impact of relationships on an opportunity
def impact(db: Database, opp_id: str, now: datetime | None = None) -> dict[str, Any]:
    """How much of the opportunity's score its relationship position accounts for, and what is still available."""
    now = now or datetime.now(timezone.utc)
    rows = [r for r in db.all("records_list", types=None, modules=None, geo=None, tender=None, progress=None, coverage=None, org=None, q=None,
                              deadline_days=None, saved=None, since=None, id=opp_id, sort="created", limit=1, offset=0)]
    if not rows:
        raise IntelligenceRejected(404, "Opportunity not found")
    r = rows[0]
    s = sc.score(r, now)
    if s is None:
        return {"opportunity_id": opp_id, "scored": False, "reason": "closed, cancelled, awarded, expired or historical records are not scored"}
    comp = next(c for c in s["components"] if c["key"] == "relationships")
    people = db.all("rel_opportunity_people", id=opp_id)
    judged = [p for p in people if (p.get("stakeholder_type") or "unknown") != "unknown"] if people and "stakeholder_type" in people[0] else []
    return {"opportunity_id": opp_id, "scored": True, "score": s["score"], "band_label": s["band_label"],
            "relationship_points": comp["points"], "relationship_max": comp["max"], "headroom": comp["max"] - comp["points"],
            "coverage": r.get("coverage"), "coverage_label": rel.COVERAGE_LABELS.get(r.get("coverage") or "none"),
            "people_linked": len([p for p in people if p.get("link_status") != "not_relevant"]), "people_judged": len(judged),
            "explanation": (f"Relationship position gives {comp['points']} of {comp['max']} points ({comp['reason'].lower()}); "
                            f"{comp['max'] - comp['points']} more are available with an existing relationship or a confirmed introduction. "
                            "This is the score's relationship share, not a probability of winning.")}


# ===================================================================== stakeholder judgements
def set_judgement(db: Database, person_id: str, data: dict[str, Any], meta: RequestMeta) -> None:
    p = db.one("rel_person_get", id=person_id)
    if p is None:
        raise IntelligenceRejected(404, "Person not found")
    if p.get("merged_into_id"):
        raise IntelligenceRejected(409, "this record was merged into another person")
    if data["stakeholder_type"] not in rh.STAKEHOLDER_TYPES or data["decision_authority"] not in rh.DECISION_AUTHORITY or data["posture"] not in rh.POSTURES:
        raise IntelligenceRejected(422, "unknown stakeholder type, decision authority or posture")
    anything = any(data[k] != "unknown" for k in ("stakeholder_type", "decision_authority", "posture"))
    if anything and len((data.get("basis") or "").strip()) < 10:
        raise IntelligenceRejected(422, "give the basis for the judgement (at least 10 characters)")
    with db.transaction() as tx:
        tx.scalar("person_judgement_set", id=person_id, stakeholder_type=data["stakeholder_type"], decision_authority=data["decision_authority"],
                  posture=data["posture"], basis=(data.get("basis") or "").strip() or None, by=data.get("by_label"),
                  key_interests=(data.get("key_interests") or "").strip() or None, strategic=bool(data.get("strategic_account")))
        audit(tx, "stakeholder_judgement", meta, entity_type="person", entity_id=person_id,
              detail={k: data.get(k) for k in ("stakeholder_type", "decision_authority", "posture", "strategic_account")})


# ===================================================================== outreach drafts
_TEMPLATES = {
    "email": ("Introduction from World Freight Company{re}",
              "Dear {salutation},\n\n{opening}\n\nWorld Freight Company represents airlines' cargo capacity and supports forwarders across "
              "{markets}. {why}\n\nWould you have 20 minutes in the coming two weeks for a short call? I would be glad to come to you.\n\n"
              "Kind regards,\n{sender}\nWorld Freight Company"),
    "linkedin_message": (None, "Hello {first}, {opening_short} {why_short} Would you be open to a short call in the next couple of weeks? "
                                "Kind regards, {sender}, World Freight Company"),
    "call_notes": (None, "Call notes for {name}{role_line}\n\nPurpose: {purpose}\nWhat we know: {known}\nAsk: 20-minute meeting or a referral to "
                          "the right person.\nDo not state: anything not recorded in ATLAS about {first}'s authority."),
}


def _draft_from_facts(person: dict[str, Any], opp: dict[str, Any] | None, channel: str, sender: str | None) -> tuple[str | None, str, list[str]]:
    name = person["full_name"]
    first = name.split()[0]
    role = person.get("role_title")
    org = person.get("organisation")
    basis = [f"name and title as recorded: {name}" + (f", {role}" if role else "") + (f" at {org}" if org else "")]
    salutation = f"{name}" if not role else f"{name}"
    opening = (f"I am writing because of {opp['title']}." if opp else
               f"I am writing because of {org}'s cargo activity." if org else "I am writing to introduce World Freight Company.")
    if opp:
        basis.append(f"opportunity as recorded: {opp['title']}")
    markets = ", ".join(COUNTRIES.get(c, (c,))[0] for c in (opp or {}).get("countries", [])[:3]) or "Africa, the Middle East and Asia"
    why = ("We would value a conversation about how we could support it." if opp else
           "We would value a conversation about how we could support your cargo plans.")
    role_line = f" ({role}{', ' + org if org else ''})" if role else (f" ({org})" if org else "")
    known = "; ".join(basis)
    sender = sender or "[your name]"
    subj_tpl, body_tpl = _TEMPLATES[channel]
    values = {"salutation": salutation, "opening": opening, "markets": markets, "why": why, "sender": sender, "first": first,
              "opening_short": opening.lower().replace("i am writing", "I am reaching out"), "why_short": why, "name": name, "role_line": role_line,
              "purpose": (opp or {}).get("title") or "introduce WFC", "known": known, "re": f": {opp['title'][:60]}" if opp else ""}
    subject = subj_tpl.format(**values) if subj_tpl else None
    return subject, body_tpl.format(**values), basis


def draft_outreach(db: Database, settings: Settings, person_id: str, data: dict[str, Any], meta: RequestMeta,
                   transport: ai_extraction.Transport | None = None) -> dict[str, Any]:
    """A draft from the recorded facts only. The configured AI extractor, when connected, may reword it under the budget; the
    template is always the fallback and the basis is always listed. Nothing is sent."""
    p = db.one("rel_person_get", id=person_id)
    if p is None:
        raise IntelligenceRejected(404, "Person not found")
    if p.get("merged_into_id"):
        raise IntelligenceRejected(409, "this record was merged into another person")
    channel = data.get("channel") or "email"
    if channel not in _TEMPLATES:
        raise IntelligenceRejected(422, "channel must be email, linkedin_message or call_notes")
    opp = None
    if data.get("opportunity_id"):
        o = db.one("opportunity_get2", id=data["opportunity_id"])
        if o is None:
            raise IntelligenceRejected(404, "Opportunity not found")
        opp = {"title": o["title"], "countries": [g["country_code"] for g in db.all("opportunity_geo", id=data["opportunity_id"])]}
    subject, body, basis = _draft_from_facts(p, opp, channel, data.get("sender_label"))
    source, cost = "template", Decimal("0")
    ai_reason = ai_extraction.available(settings)
    if not ai_reason and data.get("use_ai", True):
        from ..ai import outreach as ai_outreach
        out = ai_outreach.reword(db, settings, body, basis, transport=transport, required=[p["full_name"], "World Freight Company"])
        cost = out.cost_usd
        if out.status == "ok" and out.text:
            body, source = out.text, "ai"
        else:
            basis.append(f"AI rewording not used: {out.detail or out.status}; template kept")
    elif ai_reason:
        basis.append(f"AI rewording not available: {ai_reason}; template used")
    with db.transaction() as tx:
        did = str(tx.scalar("outreach_insert", person=person_id, opp=data.get("opportunity_id"), channel=channel, subject=subject, body=body,
                            source=source, basis=basis, cost=str(cost), session_ref=meta.session_ref))
        audit(tx, "outreach_drafted", meta, entity_type="person", entity_id=person_id, detail={"channel": channel, "source": source, "cost_usd": str(cost)})
    return dict(db.one("outreach_get", id=did))


def update_draft(db: Database, draft_id: str, subject: str | None, body: str | None, meta: RequestMeta) -> None:
    if not db.scalar("outreach_update", id=draft_id, subject=subject, body=body):
        raise IntelligenceRejected(409, "the draft was not found or is no longer editable (sent or discarded)")
    audit(db, "outreach_edited", meta, entity_type="outreach_draft", entity_id=draft_id)


def set_draft_status(db: Database, draft_id: str, status: str, by: str | None, note: str | None, meta: RequestMeta) -> None:
    if status not in ("sent", "discarded"):
        raise IntelligenceRejected(422, "status must be sent or discarded")
    if status == "sent" and not (by or "").strip():
        raise IntelligenceRejected(422, "record who sent it")
    d = db.one("outreach_get", id=draft_id)
    if d is None:
        raise IntelligenceRejected(404, "Draft not found")
    with db.transaction() as tx:
        if not tx.scalar("outreach_status", id=draft_id, status=status, by=by, note=note):
            raise IntelligenceRejected(409, "the draft is no longer a draft")
        if status == "sent":
            # the send, done by a person, is an outbound engagement awaiting a response
            tx.scalar("rel_engagement_add", person=str(d["person_id"]), opp=str(d["opportunity_id"]) if d.get("opportunity_id") else None,
                      occurred_at=datetime.now(timezone.utc), kind={"email": "email", "linkedin_message": "message", "call_notes": "call"}[d["channel"]],
                      summary=f"Outreach sent by {by}: " + ((d.get("subject") or d["body"][:120]).strip()), owner=by, outcome="pending",
                      next_step=note, direction="outbound", session_ref=meta.session_ref)
            tx.run("rel_person_verified", id=str(d["person_id"]))
        audit(tx, f"outreach_{status}", meta, entity_type="outreach_draft", entity_id=draft_id, detail={"by": by})
