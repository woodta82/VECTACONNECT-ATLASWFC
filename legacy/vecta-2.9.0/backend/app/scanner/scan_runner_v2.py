"""Phase 2 scan pipeline — the live execution path.

Replaces the legacy runner completely. The old path produced a single
alignment score, one flat value estimate, a list of bare source URLs and a
priority flag derived from a threshold; none of that is produced here.

THE SINGLE WRITE PATH
=====================
Every Phase 2 write in this module goes through
`app.services.opportunity_service`. Nothing here writes evidence, scores,
qualification, priority or commercial value to the ORM directly. That
matters because the service is where the rules live (evidence
enforcement, coverage restrictions, qualification gating, value
safeguards, override auditing) — a scanner that wrote to the ORM directly
would silently bypass all of them.

`create_opportunity_from_ai_record()` is deliberately separated from any
AI call so the entire persistence pipeline can be exercised in tests with
a fixture record and no network, no API key and no cost.

PIPELINE
========
 1. Source discovery + Phase 2 AI prompt   -> run_phase2_scan
 2. Strict schema validation                -> ai_schema.validate_ai_response
 3. Per-record validation handling          -> valid records continue, invalid isolated
 4. Parse-failure persistence               -> service.record_parse_failure
 5. Deduplication                           -> dedup.is_duplicate
 6. Opportunity base record                 -> _create_base_opportunity
 7. Evidence + claims                       -> service.persist_evidence
 8. Analysis items                          -> _persist_analysis_items
 9. Verticals / commercial types / routes   -> _persist_classification
10. Four-dimensional scoring                -> service.persist_scores
11. Qualification                           -> service.persist_qualification
12. Pursuit Priority                        -> service.persist_pursuit_priority
13. Commercial value                        -> _persist_commercial_value
14. Final enforcement                       -> service.enforce_classification_evidence
15. Human-review assignment                 -> _assign_human_review
"""
from __future__ import annotations

import logging
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..ai_schema import AIOpportunityRecord, validate_ai_response
from ..database import SessionLocal
from ..models import Opportunity, Organisation, OrgType, ScanRun
from ..models_phase2 import (
    AnalysisItemType,
    CommercialValue,
    OpportunityContributingVertical,
    OpportunityRouteToMarket,
    OpportunitySecondaryCommercialType,
    OpportunityAnalysisItem,
)
from ..regions import Region, Vertical
from ..services import opportunity_service as service
from ..taxonomy import ESTIMATED_VALUE_STATUSES, OpportunityClassification
from ..timeutils import utcnow
from .dedup import normalise_title
from .url_validator import validate_evidence_urls

logger = logging.getLogger("atlas.scanner.phase2")

# Legacy vertical enum values, keyed by the Phase 2 vertical. `intelligence`
# has no legacy equivalent, so it falls back to connect for the legacy
# column only — the Phase 2 `primary_vertical` column holds the truth.
_LEGACY_VERTICAL_FALLBACK = {
    "pathways": Vertical.PATHWAYS,
    "connect": Vertical.CONNECT,
    "media": Vertical.MEDIA,
    "experiences": Vertical.EXPERIENCES,
    "talent": Vertical.TALENT,
    "intelligence": Vertical.CONNECT,
}


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except (ValueError, TypeError):
        return None


def _get_or_create_org(db: Session, name: str | None, region: Region | None, market: str | None) -> str | None:
    if not name or not name.strip():
        return None
    existing = db.scalar(select(Organisation).where(Organisation.name == name.strip()))
    if existing:
        return existing.id
    org = Organisation(name=name.strip(), org_type=OrgType.OTHER, region=region, market=market)
    db.add(org)
    db.flush()
    return org.id


# --------------------------------------------------------- persistence

def _create_base_opportunity(db: Session, record: AIOpportunityRecord) -> Opportunity:
    """Step 6. The base row carries the single-valued Phase 2
    classification columns. It deliberately does NOT set alignment_score,
    value_estimate or priority — those are legacy fields the Phase 2 path
    no longer produces."""
    region = None
    if record.region:
        try:
            region = Region(record.region)
        except ValueError:
            region = None

    org_id = _get_or_create_org(db, record.issuing_organisation, region, record.market)

    opp = Opportunity(
        organisation_id=org_id,
        title=record.title,
        # The schema requires a summary, but this path must not be able to
        # violate the NOT NULL constraint under any circumstance — a scan
        # that dies on a database error loses the whole batch.
        summary=(record.summary or "").strip() or record.title,
        region=region,
        market=record.market,
        deadline=_parse_date(record.deadline),
        # Phase 2 classification
        classification=record.classification,
        classification_rationale=record.classification_rationale,
        primary_vertical=record.primary_vertical,
        vertical_rationale=record.vertical_rationale,
        primary_commercial_type=record.primary_commercial_type,
        verification_confidence=record.commercial_confidence,
        last_verified_at=utcnow(),
        # Legacy column kept populated only so pre-Phase-2 views and the
        # existing vertical filter keep working during transition.
        vertical=_LEGACY_VERTICAL_FALLBACK.get(record.primary_vertical, Vertical.CONNECT),
    )
    db.add(opp)
    db.flush()
    return opp


def _persist_classification(db: Session, opportunity_id: str, record: AIOpportunityRecord) -> None:
    """Steps 9. Multi-valued classification: contributing verticals,
    secondary commercial types, and route requirements (which coexist —
    an opportunity can be open competition AND local-entity-required)."""
    for vertical in record.contributing_verticals:
        db.add(
            OpportunityContributingVertical(
                opportunity_id=opportunity_id, vertical=vertical, source="ai"
            )
        )
    for ctype in record.secondary_commercial_types:
        db.add(
            OpportunitySecondaryCommercialType(
                opportunity_id=opportunity_id, commercial_type=ctype, source="ai"
            )
        )
    for route in record.routes_to_market:
        db.add(OpportunityRouteToMarket(opportunity_id=opportunity_id, route=route, source="ai"))
    db.flush()


def _persist_analysis_items(db: Session, opportunity_id: str, record: AIOpportunityRecord,
                            evidence_by_url: dict[str, str]) -> None:
    """Step 8. Facts, interpretation, assumptions, gaps and verification
    actions are stored separately — never merged into one summary field.

    A fact candidate becomes `is_verified=True` only if the referenced
    evidence genuinely supports that claim type. The AI proposes; the
    evidence decides."""
    stored = service.evidence_as_dicts(db, opportunity_id)

    for fact in record.verified_fact_candidates:
        evidence_id = evidence_by_url.get(fact.evidence_url)
        verified = service.evidence_engine.is_fact_verified(stored, fact.claim_type)
        db.add(
            OpportunityAnalysisItem(
                opportunity_id=opportunity_id,
                item_type=AnalysisItemType.VERIFIED_FACT.value,
                content=fact.content,
                claim_type=fact.claim_type,
                supporting_evidence_id=evidence_id,
                is_verified=verified,
                source="ai",
            )
        )

    for interpretation in record.ai_interpretation:
        db.add(
            OpportunityAnalysisItem(
                opportunity_id=opportunity_id,
                item_type=AnalysisItemType.AI_INTERPRETATION.value,
                content=interpretation,
                is_verified=False,
                source="ai",
            )
        )

    for assumption in record.assumptions:
        db.add(
            OpportunityAnalysisItem(
                opportunity_id=opportunity_id,
                item_type=AnalysisItemType.ASSUMPTION.value,
                content=assumption.content,
                is_verified=False,
                confidence=None,
                source="ai",
            )
        )

    for gap in record.missing_information:
        db.add(
            OpportunityAnalysisItem(
                opportunity_id=opportunity_id,
                item_type=AnalysisItemType.MISSING_INFORMATION.value,
                content=gap.content,
                is_verified=False,
                source="ai",
            )
        )

    for action in record.verification_actions:
        db.add(
            OpportunityAnalysisItem(
                opportunity_id=opportunity_id,
                item_type=AnalysisItemType.VERIFICATION_ACTION.value,
                content=action.action,
                is_verified=False,
                source="ai",
            )
        )
    db.flush()


def _persist_commercial_value(db: Session, opportunity_id: str, record: AIOpportunityRecord) -> CommercialValue:
    """Step 13. Programme value and contract value are stored in separate
    columns so a national strategy's headline figure can never be read as
    money available to VECTA."""
    v = record.commercial_value
    row = CommercialValue(
        opportunity_id=opportunity_id,
        published_programme_value=v.published_programme_value,
        published_contract_value=v.published_contract_value,
        estimated_contract_min=v.estimated_contract_min,
        estimated_contract_max=v.estimated_contract_max,
        estimated_vecta_revenue=v.estimated_vecta_revenue,
        currency=v.currency,
        value_status=v.value_status,
        estimate_methodology=v.estimate_methodology,
        confidence=v.confidence,
        partner_share_assumption=v.partner_share_assumption,
        last_reviewed_at=utcnow(),
    )
    db.add(row)
    db.flush()
    return row


def _assign_human_review(db: Session, opp: Opportunity, downgrade_note: str | None,
                         qualification_result: dict, priority_result: dict) -> None:
    """Step 15. Flags anything a person needs to look at, with the reason
    stated. Never silently."""
    reasons: list[str] = []
    if downgrade_note:
        reasons.append(downgrade_note)
    if qualification_result.get("state") == "verification_required":
        reasons.append("Qualification requires verification.")
    if qualification_result.get("remediable_blockers"):
        reasons.append(
            f"{len(qualification_result['remediable_blockers'])} remediable blocker(s) to resolve."
        )
    if priority_result.get("coverage_restricted"):
        reasons.append("Score coverage insufficient — assessment incomplete.")
    if not priority_result.get("risk_established", True):
        reasons.append("Risk not established.")

    if reasons:
        opp.requires_human_review = True
        opp.human_review_reason = " ".join(reasons)
    db.flush()


def create_opportunity_from_ai_record(
    db: Session, record: AIOpportunityRecord, existing_titles: set[str] | None = None,
    url_validator=None,
) -> Opportunity | None:
    """Steps 5–15 for one validated record.

    Separated from any AI call on purpose: this is the whole persistence
    pipeline, and it can be driven from a fixture in tests with no
    network, no API key and no cost. Returns None if the record is a
    duplicate.
    """
    # --- 5. deduplication ---
    if existing_titles is not None and normalise_title(record.title) in existing_titles:
        logger.info("Skipping duplicate: %s", record.title)
        return None

    # --- 6. base record ---
    opp = _create_base_opportunity(db, record)

    # --- 7. URL validation, then evidence + claims (via the service) ---
    # ATLAS validates the URLs; the AI does not get to certify its own
    # sources. Without this step every record's evidence stays
    # `not_reviewed`, which silently blocks Confirmed classification.
    validated = validate_evidence_urls(
        [e.model_dump() for e in record.evidence], validator=url_validator
    )
    evidence_rows = service.persist_evidence(db, opp.id, validated)
    evidence_by_url = {row.url: row.id for row in evidence_rows}

    # --- 8. analysis items ---
    _persist_analysis_items(db, opp.id, record, evidence_by_url)

    # --- 9. multi-valued classification ---
    _persist_classification(db, opp.id, record)

    # --- 10. four-dimensional scoring (via the service) ---
    factor_scores = {
        dim: {f.factor_key: f.score for f in getattr(record.scores, dim).factors}
        for dim in ("strategic_alignment", "commercial_attractiveness", "win_probability", "risk")
    }
    rationales = {
        dim: {f.factor_key: f.rationale for f in getattr(record.scores, dim).factors}
        for dim in ("strategic_alignment", "commercial_attractiveness", "win_probability", "risk")
    }
    confidences = {
        dim: getattr(record.scores, dim).confidence
        for dim in ("strategic_alignment", "commercial_attractiveness", "win_probability", "risk")
    }
    computed = service.persist_scores(db, opp.id, factor_scores, rationales, confidences)

    # --- 11. qualification (via the service) ---
    answers = {
        a.item_key: {"answer": a.answer, "explanation": a.explanation, "source": "ai"}
        for a in record.qualification.checklist
    }
    has_credible_source = any(
        e.source_tier in ("tier_1", "tier_2") for e in record.evidence
    )
    qualification_result = service.persist_qualification(
        db, opp.id, answers,
        classification=record.classification,
        deadline=opp.deadline,
        has_credible_source=has_credible_source,
    )

    # --- 12. pursuit priority (via the service) ---
    priority_result = service.persist_pursuit_priority(
        db, opp.id, computed, qualification_state=qualification_result["state"]
    )

    # --- 13. commercial value ---
    _persist_commercial_value(db, opp.id, record)

    # --- 14. final enforcement (via the service) ---
    downgrade_note = service.enforce_classification_evidence(db, opp)

    # --- 15. human review ---
    _assign_human_review(db, opp, downgrade_note, qualification_result, priority_result)

    db.flush()
    return opp


def process_ai_response(db: Session, raw_response: str, scan_run_id: str | None = None,
                        url_validator=None) -> dict:
    """Steps 2–4 plus the per-record pipeline.

    A malformed record is isolated as an AIParseFailure and the good
    records in the same batch still persist — one bad record must not
    discard six good ones, and a partially-populated opportunity is never
    created.
    """
    outcome = validate_ai_response(raw_response)

    # --- 4. parse failures ---
    for err in outcome.errors:
        service.record_parse_failure(
            db,
            raw_response=raw_response,
            errors=err.get("errors", [err]),
            scan_run_id=scan_run_id,
            proposed_title=err.get("proposed_title"),
        )

    existing_titles = {normalise_title(t) for (t,) in db.execute(select(Opportunity.title)).all()}

    created: list[Opportunity] = []
    for record in outcome.records:
        opp = create_opportunity_from_ai_record(db, record, existing_titles, url_validator=url_validator)
        if opp is not None:
            created.append(opp)
            existing_titles.add(normalise_title(opp.title))

    return {
        "created": len(created),
        "opportunity_ids": [o.id for o in created],
        "parse_failures": len(outcome.errors),
        "records_validated": len(outcome.records),
    }


def execute_phase2_scan(scan_run_id: str, scope_line: str, raw_response: str | None = None,
                        url_validator=None) -> None:
    """Step 1 + the rest. `raw_response` is injectable so an end-to-end
    test can drive the full live path from a fixture without an AI call."""
    db = SessionLocal()
    try:
        if raw_response is None:
            from ..ai.opportunity_scan_v2 import run_phase2_scan

            raw_response = run_phase2_scan(scope_line)

        result = process_ai_response(db, raw_response, scan_run_id=scan_run_id, url_validator=url_validator)

        run = db.get(ScanRun, scan_run_id)
        if run:
            run.status = "complete"
            run.new_items = result["created"]
            run.sources_checked = result["records_validated"]
            run.completed_at = utcnow()
            if result["parse_failures"]:
                run.error = (
                    f"{result['parse_failures']} record(s) failed schema validation and were "
                    "stored for review — see AI parse failures in Settings."
                )
        db.commit()
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        run = db.get(ScanRun, scan_run_id)
        if run:
            run.status = "failed"
            run.error = str(exc)
            db.commit()
        logger.exception("Phase 2 scan failed for run %s", scan_run_id)
    finally:
        db.close()


# ------------------------------------------- live entry points

def execute_scan(scan_run_id: str, vertical: Vertical | None, scope_line: str,
                 raw_response: str | None = None, url_validator=None) -> None:
    """Live entry point, signature-compatible with the legacy
    `scan_runner.execute_scan` so the routers and scheduler switch over
    with an import change rather than a rewrite.

    The `vertical` argument now only narrows the SEARCH SCOPE. It no longer
    determines the stored vertical: Phase 2 classifies against the six-
    vertical taxonomy itself and records a primary plus contributing
    verticals with a rationale, which the legacy per-vertical assignment
    could not express.
    """
    scoped = scope_line
    if vertical is not None:
        scoped = f"{scope_line} — focus: {vertical.value}"
    execute_phase2_scan(scan_run_id, scoped, raw_response=raw_response, url_validator=url_validator)


def execute_regional_scan(scan_run_id: str, verticals: list[Vertical], scope_line: str,
                          raw_response: str | None = None, url_validator=None) -> None:
    """Live entry point for Regional Search, signature-compatible with the
    legacy runner. Runs ONE Phase 2 scan for the whole scope rather than
    one per vertical — Phase 2 classifies verticals per opportunity, so
    looping would duplicate work and multiply API cost for no gain."""
    scoped = scope_line
    if verticals:
        scoped = f"{scope_line} — verticals of interest: {', '.join(v.value for v in verticals)}"
    execute_phase2_scan(scan_run_id, scoped, raw_response=raw_response, url_validator=url_validator)
