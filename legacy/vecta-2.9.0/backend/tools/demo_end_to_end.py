#!/usr/bin/env python3
"""ATLAS v2.9 end-to-end workflow demonstration.

Drives the real code path with a fixture instead of an AI call and prints
the resulting state at each step, so the evidence is reproducible and
costs nothing to generate.

    cd backend && DATABASE_URL=sqlite:///./demo.db python3 tools/demo_end_to_end.py

Demonstrates:
  A. Confirmed Opportunity  — validated Tier 1 evidence
  B. Unverified Lead        — identical record, URLs unvalidated
  C. Qualification workflow — Verification Required -> Qualified,
                              priority restriction lifted, pipeline opens
  D. Remediable blocker     — Conditionally Qualified

Exit 0 = every assertion held.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

os.environ.setdefault("DATABASE_URL", "sqlite:///./demo_e2e.db")
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("ANTHROPIC_API_KEY", "")

from app.database import Base, SessionLocal, engine  # noqa: E402
from app.models import Opportunity  # noqa: E402
from app.scanner.scan_runner_v2 import process_ai_response  # noqa: E402
from app.services import opportunity_service as svc  # noqa: E402
from app.services.opportunity_serializer import serialise_opportunity  # noqa: E402
from app.taxonomy import QUALIFICATION_ITEMS  # noqa: E402

FIXTURE = BACKEND / "tests" / "fixtures" / "scan_valid.json"
FAILURES: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    status = "PASS" if condition else "FAIL"
    print(f"    [{status}] {label}" + (f" — {detail}" if detail else ""))
    if not condition:
        FAILURES.append(label)


def banner(title: str) -> None:
    print()
    print("-" * 66)
    print(title)
    print("-" * 66)


def reset() -> None:
    import app.models  # noqa: F401  (registers Phase 2 tables)

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def valid_url(url: str) -> str:
    """Deterministic stand-in for the real HTTP validator, so the
    demonstration is offline and reproducible."""
    return "valid"


def unvalidated_url(url: str) -> str:
    return "not_reviewed"


# ------------------------------------------------------------------ A + B

def demo_classification() -> None:
    banner("A. CONFIRMED OPPORTUNITY — validated Tier 1 evidence")
    reset()
    db = SessionLocal()
    try:
        raw = FIXTURE.read_text()
        result = process_ai_response(db, raw, url_validator=valid_url)
        db.commit()

        check("schema validation accepted the record", result["records_validated"] == 1)
        check("no parse failures", result["parse_failures"] == 0)
        check("opportunity created", result["created"] == 1)

        opp = db.query(Opportunity).first()
        payload = serialise_opportunity(db, opp)

        check("classification is Confirmed Opportunity",
              opp.classification == "confirmed_opportunity", opp.classification or "none")
        check("summary present", bool((opp.summary or "").strip()))

        tier1 = [e for e in payload["evidence"] if e["source_tier"] == "tier_1"]
        check("Tier 1 evidence persisted", len(tier1) >= 1)
        check("URL validated by ATLAS", tier1[0]["url_validation_status"] == "valid")
        check("claims linked to evidence", len(tier1[0]["claims_supported"]) >= 3,
              ", ".join(tier1[0]["claims_supported"][:4]))
        check("live_status claim present",
              "live_status" in tier1[0]["claims_supported"])

        check("four score dimensions", len(payload["scores"]) == 4)
        for dim, s in payload["scores"].items():
            check(f"  {dim} has factor breakdown", len(s["factors"]) > 0,
                  f"score={s['display_label']} coverage={s['coverage_percent']}%")

        check("pursuit priority calculated", payload["pursuit_priority"] is not None,
              f"score={payload['pursuit_priority']['final_score']} band={payload['pursuit_priority']['band_label']}")
        check("qualification assessed", payload["qualification"]["state"] != "not_assessed",
              payload["qualification"]["state_label"])
        check("commercial value is an estimate, not a published fact",
              payload["commercial_value"]["is_estimate"] is True
              and payload["commercial_value"]["is_published_fact"] is False)

        print("\n    --- API PAYLOAD (excerpt) ---")
        excerpt = {
            "id": payload["id"],
            "title": payload["title"],
            "classification": payload["classification"],
            "classification_label": payload["classification_label"],
            "primary_vertical_label": payload["primary_vertical_label"],
            "contributing_vertical_count": payload["contributing_vertical_count"],
            "routes_to_market": [r["label"] for r in payload["routes_to_market"]],
            "evidence_status": payload["evidence_status"],
            "scores": {
                k: {"display": v["display_label"], "coverage": f"{v['coverage_percent']}%",
                    "band": v["coverage_band"]}
                for k, v in payload["scores"].items()
            },
            "pursuit_priority": {
                "final_score": payload["pursuit_priority"]["final_score"],
                "band_label": payload["pursuit_priority"]["band_label"],
                "is_restricted": payload["pursuit_priority"]["is_restricted"],
            },
            "qualification_state": payload["qualification"]["state_label"],
            "commercial_value": {
                "status": payload["commercial_value"]["value_status_label"],
                "is_estimate": payload["commercial_value"]["is_estimate"],
                "range": [payload["commercial_value"]["estimated_contract_min"],
                          payload["commercial_value"]["estimated_contract_max"]],
            },
        }
        print(json.dumps(excerpt, indent=6))
    finally:
        db.close()

    banner("B. UNVERIFIED LEAD — identical record, URLs not validated")
    reset()
    db = SessionLocal()
    try:
        process_ai_response(db, FIXTURE.read_text(), url_validator=unvalidated_url)
        db.commit()
        opp = db.query(Opportunity).first()
        check("classification downgraded to Unverified Lead",
              opp.classification == "unverified_lead", opp.classification or "none")
        check("flagged for human review", opp.requires_human_review is True)
        check("reason names the evidence gap",
              "validated or manually reviewed URL" in (opp.human_review_reason or ""),
              (opp.human_review_reason or "")[:90])
        print("\n    Evidence hierarchy held: the same AI record cannot self-certify"
              "\n    its way to Confirmed without ATLAS validating the sources.")
    finally:
        db.close()


# ---------------------------------------------------------------------- C

def demo_qualification_workflow() -> None:
    banner("C. QUALIFICATION WORKFLOW — Verification Required -> Qualified")
    reset()
    db = SessionLocal()
    try:
        process_ai_response(db, FIXTURE.read_text(), url_validator=valid_url)
        db.commit()
        opp = db.query(Opportunity).first()

        # Step 1 — unresolved mandatory questions
        svc.persist_qualification(
            db, opp.id,
            {i["key"]: {"answer": "unknown"} for i in QUALIFICATION_ITEMS},
            classification=opp.classification, deadline=opp.deadline,
        )
        svc._recalculate_priority(db, opp.id, "verification_required")
        db.commit()

        before = serialise_opportunity(db, opp)
        print(f"    Initial state        : {before['qualification']['state_label']}")
        print(f"    Priority             : {before['pursuit_priority']['final_score']} "
              f"({before['pursuit_priority']['band_label']})")
        print(f"    Restricted           : {before['pursuit_priority']['qualification_restricted']}")
        check("starts at Verification Required",
              before["qualification"]["state"] == "verification_required")
        check("priority is qualification-restricted",
              before["pursuit_priority"]["qualification_restricted"] is True)

        actions = svc.qualification_next_actions(db, opp.id)
        check("next actions explain the block", len(actions) > 0,
              f"{len(actions)} action(s), e.g. '{actions[0]['action']}'")
        try:
            svc.assert_can_enter_active_pipeline(db, opp)
            check("pipeline blocked before qualification", False, "it was NOT blocked")
        except svc.ServiceRuleViolation:
            check("pipeline blocked before qualification", True)

        # Step 2 — owner completes the checklist
        print("\n    Owner answers all 16 checklist items...")
        result = svc.answer_qualification_items(
            db, opp.id,
            {i["key"]: {"answer": "yes", "explanation": "Confirmed from the official notice."}
             for i in QUALIFICATION_ITEMS},
        )
        db.commit()

        after = serialise_opportunity(db, opp)
        print(f"    New state            : {after['qualification']['state_label']}")
        print(f"    Priority             : {after['pursuit_priority']['final_score']} "
              f"({after['pursuit_priority']['band_label']})")
        print(f"    Restricted           : {after['pursuit_priority']['qualification_restricted']}")

        check("state becomes Qualified", result["state"] == "qualified", result["state"])
        check("restriction lifted",
              after["pursuit_priority"]["qualification_restricted"] is False)
        check("priority increased",
              after["pursuit_priority"]["final_score"] > before["pursuit_priority"]["final_score"],
              f"{before['pursuit_priority']['final_score']} -> {after['pursuit_priority']['final_score']}")
        check("cap fully removed",
              after["pursuit_priority"]["final_score"] == after["pursuit_priority"]["uncapped_score"])
        try:
            svc.assert_can_enter_active_pipeline(db, opp)
            check("pipeline entry now permitted", True)
        except svc.ServiceRuleViolation as exc:
            check("pipeline entry now permitted", False, "; ".join(exc.failures))
    finally:
        db.close()


# ---------------------------------------------------------------------- D

def demo_remediable_blocker() -> None:
    banner("D. REMEDIABLE BLOCKER — Conditionally Qualified")
    reset()
    db = SessionLocal()
    try:
        process_ai_response(db, FIXTURE.read_text(), url_validator=valid_url)
        db.commit()
        opp = db.query(Opportunity).first()

        answers = {i["key"]: {"answer": "yes"} for i in QUALIFICATION_ITEMS}
        answers["local_entity_understood"] = {
            "answer": "no",
            "explanation": "Local entity required but not yet registered.",
        }
        result = svc.answer_qualification_items(db, opp.id, answers)
        db.commit()

        payload = serialise_opportunity(db, opp)
        print(f"    State                : {payload['qualification']['state_label']}")
        for b in payload["qualification"]["blockers"]:
            print(f"    Blocker              : [{b['failure_type_label']}] {b['message']}")

        check("state is Conditionally Qualified",
              result["state"] == "conditionally_qualified", result["state"])
        check("blocker typed as remediable, not absolute",
              result["has_absolute_disqualifier"] is False and bool(result["remediable_blockers"]))
        try:
            svc.assert_can_enter_active_pipeline(db, opp)
            check("conditionally qualified may still progress", True)
        except svc.ServiceRuleViolation as exc:
            check("conditionally qualified may still progress", False, "; ".join(exc.failures))

        print("\n    A recoverable obstacle does not permanently disqualify — the"
              "\n    required action is recorded and pursuit can continue.")
    finally:
        db.close()


def main() -> int:
    print("=" * 66)
    print("ATLAS v2.9 — END-TO-END WORKFLOW DEMONSTRATION")
    print("Fixture-driven: no AI call, no network, no cost.")
    print("=" * 66)

    demo_classification()
    demo_qualification_workflow()
    demo_remediable_blocker()

    print()
    print("=" * 66)
    if FAILURES:
        print(f"RESULT: {len(FAILURES)} CHECK(S) FAILED")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("RESULT: ALL CHECKS PASSED")
    print("=" * 66)
    return 0


if __name__ == "__main__":
    sys.exit(main())
