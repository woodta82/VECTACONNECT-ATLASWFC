"""Qualification gate (rebuild spec §10–§11).

Turns the 16-item qualification checklist into one of five states, and
enforces the mandatory rules that keep unqualified work out of the active
pipeline. The rules are deliberately conservative: a high score never
qualifies an opportunity, and a Confirmed classification never qualifies
it either — only the checklist does.
"""
from __future__ import annotations

from .timeutils import utcnow

from .taxonomy import (
    ABSOLUTE_DISQUALIFIER_KEYS,
    MANDATORY_QUALIFICATION_KEYS,
    NON_PIPELINE_CLASSIFICATIONS,
    QUALIFICATION_ITEMS,
    REMEDIABLE_BLOCKER_KEYS,
    FailureType,
    GateAnswer,
    QualificationState,
)

QUALIFICATION_MODEL_VERSION = "2.0"


def empty_qualification() -> dict:
    """A blank checklist — every item Unknown, state Not assessed."""
    return {
        "state": QualificationState.NOT_ASSESSED.value,
        "items": {
            item["key"]: {
                "answer": GateAnswer.UNKNOWN.value,
                "explanation": None,
                "evidence_id": None,
                "last_reviewed": None,
            }
            for item in QUALIFICATION_ITEMS
        },
        "model_version": QUALIFICATION_MODEL_VERSION,
        "evaluated_at": None,
        "reasons": [],
        "override": None,
    }


def evaluate_qualification(
    items: dict[str, dict],
    classification: str | None = None,
    deadline_passed: bool = False,
    deadline_extension_valid: bool = False,
    has_credible_source: bool = True,
    prohibited_from_participating: bool = False,
) -> dict:
    """Evaluates the checklist into a qualification state with TYPED
    failures (§3).

    Failures are classified as absolute, remediable, unresolved-mandatory
    or non-material, because collapsing them into one "Disqualified"
    bucket would permanently bury opportunities that only need a partner
    appointed or an entity registered.

    Precedence:
      1. Absolute disqualifiers  -> Disqualified (permanent)
      2. Non-opportunity classification -> Verification Required
      3. Unresolved mandatory questions -> Verification Required
      4. Remediable blockers / non-material concerns -> Conditionally Qualified
      5. Otherwise -> Qualified
    """
    findings: list[dict] = []
    answered = {k: (v or {}).get("answer", GateAnswer.UNKNOWN.value) for k, v in (items or {}).items()}
    label_for = {i["key"]: i["label"] for i in QUALIFICATION_ITEMS}

    def add(ftype: FailureType, message: str, key: str | None = None) -> None:
        findings.append({"type": ftype.value, "message": message, "item_key": key})

    # --- 1. absolute disqualifiers --------------------------------------
    if deadline_passed and not deadline_extension_valid:
        add(FailureType.ABSOLUTE_DISQUALIFIER, "Deadline has passed with no valid extension.")
    if not has_credible_source:
        add(FailureType.ABSOLUTE_DISQUALIFIER, "No credible source.")
    if prohibited_from_participating:
        add(FailureType.ABSOLUTE_DISQUALIFIER, "VECTA is prohibited from participating.")

    for key in ABSOLUTE_DISQUALIFIER_KEYS:
        if answered.get(key) == GateAnswer.NO.value:
            add(FailureType.ABSOLUTE_DISQUALIFIER, f"Absolute bar: {label_for.get(key, key)} answered No.", key)

    if any(f["type"] == FailureType.ABSOLUTE_DISQUALIFIER.value for f in findings):
        return _result(QualificationState.DISQUALIFIED, findings)

    # --- remediable blockers (recorded, not fatal) ----------------------
    for key in REMEDIABLE_BLOCKER_KEYS:
        if answered.get(key) == GateAnswer.NO.value:
            add(
                FailureType.REMEDIABLE_BLOCKER,
                f"Remediable blocker: {label_for.get(key, key)} not yet satisfied — resolvable by VECTA.",
                key,
            )

    # --- 2. classification block ----------------------------------------
    if classification in NON_PIPELINE_CLASSIFICATIONS:
        add(
            FailureType.UNRESOLVED_MANDATORY,
            f"Classification '{classification}' is not an actionable opportunity — "
            "cannot be qualified until reclassified.",
        )
        return _result(QualificationState.VERIFICATION_REQUIRED, findings)

    # --- 3. unresolved mandatory questions ------------------------------
    unresolved = [
        k for k in MANDATORY_QUALIFICATION_KEYS
        if answered.get(k, GateAnswer.UNKNOWN.value) == GateAnswer.UNKNOWN.value
    ]
    for k in unresolved:
        add(FailureType.UNRESOLVED_MANDATORY, f"Mandatory check unresolved: {label_for.get(k, k)}.", k)
    if unresolved:
        return _result(QualificationState.VERIFICATION_REQUIRED, findings)

    # --- 4. non-material concerns ---------------------------------------
    for i in QUALIFICATION_ITEMS:
        if not i["mandatory"] and answered.get(i["key"], GateAnswer.UNKNOWN.value) == GateAnswer.UNKNOWN.value:
            add(FailureType.NON_MATERIAL_CONCERN, f"Open question: {i['label']}.", i["key"])

    if findings:
        return _result(QualificationState.CONDITIONALLY_QUALIFIED, findings)

    # --- 5. qualified ----------------------------------------------------
    return _result(QualificationState.QUALIFIED, [])


def _result(state: QualificationState, findings: list[dict]) -> dict:
    by_type: dict[str, list[str]] = {}
    for f in findings:
        by_type.setdefault(f["type"], []).append(f["message"])
    return {
        "state": state.value,
        "findings": findings,
        "findings_by_type": by_type,
        # Plain-language reasons, always populated — no state is ever unexplained.
        "reasons": [f["message"] for f in findings]
        or ["All mandatory checks passed and no open questions remain."],
        "has_absolute_disqualifier": any(
            f["type"] == FailureType.ABSOLUTE_DISQUALIFIER.value for f in findings
        ),
        "remediable_blockers": [
            f["message"] for f in findings if f["type"] == FailureType.REMEDIABLE_BLOCKER.value
        ],
        "evaluated_at": utcnow().isoformat(),
        "model_version": QUALIFICATION_MODEL_VERSION,
    }


def apply_manual_override(
    current_state: str, new_state: str, reason: str, note: str | None = None
) -> dict:
    """Explicit owner override (§11). Records what changed and why; the
    computed state is preserved as `previous_state` so the override is
    always auditable. No user identity is recorded — ATLAS is single
    login."""
    if not reason or not reason.strip():
        raise ValueError("An override requires a reason.")
    valid = {s.value for s in QualificationState}
    if new_state not in valid:
        raise ValueError(f"Invalid qualification state: {new_state}")
    return {
        "previous_state": current_state,
        "new_state": new_state,
        "reason": reason.strip(),
        "note": (note or "").strip() or None,
        "overridden_at": utcnow().isoformat(),
    }


# Pipeline-entry rule hierarchy (documented, and enforced in this order).
# The gate reports EVERY blocking reason, not just the first: a user who
# fixes one blocker only to be told about the next is being drip-fed, and
# tests that assert on "the reason" become order-dependent and brittle.
# The list is ordered by how fundamental the objection is.
PIPELINE_RULE_ORDER = [
    "classification",   # 1. not an actionable opportunity at all
    "disqualified",     # 2. failed an absolute qualification bar
    "deadline",         # 3. cannot be delivered in time
    "not_qualified",    # 4. not yet assessed / verification outstanding
]


def can_enter_active_pipeline(
    qualification_state: str,
    classification: str | None,
    deadline_passed: bool = False,
) -> tuple[bool, list[str]]:
    """Gate for pipeline entry (spec §10/§11).

    Returns (allowed, reasons). `reasons` lists EVERY objection, ordered by
    PIPELINE_RULE_ORDER, so the caller can show the complete set of things
    to resolve rather than revealing them one at a time.
    """
    reasons: list[str] = []

    if classification in NON_PIPELINE_CLASSIFICATIONS:
        reasons.append(
            f"Classification '{classification}' is not an actionable opportunity — "
            "reclassify before pursuing."
        )

    if qualification_state == QualificationState.DISQUALIFIED.value:
        reasons.append(
            "Opportunity is disqualified — searchable and auditable, but not an active pursuit."
        )

    if deadline_passed:
        reasons.append("Deadline passed — cannot enter the active pipeline.")

    if qualification_state in (
        QualificationState.NOT_ASSESSED.value,
        QualificationState.VERIFICATION_REQUIRED.value,
    ):
        reasons.append(
            f"Qualification state '{qualification_state}' — must be qualified or "
            "conditionally qualified before pipeline entry."
        )

    return (not reasons), reasons
