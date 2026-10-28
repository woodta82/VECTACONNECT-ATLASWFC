"""End-to-end Phase 2 integration tests.

Proves the live execution path with fixture AI responses — no network, no
API key, no cost:

    AI fixture -> schema validation -> OpportunityService -> evidence
    -> scoring -> qualification -> priority -> database -> API shape

The spy tests are the important ones. They assert that the *scanner*
invokes the service functions, so if someone later writes Phase 2 data
straight to the ORM from the scanner or a router, these fail — which is
what "the service is the only write path" has to mean to be worth
anything.
"""
import json
from pathlib import Path

import pytest

from app.database import Base, SessionLocal, engine
from app.models import Opportunity

FIXTURES = Path(__file__).parent / "fixtures"


def stub_validator(url: str) -> str:
    """Deterministic offline URL validation.

    Tests must not make network calls, but they DO need evidence to reach
    `valid` — otherwise the Confirmed-Opportunity gate correctly refuses
    and every downstream assertion fails for the wrong reason. This stubs
    the transport only; the persistence and enforcement path is identical
    to production.
    """
    return "valid"


def load_fixture(name: str) -> str:
    return (FIXTURES / name).read_text()


@pytest.fixture(autouse=True)
def fresh_db():
    import app.models  # noqa: F401  (registers Phase 2 tables)

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


# ------------------------------------------------- 1. schema validation

def test_fixture_validates_against_strict_schema():
    from app.ai_schema import validate_ai_response

    outcome = validate_ai_response(load_fixture("scan_valid.json"))
    assert outcome.ok, outcome.errors
    assert len(outcome.records) == 1
    record = outcome.records[0]
    assert record.classification == "confirmed_opportunity"
    assert record.primary_vertical == "pathways"
    assert set(record.contributing_verticals) == {"connect", "intelligence"}
    assert len(record.routes_to_market) == 3  # routes coexist


def test_malformed_record_isolated_not_batch_discarded():
    from app.ai_schema import validate_ai_response

    outcome = validate_ai_response(load_fixture("scan_mixed.json"))
    assert not outcome.ok
    assert len(outcome.records) == 1   # the good record survives
    assert len(outcome.errors) == 1    # the bad one is isolated
    assert outcome.errors[0]["record_index"] == 1


def test_bracket_slicing_no_longer_accepted():
    """The legacy extractor would happily slice JSON out of surrounding
    prose. Strict validation must reject it instead."""
    from app.ai_schema import validate_ai_response

    outcome = validate_ai_response("Here are the results I found:\n[{'title': 'x'}]\nHope that helps!")
    assert not outcome.ok
    assert outcome.records == []


def test_unknown_fields_rejected():
    from app.ai_schema import validate_ai_response

    payload = json.loads(load_fixture("scan_valid.json"))
    payload["records"][0]["invented_field"] = "drifted from the contract"
    outcome = validate_ai_response(json.dumps(payload))
    assert not outcome.ok


def test_fact_citing_nonexistent_evidence_rejected():
    """Guards against the AI inventing a source for a claim."""
    from app.ai_schema import validate_ai_response

    payload = json.loads(load_fixture("scan_valid.json"))
    payload["records"][0]["verified_fact_candidates"][0]["evidence_url"] = "https://invented.example/nope"
    outcome = validate_ai_response(json.dumps(payload))
    assert not outcome.ok


def test_estimated_range_requires_bounds_and_methodology():
    from app.ai_schema import validate_ai_response

    payload = json.loads(load_fixture("scan_valid.json"))
    payload["records"][0]["commercial_value"]["estimate_methodology"] = None
    outcome = validate_ai_response(json.dumps(payload))
    assert not outcome.ok


# --------------------------------------- 2. full pipeline persistence

def test_end_to_end_scan_creates_complete_phase2_opportunity(db):
    from app.models_phase2 import (
        CommercialValue,
        EvidenceClaim,
        OpportunityAnalysisItem,
        OpportunityContributingVertical,
        OpportunityEvidence,
        OpportunityRouteToMarket,
        PursuitPriority,
        QualificationAssessment,
        QualificationChecklistItem,
        ScoreAssessment,
        ScoreFactor,
    )
    from app.scanner.scan_runner_v2 import process_ai_response

    result = process_ai_response(db, load_fixture("scan_valid.json"), url_validator=stub_validator)
    db.commit()

    assert result["created"] == 1
    assert result["parse_failures"] == 0

    opp = db.query(Opportunity).first()
    assert opp.classification == "confirmed_opportunity"
    assert opp.primary_vertical == "pathways"
    assert opp.primary_commercial_type == "coach_education"
    assert opp.classification_rationale and opp.vertical_rationale

    # legacy fields NOT produced by the Phase 2 path
    assert opp.alignment_score == 0
    assert opp.value_estimate is None

    # evidence + claim links
    evidence = db.query(OpportunityEvidence).filter_by(opportunity_id=opp.id).all()
    assert len(evidence) == 2
    tier1 = next(e for e in evidence if e.source_tier == "tier_1")
    claims = {c.claim_type for c in db.query(EvidenceClaim).filter_by(evidence_id=tier1.id).all()}
    assert "live_status" in claims and "deadline" in claims

    # analysis items stored separately by type
    items = db.query(OpportunityAnalysisItem).filter_by(opportunity_id=opp.id).all()
    by_type = {}
    for i in items:
        by_type.setdefault(i.item_type, []).append(i)
    assert len(by_type["verified_fact"]) == 2
    assert len(by_type["ai_interpretation"]) == 2
    assert len(by_type["assumption"]) == 1
    assert len(by_type["missing_information"]) == 2
    assert len(by_type["human_verification_action"]) == 1

    # a fact is verified only because evidence supports that claim type
    deadline_fact = next(f for f in by_type["verified_fact"] if f.claim_type == "deadline")
    assert deadline_fact.is_verified is True

    # multi-valued classification
    assert db.query(OpportunityContributingVertical).filter_by(opportunity_id=opp.id).count() == 2
    assert db.query(OpportunityRouteToMarket).filter_by(opportunity_id=opp.id).count() == 3

    # four dimensions, every factor row stored
    assessments = db.query(ScoreAssessment).filter_by(opportunity_id=opp.id).all()
    assert len(assessments) == 4
    for a in assessments:
        assert a.coverage_percent == 100
        assert a.coverage_band == "assessed"
        factors = db.query(ScoreFactor).filter_by(assessment_id=a.id).all()
        assert all(f.rationale for f in factors), "every factor must carry a rationale"

    risk = next(a for a in assessments if a.dimension == "risk")
    assert risk.risk_established is True

    # priority calculated and unrestricted
    priority = db.query(PursuitPriority).filter_by(opportunity_id=opp.id).first()
    assert priority.final_score > 0
    assert priority.qualification_restricted is False
    assert priority.coverage_restricted is False

    # qualification with full checklist
    qual = db.query(QualificationAssessment).filter_by(opportunity_id=opp.id).first()
    assert qual.state == "qualified"
    assert db.query(QualificationChecklistItem).filter_by(assessment_id=qual.id).count() == 16

    # commercial value — an estimate, never presented as published
    value = db.query(CommercialValue).filter_by(opportunity_id=opp.id).first()
    assert value.value_status == "estimated_range"
    assert value.published_contract_value is None
    assert value.estimated_contract_min == 2500000.0
    assert value.estimate_methodology


def test_parse_failure_persisted_and_good_record_still_created(db):
    from app.models_phase2 import AIParseFailure
    from app.scanner.scan_runner_v2 import process_ai_response

    result = process_ai_response(db, load_fixture("scan_mixed.json"), url_validator=stub_validator)
    db.commit()

    assert result["created"] == 1        # good record survived
    assert result["parse_failures"] == 1
    failure = db.query(AIParseFailure).first()
    assert failure.parse_status == "parsing_failed"
    assert failure.raw_response          # verbatim, for retry
    assert failure.validation_errors["errors"]
    assert db.query(Opportunity).count() == 1  # no partial opportunity from the bad record


def test_thin_risk_coverage_suppresses_score_and_restricts_priority(db):
    from app.models_phase2 import PursuitPriority, ScoreAssessment
    from app.scanner.scan_runner_v2 import process_ai_response

    process_ai_response(db, load_fixture("scan_thin_risk.json"), url_validator=stub_validator)
    db.commit()

    opp = db.query(Opportunity).first()
    risk = db.query(ScoreAssessment).filter_by(opportunity_id=opp.id, dimension="risk").first()
    assert risk.risk_established is False       # a low number from thin data
    assert risk.coverage_percent < 80

    priority = db.query(PursuitPriority).filter_by(opportunity_id=opp.id).first()
    assert priority.coverage_restricted is True
    assert priority.final_score <= 69           # cannot present as High/Immediate
    assert priority.restriction_explanation
    assert opp.requires_human_review is True


def test_duplicate_titles_not_created_twice(db):
    from app.scanner.scan_runner_v2 import process_ai_response

    process_ai_response(db, load_fixture("scan_valid.json"), url_validator=stub_validator)
    db.commit()
    second = process_ai_response(db, load_fixture("scan_valid.json"), url_validator=stub_validator)
    db.commit()

    assert second["created"] == 0
    assert db.query(Opportunity).count() == 1


# ------------------------------------- 3. the service IS the write path

def test_scanner_invokes_service_evidence_persistence(db, monkeypatch):
    """Spy: if the scanner ever writes evidence directly to the ORM
    instead of going through the service, this fails."""
    from app.scanner import scan_runner_v2
    from app.services import opportunity_service as svc

    calls = []
    original = svc.persist_evidence

    def spy(*args, **kwargs):
        calls.append(args[1] if len(args) > 1 else None)
        return original(*args, **kwargs)

    monkeypatch.setattr(svc, "persist_evidence", spy)
    scan_runner_v2.process_ai_response(db, load_fixture("scan_valid.json"), url_validator=stub_validator)
    db.commit()

    assert len(calls) == 1, "scanner did not route evidence through the service"


def test_scanner_invokes_service_scoring(db, monkeypatch):
    from app.scanner import scan_runner_v2
    from app.services import opportunity_service as svc

    calls = []
    original = svc.persist_scores
    monkeypatch.setattr(svc, "persist_scores", lambda *a, **k: (calls.append(1), original(*a, **k))[1])

    scan_runner_v2.process_ai_response(db, load_fixture("scan_valid.json"), url_validator=stub_validator)
    db.commit()
    assert calls, "scanner did not route scoring through the service"


def test_scanner_invokes_service_qualification(db, monkeypatch):
    from app.scanner import scan_runner_v2
    from app.services import opportunity_service as svc

    calls = []
    original = svc.persist_qualification
    monkeypatch.setattr(svc, "persist_qualification", lambda *a, **k: (calls.append(1), original(*a, **k))[1])

    scan_runner_v2.process_ai_response(db, load_fixture("scan_valid.json"), url_validator=stub_validator)
    db.commit()
    assert calls, "scanner did not route qualification through the service"


def test_scanner_invokes_service_priority_and_enforcement(db, monkeypatch):
    from app.scanner import scan_runner_v2
    from app.services import opportunity_service as svc

    priority_calls, enforce_calls = [], []
    orig_p, orig_e = svc.persist_pursuit_priority, svc.enforce_classification_evidence
    monkeypatch.setattr(svc, "persist_pursuit_priority", lambda *a, **k: (priority_calls.append(1), orig_p(*a, **k))[1])
    monkeypatch.setattr(svc, "enforce_classification_evidence", lambda *a, **k: (enforce_calls.append(1), orig_e(*a, **k))[1])

    scan_runner_v2.process_ai_response(db, load_fixture("scan_valid.json"), url_validator=stub_validator)
    db.commit()

    assert priority_calls, "scanner did not route pursuit priority through the service"
    assert enforce_calls, "scanner did not run final evidence enforcement"


def test_scanner_module_does_not_write_phase2_tables_directly():
    """Static guard on the scanner source: the Phase 2 tables owned by the
    service must never be instantiated in the scanner. The scanner may
    write its own tables (analysis items, classification joins, commercial
    value) but not evidence, scores, qualification or priority."""
    import ast
    import inspect

    from app.scanner import scan_runner_v2

    source = inspect.getsource(scan_runner_v2)
    tree = ast.parse(source)
    instantiated = {
        n.func.id for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
    }
    service_owned = {
        "OpportunityEvidence", "EvidenceClaim", "ScoreAssessment", "ScoreFactor",
        "PursuitPriority", "QualificationAssessment", "QualificationChecklistItem",
        "QualificationBlocker", "OverrideAudit", "AIParseFailure",
    }
    leaked = instantiated & service_owned
    assert not leaked, f"scanner writes service-owned tables directly: {sorted(leaked)}"


# ------------------------------------------- 4. API-shaped serialisation

def test_opportunity_serialises_with_full_phase2_model(db):
    """The shape the API returns and the frontend renders. Asserted here so
    a change that drops a Phase 2 field from the response fails a test
    rather than silently emptying a panel in the UI."""
    from app.scanner.scan_runner_v2 import process_ai_response
    from app.services.opportunity_serializer import serialise_opportunity

    process_ai_response(db, load_fixture("scan_valid.json"), url_validator=stub_validator)
    db.commit()

    opp = db.query(Opportunity).first()
    payload = serialise_opportunity(db, opp)

    for key in (
        "classification", "classification_label", "primary_vertical", "primary_vertical_label",
        "contributing_verticals", "contributing_vertical_count", "routes_to_market",
        "evidence", "evidence_status", "verified_facts", "ai_interpretation", "assumptions",
        "missing_information", "verification_actions", "scores", "pursuit_priority",
        "qualification", "commercial_value", "requires_human_review",
    ):
        assert key in payload, f"API payload missing '{key}'"

    assert payload["contributing_vertical_count"] == 2
    assert len(payload["evidence"]) == 2
    assert payload["evidence"][0]["claims_supported"]

    scores = payload["scores"]
    assert set(scores) == {"strategic_alignment", "commercial_attractiveness", "win_probability", "risk"}
    for dim in scores.values():
        assert "coverage_percent" in dim and "coverage_label" in dim
        assert dim["factors"], "every score must ship its factor breakdown"

    # Risk carries a display label, never a bare number the UI must interpret
    assert scores["risk"]["display_label"] is not None

    # Value is explicitly flagged as an estimate
    assert payload["commercial_value"]["is_estimate"] is True
    assert payload["commercial_value"]["is_published_fact"] is False


def test_risk_not_established_surfaces_in_api_payload(db):
    from app.scanner.scan_runner_v2 import process_ai_response
    from app.services.opportunity_serializer import serialise_opportunity

    process_ai_response(db, load_fixture("scan_thin_risk.json"), url_validator=stub_validator)
    db.commit()

    opp = db.query(Opportunity).first()
    payload = serialise_opportunity(db, opp)

    risk = payload["scores"]["risk"]
    assert risk["display_label"] == "Risk not established"
    assert risk["display_score"] is None       # no reassuring number
    assert payload["pursuit_priority"]["coverage_restricted"] is True


# ------------------------------- 5. the LIVE entry points use Phase 2

def test_live_entry_points_import_phase2_scanner():
    """The gap this catches: `scan_runner_v2` existed and its spy tests
    passed, but every real entry point still imported the legacy
    `scan_runner`. The Phase 2 code was reachable only from tests, so the
    deployed app kept running the old five-factor model while the suite
    reported green.
    """
    import ast
    from pathlib import Path

    backend = Path(__file__).resolve().parent.parent
    for rel in ("app/routers/scans.py", "app/routers/regions.py", "app/scheduler.py"):
        tree = ast.parse((backend / rel).read_text())
        scanner_imports = [
            n.module for n in ast.walk(tree)
            if isinstance(n, ast.ImportFrom) and n.module and "scan_runner" in n.module
        ]
        assert scanner_imports, f"{rel}: no scanner import found"
        for mod in scanner_imports:
            assert mod.endswith("scan_runner_v2"), (
                f"{rel} imports legacy '{mod}' — the live path must use scan_runner_v2"
            )


def test_live_scan_entry_point_runs_full_phase2_pipeline(db):
    """Drives the actual function the router calls, with a fixture instead
    of an AI call, and asserts the full Phase 2 model landed."""
    from app.models import ScanRun, ScanType
    from app.models_phase2 import PursuitPriority, QualificationAssessment, ScoreAssessment
    from app.regions import Vertical
    from app.scanner.scan_runner_v2 import execute_scan

    run = ScanRun(type=ScanType.ON_DEMAND, vertical_scope=Vertical.PATHWAYS)
    db.add(run)
    db.commit()
    run_id = run.id

    # Same call signature the router uses; raw_response injected so no AI call.
    execute_scan(run_id, Vertical.PATHWAYS, "Test scope", raw_response=load_fixture("scan_valid.json"), url_validator=stub_validator)

    fresh = SessionLocal()
    try:
        opp = fresh.query(Opportunity).first()
        assert opp is not None, "live entry point created no opportunity"
        assert opp.classification == "confirmed_opportunity"
        assert opp.primary_vertical == "pathways"
        assert fresh.query(ScoreAssessment).filter_by(opportunity_id=opp.id).count() == 4
        assert fresh.query(PursuitPriority).filter_by(opportunity_id=opp.id).first() is not None
        assert fresh.query(QualificationAssessment).filter_by(opportunity_id=opp.id).first() is not None

        completed = fresh.get(ScanRun, run_id)
        assert completed.status == "complete"
        assert completed.new_items == 1
    finally:
        fresh.close()


def test_regional_scan_entry_point_runs_phase2(db):
    from app.models import ScanRun, ScanType
    from app.regions import Region, Vertical
    from app.scanner.scan_runner_v2 import execute_regional_scan

    run = ScanRun(type=ScanType.ON_DEMAND, region_scope=Region.MENA)
    db.add(run)
    db.commit()
    run_id = run.id

    execute_regional_scan(
        run_id, [Vertical.PATHWAYS], "MENA scope",
        raw_response=load_fixture("scan_valid.json"), url_validator=stub_validator,
    )

    fresh = SessionLocal()
    try:
        opp = fresh.query(Opportunity).first()
        assert opp is not None and opp.primary_vertical == "pathways"
    finally:
        fresh.close()


# ------------------------------ 6. owner qualification workflow (v2.9)

def test_owner_can_answer_checklist_and_state_changes(db):
    """The operational gap this closes: before the workflow existed, an
    opportunity reached 'verification required' and stayed there forever
    because nothing could answer a checklist item."""
    from app.models_phase2 import QualificationAssessment
    from app.scanner.scan_runner_v2 import process_ai_response
    from app.services import opportunity_service as svc
    from app.taxonomy import QUALIFICATION_ITEMS

    process_ai_response(db, load_fixture("scan_valid.json"), url_validator=stub_validator)
    db.commit()
    opp = db.query(Opportunity).first()

    # Force an unresolved mandatory question.
    svc.persist_qualification(
        db, opp.id,
        {i["key"]: {"answer": "unknown"} for i in QUALIFICATION_ITEMS},
        classification=opp.classification, deadline=opp.deadline,
    )
    db.commit()
    assert db.query(QualificationAssessment).filter_by(opportunity_id=opp.id).first().state == "verification_required"

    # Owner answers everything.
    result = svc.answer_qualification_items(
        db, opp.id,
        {i["key"]: {"answer": "yes", "explanation": "Confirmed from the notice."} for i in QUALIFICATION_ITEMS},
    )
    db.commit()

    assert result["state"] == "qualified"
    assessment = db.query(QualificationAssessment).filter_by(opportunity_id=opp.id).first()
    assert assessment.state == "qualified"
    svc.assert_can_enter_active_pipeline(db, opp)  # no longer raises


def test_partial_answers_merge_rather_than_reset(db):
    """Answering three items must not silently reset the other thirteen."""
    from app.models_phase2 import QualificationChecklistItem, QualificationAssessment
    from app.scanner.scan_runner_v2 import process_ai_response
    from app.services import opportunity_service as svc

    process_ai_response(db, load_fixture("scan_valid.json"), url_validator=stub_validator)
    db.commit()
    opp = db.query(Opportunity).first()

    svc.answer_qualification_items(db, opp.id, {"buyer_identifiable": {"answer": "no"}})
    db.commit()

    assessment = db.query(QualificationAssessment).filter_by(opportunity_id=opp.id).first()
    items = {
        i.item_key: i.answer
        for i in db.query(QualificationChecklistItem).filter_by(assessment_id=assessment.id).all()
    }
    assert items["buyer_identifiable"] == "no"
    # The AI's original "yes" answers survive the partial update.
    assert items["live_status_verified"] == "yes"


def test_remediable_blocker_keeps_opportunity_conditionally_qualified(db):
    from app.models_phase2 import QualificationAssessment
    from app.scanner.scan_runner_v2 import process_ai_response
    from app.services import opportunity_service as svc

    process_ai_response(db, load_fixture("scan_valid.json"), url_validator=stub_validator)
    db.commit()
    opp = db.query(Opportunity).first()

    result = svc.answer_qualification_items(db, opp.id, {"local_entity_understood": {"answer": "no"}})
    db.commit()

    assert result["state"] == "conditionally_qualified"
    assert result["remediable_blockers"]
    assert not result["has_absolute_disqualifier"]
    svc.assert_can_enter_active_pipeline(db, opp)  # conditional still progresses


def test_absolute_disqualifier_blocks_pipeline(db):
    from app.scanner.scan_runner_v2 import process_ai_response
    from app.services import opportunity_service as svc

    process_ai_response(db, load_fixture("scan_valid.json"), url_validator=stub_validator)
    db.commit()
    opp = db.query(Opportunity).first()

    result = svc.answer_qualification_items(db, opp.id, {"basic_eligibility_met": {"answer": "no"}})
    db.commit()

    assert result["state"] == "disqualified"
    with pytest.raises(svc.ServiceRuleViolation):
        svc.assert_can_enter_active_pipeline(db, opp)
    # Still searchable — disqualified means excluded from pursuit, not deleted.
    assert db.query(Opportunity).filter_by(id=opp.id).first() is not None


def test_next_actions_explain_what_is_blocking(db):
    """Guards against a dead-end gate: a blocked opportunity must always
    say what would unblock it."""
    from app.scanner.scan_runner_v2 import process_ai_response
    from app.services import opportunity_service as svc
    from app.taxonomy import QUALIFICATION_ITEMS

    process_ai_response(db, load_fixture("scan_valid.json"), url_validator=stub_validator)
    db.commit()
    opp = db.query(Opportunity).first()

    svc.persist_qualification(
        db, opp.id,
        {i["key"]: {"answer": "unknown"} for i in QUALIFICATION_ITEMS},
        classification=opp.classification, deadline=opp.deadline,
    )
    db.commit()

    actions = svc.qualification_next_actions(db, opp.id)
    assert actions, "a blocked opportunity must state what is needed"
    mandatory = [a for a in actions if a["type"] == "answer_mandatory"]
    assert mandatory
    assert all(a["action"] and a["detail"] for a in actions)


def test_qualification_override_preserves_computed_state(db):
    from app.models_phase2 import QualificationOverride, QualificationAssessment
    from app.scanner.scan_runner_v2 import process_ai_response
    from app.services import opportunity_service as svc

    process_ai_response(db, load_fixture("scan_valid.json"), url_validator=stub_validator)
    db.commit()
    opp = db.query(Opportunity).first()

    svc.answer_qualification_items(db, opp.id, {"basic_eligibility_met": {"answer": "no"}})
    db.commit()
    computed = db.query(QualificationAssessment).filter_by(opportunity_id=opp.id).first().state
    assert computed == "disqualified"

    svc.override_qualification_state(
        db, opp.id, new_state="conditionally_qualified",
        reason="Eligibility confirmed by phone with the procurement lead.",
    )
    db.commit()

    override = db.query(QualificationOverride).first()
    assert override.previous_state == "disqualified"   # computed state preserved
    assert override.new_state == "conditionally_qualified"
    assert override.reason
    assert override.overridden_at is not None
    assert db.query(QualificationAssessment).filter_by(opportunity_id=opp.id).first().state == "conditionally_qualified"


def test_override_without_reason_rejected(db):
    from app.scanner.scan_runner_v2 import process_ai_response
    from app.services import opportunity_service as svc

    process_ai_response(db, load_fixture("scan_valid.json"), url_validator=stub_validator)
    db.commit()
    opp = db.query(Opportunity).first()

    with pytest.raises((svc.ServiceRuleViolation, ValueError)):
        svc.override_qualification_state(db, opp.id, new_state="qualified", reason="")


def test_qualifying_removes_the_priority_cap(db):
    """The cap must lift the moment qualification changes — otherwise a
    newly-qualified opportunity keeps displaying a capped score."""
    from app.models_phase2 import PursuitPriority
    from app.scanner.scan_runner_v2 import process_ai_response
    from app.services import opportunity_service as svc
    from app.taxonomy import QUALIFICATION_ITEMS

    process_ai_response(db, load_fixture("scan_valid.json"), url_validator=stub_validator)
    db.commit()
    opp = db.query(Opportunity).first()

    svc.persist_qualification(
        db, opp.id,
        {i["key"]: {"answer": "unknown"} for i in QUALIFICATION_ITEMS},
        classification=opp.classification, deadline=opp.deadline,
    )
    svc._recalculate_priority(db, opp.id, "verification_required")
    db.commit()
    capped = db.query(PursuitPriority).filter_by(opportunity_id=opp.id).first()
    assert capped.qualification_restricted is True

    svc.answer_qualification_items(
        db, opp.id, {i["key"]: {"answer": "yes"} for i in QUALIFICATION_ITEMS}
    )
    db.commit()

    lifted = db.query(PursuitPriority).filter_by(opportunity_id=opp.id).first()
    assert lifted.qualification_restricted is False
    assert lifted.final_score > capped.final_score


def test_invalid_answer_rejected(db):
    from app.scanner.scan_runner_v2 import process_ai_response
    from app.services import opportunity_service as svc

    process_ai_response(db, load_fixture("scan_valid.json"), url_validator=stub_validator)
    db.commit()
    opp = db.query(Opportunity).first()

    with pytest.raises(svc.ServiceRuleViolation):
        svc.answer_qualification_items(db, opp.id, {"live_status_verified": {"answer": "maybe"}})


# ------------- 7. priority recalculation regression (validation item 4)

def test_priority_row_is_replaced_not_stale_after_qualification(db):
    """Explicit regression for the reported failure: after an opportunity
    becomes Qualified the persisted priority must be REPLACED, not left as
    an older restricted row that the API would then serve."""
    from app.models_phase2 import PursuitPriority
    from app.scanner.scan_runner_v2 import process_ai_response
    from app.services import opportunity_service as svc
    from app.services.opportunity_serializer import serialise_opportunity
    from app.taxonomy import QUALIFICATION_ITEMS

    process_ai_response(db, load_fixture("scan_valid.json"), url_validator=stub_validator)
    db.commit()
    opp = db.query(Opportunity).first()

    # Force the restricted state.
    svc.persist_qualification(
        db, opp.id,
        {i["key"]: {"answer": "unknown"} for i in QUALIFICATION_ITEMS},
        classification=opp.classification, deadline=opp.deadline,
    )
    svc._recalculate_priority(db, opp.id, "verification_required")
    db.commit()

    before = db.query(PursuitPriority).filter_by(opportunity_id=opp.id).all()
    assert len(before) == 1, "exactly one active priority row"
    assert before[0].qualification_restricted is True
    restricted_score = before[0].final_score

    # Qualify.
    result = svc.answer_qualification_items(
        db, opp.id, {i["key"]: {"answer": "yes"} for i in QUALIFICATION_ITEMS}
    )
    db.commit()
    assert result["state"] == "qualified"

    after = db.query(PursuitPriority).filter_by(opportunity_id=opp.id).all()
    assert len(after) == 1, "old row must be replaced, not accumulated"
    assert after[0].qualification_restricted is False
    assert after[0].final_score > restricted_score
    assert after[0].final_score == after[0].uncapped_score  # cap fully removed

    # And the API serves the fresh row, not the stale one.
    payload = serialise_opportunity(db, opp)
    assert payload["pursuit_priority"]["qualification_restricted"] is False
    assert payload["pursuit_priority"]["final_score"] == after[0].final_score


def test_null_risk_established_does_not_wrongly_restrict(db):
    """`bool(None)` is False, so a NULL risk flag would silently apply the
    risk restriction. Guards that coercion."""
    from app.models_phase2 import PursuitPriority, ScoreAssessment
    from app.scanner.scan_runner_v2 import process_ai_response
    from app.services import opportunity_service as svc
    from app.taxonomy import QUALIFICATION_ITEMS

    process_ai_response(db, load_fixture("scan_valid.json"), url_validator=stub_validator)
    db.commit()
    opp = db.query(Opportunity).first()

    risk = db.query(ScoreAssessment).filter_by(opportunity_id=opp.id, dimension="risk").first()
    risk.risk_established = None
    db.commit()

    svc.answer_qualification_items(
        db, opp.id, {i["key"]: {"answer": "yes"} for i in QUALIFICATION_ITEMS}
    )
    db.commit()

    priority = db.query(PursuitPriority).filter_by(opportunity_id=opp.id).first()
    assert priority.qualification_restricted is False


def test_confirmed_requires_validated_url_not_ai_assertion(db):
    """The evidence hierarchy must not be bypassable: with URLs left
    unreviewed, a Confirmed claim is still downgraded."""
    from app.scanner.scan_runner_v2 import process_ai_response

    def never_validates(url: str) -> str:
        return "not_reviewed"

    process_ai_response(db, load_fixture("scan_valid.json"), url_validator=never_validates)
    db.commit()

    opp = db.query(Opportunity).first()
    assert opp.classification == "unverified_lead"   # correctly downgraded
    assert opp.requires_human_review is True
    assert "validated or manually reviewed URL" in (opp.human_review_reason or "")


def test_unreachable_url_also_blocks_confirmed(db):
    from app.scanner.scan_runner_v2 import process_ai_response

    process_ai_response(db, load_fixture("scan_valid.json"), url_validator=lambda u: "unreachable")
    db.commit()
    assert db.query(Opportunity).first().classification == "unverified_lead"


def test_every_created_opportunity_has_a_summary(db):
    from app.scanner.scan_runner_v2 import process_ai_response

    process_ai_response(db, load_fixture("scan_valid.json"), url_validator=stub_validator)
    db.commit()
    for opp in db.query(Opportunity).all():
        assert opp.summary and opp.summary.strip(), "summary must never be empty"
