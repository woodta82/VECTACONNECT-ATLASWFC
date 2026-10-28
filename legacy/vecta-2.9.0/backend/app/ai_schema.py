"""Strict, versioned AI output contract (rebuild spec §4).

Replaces the previous approach of slicing whatever sat between the first
`[` and last `]` and hoping it parsed. That method could not distinguish
"the model returned nothing useful" from "the model returned six good
records and one malformed one", and it silently produced half-populated
opportunities from partial JSON.

Every field the Phase 2 model needs is declared here with its type and
constraints. Validation is all-or-nothing per record: a record either
satisfies the schema completely and becomes an opportunity, or it becomes
an `AIParseFailure` with the raw response and the exact validation errors
preserved for retry or manual review. There is no partial path.
"""
from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from .scoring_v2 import (
    COMMERCIAL_FACTORS,
    RISK_FACTORS,
    STRATEGIC_FACTORS,
    WIN_PROBABILITY_FACTORS,
)
from .taxonomy import (
    QUALIFICATION_ITEMS,
    CommercialType,
    ConfidenceLevel,
    GateAnswer,
    OpportunityClassification,
    QualificationState,
    RouteToMarket,
    SourceTier,
    ValueStatus,
    VerticalV2,
)

AI_SCHEMA_VERSION = "2.0"

# Valid keys pulled from the engines themselves rather than duplicated —
# if a factor is renamed in scoring_v2.py, the schema follows automatically
# and a stale AI response fails validation instead of silently dropping.
_STRATEGIC_KEYS = {f["key"] for f in STRATEGIC_FACTORS}
_COMMERCIAL_KEYS = {f["key"] for f in COMMERCIAL_FACTORS}
_WIN_KEYS = {f["key"] for f in WIN_PROBABILITY_FACTORS}
_RISK_KEYS = {f["key"] for f in RISK_FACTORS}
_QUALIFICATION_KEYS = {i["key"] for i in QUALIFICATION_ITEMS}

_CLAIM_TYPES = {
    "opportunity_existence",
    "live_status",
    "issuing_organisation",
    "deadline",
    "published_value",
    "eligibility",
    "geographic_scope",
    "procurement_route",
    "programme_description",
}


class _Strict(BaseModel):
    """Base config: unknown fields are an error, not a shrug. A response
    carrying fields we don't recognise means the model drifted from the
    contract, and that should surface loudly rather than be discarded."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


# ------------------------------------------------------------- evidence

class AIEvidenceRecord(_Strict):
    url: str = Field(min_length=8)
    page_title: str | None = None
    publisher: str | None = None
    source_tier: Literal["tier_1", "tier_2", "tier_3", "tier_4"]
    evidence_type: str = "other"
    publication_date: str | None = Field(
        default=None, description="ISO date (YYYY-MM-DD) or null if genuinely unavailable"
    )
    no_publication_date_reason: str | None = None
    is_official_source: bool = False
    is_definitive: bool = False
    claims_supported: list[str] = Field(min_length=1)
    confidence: Literal["high", "medium", "low"] = "medium"
    notes: str | None = None

    @field_validator("claims_supported")
    @classmethod
    def _known_claims(cls, v: list[str]) -> list[str]:
        bad = [c for c in v if c not in _CLAIM_TYPES]
        if bad:
            raise ValueError(f"Unknown claim types {bad}; valid: {sorted(_CLAIM_TYPES)}")
        return v

    @field_validator("url")
    @classmethod
    def _http_url(cls, v: str) -> str:
        if not v.startswith(("http://", "https://")):
            raise ValueError("Evidence URL must be an absolute http(s) URL")
        return v


# ------------------------------------------------------------- analysis

class AIVerifiedFact(_Strict):
    """A fact CANDIDATE. The AI proposes; the service layer decides whether
    it is actually verified, by checking that the referenced evidence
    genuinely supports this claim type (§5)."""

    content: str = Field(min_length=3)
    claim_type: str
    evidence_url: str = Field(description="Must match one of the evidence records' URLs")

    @field_validator("claim_type")
    @classmethod
    def _known_claim(cls, v: str) -> str:
        if v not in _CLAIM_TYPES:
            raise ValueError(f"Unknown claim type '{v}'")
        return v


class AIAssumption(_Strict):
    content: str = Field(min_length=3)
    basis: str | None = None


class AIMissingInformation(_Strict):
    content: str = Field(min_length=3)
    blocks_qualification: bool = False


class AIVerificationAction(_Strict):
    action: str = Field(min_length=3)
    reason: str | None = None


# --------------------------------------------------------------- values

class AICommercialValue(_Strict):
    value_status: Literal[
        "published_contract_value",
        "published_wider_programme_value",
        "estimated_range",
        "value_not_disclosed",
        "insufficient_evidence",
    ]
    currency: str = "USD"
    published_programme_value: float | None = None
    published_contract_value: float | None = None
    estimated_contract_min: float | None = None
    estimated_contract_max: float | None = None
    estimated_vecta_revenue: float | None = None
    estimate_methodology: str | None = None
    partner_share_assumption: float | None = None
    confidence: Literal["high", "medium", "low"] | None = None

    @field_validator("estimated_contract_max")
    @classmethod
    def _max_ge_min(cls, v: float | None, info) -> float | None:
        lo = info.data.get("estimated_contract_min")
        if v is not None and lo is not None and v < lo:
            raise ValueError("estimated_contract_max cannot be below estimated_contract_min")
        return v

    def model_post_init(self, __context: Any) -> None:
        # An estimated range must actually carry a range and a stated basis
        # — otherwise it is a guess wearing the costume of an estimate.
        if self.value_status == ValueStatus.ESTIMATED_RANGE.value:
            if self.estimated_contract_min is None or self.estimated_contract_max is None:
                raise ValueError("estimated_range requires both a minimum and a maximum")
            if not self.estimate_methodology:
                raise ValueError("estimated_range requires estimate_methodology")
        # A published status must carry the corresponding published figure.
        if self.value_status == ValueStatus.PUBLISHED_CONTRACT.value and self.published_contract_value is None:
            raise ValueError("published_contract_value status requires published_contract_value")
        if self.value_status == ValueStatus.PUBLISHED_PROGRAMME.value and self.published_programme_value is None:
            raise ValueError("published_wider_programme_value status requires published_programme_value")


# -------------------------------------------------------------- scoring

class AIFactorScore(_Strict):
    factor_key: str
    score: int = Field(ge=0, le=100)
    rationale: str = Field(min_length=3, description="Why this score — never optional")
    evidence_url: str | None = None


class AIScoreDimension(_Strict):
    factors: list[AIFactorScore] = Field(min_length=1)
    confidence: Literal["high", "medium", "low"] = "medium"
    rationale: str | None = None


class AIScores(_Strict):
    strategic_alignment: AIScoreDimension
    commercial_attractiveness: AIScoreDimension
    win_probability: AIScoreDimension
    risk: AIScoreDimension

    def model_post_init(self, __context: Any) -> None:
        for name, valid in (
            ("strategic_alignment", _STRATEGIC_KEYS),
            ("commercial_attractiveness", _COMMERCIAL_KEYS),
            ("win_probability", _WIN_KEYS),
            ("risk", _RISK_KEYS),
        ):
            dim: AIScoreDimension = getattr(self, name)
            bad = [f.factor_key for f in dim.factors if f.factor_key not in valid]
            if bad:
                raise ValueError(f"{name}: unknown factor keys {bad}")
            seen = [f.factor_key for f in dim.factors]
            if len(seen) != len(set(seen)):
                raise ValueError(f"{name}: duplicate factor keys")


# -------------------------------------------------------- qualification

class AIQualificationAnswer(_Strict):
    item_key: str
    answer: Literal["yes", "no", "unknown", "not_applicable"]
    explanation: str | None = None
    evidence_url: str | None = None

    @field_validator("item_key")
    @classmethod
    def _known_item(cls, v: str) -> str:
        if v not in _QUALIFICATION_KEYS:
            raise ValueError(f"Unknown qualification item '{v}'")
        return v


class AIQualification(_Strict):
    checklist: list[AIQualificationAnswer] = Field(min_length=1)
    recommended_state: Literal[
        "not_assessed", "verification_required", "qualified",
        "conditionally_qualified", "disqualified",
    ]
    rationale: str | None = None

    @field_validator("checklist")
    @classmethod
    def _no_duplicates(cls, v: list[AIQualificationAnswer]) -> list[AIQualificationAnswer]:
        keys = [a.item_key for a in v]
        if len(keys) != len(set(keys)):
            raise ValueError("Duplicate qualification checklist items")
        return v


# ----------------------------------------------------- the full record

class AIOpportunityRecord(_Strict):
    """One complete opportunity as returned by the AI. Every field the
    Phase 2 model persists is represented; nothing is inferred later from
    free text."""

    schema_version: Literal["2.0"] = AI_SCHEMA_VERSION

    title: str = Field(min_length=5)
    issuing_organisation: str | None = None
    # Required: a record with no summary is unusable in a list view, and
    # asking the model for one costs nothing.
    summary: str = Field(min_length=10)

    classification: Literal[
        "confirmed_opportunity", "early_stage_opportunity", "relationship_led_opportunity",
        "market_signal", "intelligence_watch", "unverified_lead",
    ]
    classification_rationale: str = Field(min_length=3)

    primary_vertical: Literal[
        "pathways", "connect", "media", "experiences", "talent", "intelligence"
    ]
    contributing_verticals: list[str] = Field(default_factory=list)
    vertical_rationale: str = Field(min_length=3)

    primary_commercial_type: str
    secondary_commercial_types: list[str] = Field(default_factory=list)
    routes_to_market: list[str] = Field(min_length=1)

    region: str | None = None
    market: str | None = None
    publication_date: str | None = None
    deadline: str | None = None

    evidence: list[AIEvidenceRecord] = Field(min_length=1)
    verified_fact_candidates: list[AIVerifiedFact] = Field(default_factory=list)
    ai_interpretation: list[str] = Field(default_factory=list)
    assumptions: list[AIAssumption] = Field(default_factory=list)
    missing_information: list[AIMissingInformation] = Field(default_factory=list)
    verification_actions: list[AIVerificationAction] = Field(default_factory=list)

    commercial_value: AICommercialValue
    scores: AIScores
    qualification: AIQualification
    commercial_confidence: Literal["high", "medium", "low"] = "medium"

    @field_validator("contributing_verticals")
    @classmethod
    def _known_verticals(cls, v: list[str]) -> list[str]:
        valid = {x.value for x in VerticalV2}
        bad = [x for x in v if x not in valid]
        if bad:
            raise ValueError(f"Unknown verticals {bad}")
        return v

    @field_validator("primary_commercial_type", "secondary_commercial_types")
    @classmethod
    def _known_types(cls, v):
        valid = {x.value for x in CommercialType}
        items = [v] if isinstance(v, str) else v
        bad = [x for x in items if x not in valid]
        if bad:
            raise ValueError(f"Unknown commercial types {bad}")
        return v

    @field_validator("routes_to_market")
    @classmethod
    def _known_routes(cls, v: list[str]) -> list[str]:
        valid = {x.value for x in RouteToMarket}
        bad = [x for x in v if x not in valid]
        if bad:
            raise ValueError(f"Unknown routes to market {bad}")
        return v

    def model_post_init(self, __context: Any) -> None:
        # The primary vertical must not also be listed as contributing.
        if self.primary_vertical in self.contributing_verticals:
            raise ValueError("primary_vertical must not also appear in contributing_verticals")
        # Every fact candidate must point at an evidence record that
        # actually exists in this payload — a dangling reference means the
        # AI invented a source, which is exactly what §5 guards against.
        urls = {e.url for e in self.evidence}
        dangling = [f.evidence_url for f in self.verified_fact_candidates if f.evidence_url not in urls]
        if dangling:
            raise ValueError(f"verified_fact_candidates reference unknown evidence URLs: {dangling}")


class AIScanResponse(_Strict):
    """The top-level payload: a list of records, plus the searches the
    model actually performed (kept for auditability of how a finding was
    reached)."""

    schema_version: Literal["2.0"] = AI_SCHEMA_VERSION
    records: list[AIOpportunityRecord] = Field(default_factory=list)
    raw_source_references: list[str] = Field(default_factory=list)


# ------------------------------------------------------------ validation

class ValidationOutcome:
    """Result of validating one raw AI response.

    Deliberately not an exception: a failure is a *record* to be stored
    and retried, not an error to unwind the scan. One malformed record
    must not discard the good ones alongside it.
    """

    def __init__(
        self,
        ok: bool,
        records: list[AIOpportunityRecord] | None = None,
        errors: list[dict] | None = None,
        raw: str = "",
    ) -> None:
        self.ok = ok
        self.records = records or []
        self.errors = errors or []
        self.raw = raw

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"<ValidationOutcome ok={self.ok} records={len(self.records)} errors={len(self.errors)}>"


def _format_errors(exc: ValidationError, index: int | None = None) -> list[dict]:
    out = []
    for e in exc.errors():
        out.append(
            {
                "record_index": index,
                "field": ".".join(str(p) for p in e.get("loc", ())),
                "message": e.get("msg"),
                "type": e.get("type"),
            }
        )
    return out


def validate_ai_response(raw: str) -> ValidationOutcome:
    """Validates a raw AI response against the strict schema.

    Records are validated individually so a single bad record is isolated
    rather than poisoning the whole batch — the outcome carries the valid
    records AND the errors for the invalid ones, and the caller persists
    both.
    """
    if not raw or not raw.strip():
        return ValidationOutcome(False, errors=[{"field": "", "message": "Empty AI response", "type": "empty"}], raw=raw or "")

    # Strict JSON parse — no bracket slicing. If the model wrapped the JSON
    # in a fenced code block we strip only that well-defined wrapper.
    text = raw.strip()
    if text.startswith("```"):
        first_newline = text.find("\n")
        closing = text.rfind("```")
        if first_newline != -1 and closing > first_newline:
            text = text[first_newline + 1 : closing].strip()

    try:
        payload = json.loads(text)
    except json.JSONDecodeError as e:
        return ValidationOutcome(
            False,
            errors=[{"field": "", "message": f"Response is not valid JSON: {e}", "type": "json_decode"}],
            raw=raw,
        )

    if isinstance(payload, list):
        payload = {"schema_version": AI_SCHEMA_VERSION, "records": payload}
    if not isinstance(payload, dict):
        return ValidationOutcome(
            False,
            errors=[{"field": "", "message": "Top level must be an object or array", "type": "structure"}],
            raw=raw,
        )

    raw_records = payload.get("records", [])
    if not isinstance(raw_records, list):
        return ValidationOutcome(
            False, errors=[{"field": "records", "message": "'records' must be an array", "type": "structure"}], raw=raw
        )

    valid: list[AIOpportunityRecord] = []
    errors: list[dict] = []
    for i, item in enumerate(raw_records):
        try:
            valid.append(AIOpportunityRecord.model_validate(item))
        except ValidationError as e:
            errors.append(
                {
                    "record_index": i,
                    "proposed_title": (item or {}).get("title") if isinstance(item, dict) else None,
                    "errors": _format_errors(e, i),
                }
            )

    return ValidationOutcome(ok=not errors, records=valid, errors=errors, raw=raw)


def json_schema() -> dict:
    """Machine-readable schema — used to build the AI prompt and to
    publish the contract in the API docs, so prompt and validator can
    never describe different shapes."""
    return AIScanResponse.model_json_schema()
