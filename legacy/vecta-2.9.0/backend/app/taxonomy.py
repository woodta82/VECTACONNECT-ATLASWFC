"""Phase 2 intelligence taxonomies (rebuild spec §3–§7).

Single source of truth for every classification ATLAS applies to an
opportunity. Definitions live beside the enums deliberately: the same
text is used in the AI prompt, the API schema descriptions and the
frontend labels, so the three can never drift apart.
"""
import enum


# --------------------------------------------------------------- verticals (§3)

class VerticalV2(str, enum.Enum):
    """Six VECTA verticals. `intelligence` is new in v2.9; the five legacy
    values keep their exact string identities so existing rows migrate
    without a data rewrite."""

    PATHWAYS = "pathways"
    CONNECT = "connect"
    MEDIA = "media"
    EXPERIENCES = "experiences"
    TALENT = "talent"
    INTELLIGENCE = "intelligence"


VERTICAL_V2_INFO: dict[str, dict[str, str]] = {
    "pathways": {
        "label": "VECTA Pathways",
        "definition": (
            "Sports infrastructure, coach education, player-development pathways, academies, "
            "government and federation programmes, schools, talent centres and long-term "
            "sporting asset creation."
        ),
    },
    "connect": {
        "label": "VECTA Connect",
        "definition": (
            "Market access, partnerships, sponsorship, commercial introductions, government "
            "and federation relationships, strategic account development and cross-border deal flow."
        ),
    },
    "media": {
        "label": "VECTA Media",
        "definition": (
            "Sports content, storytelling, digital production, rights support, commercial media, "
            "audience development, visibility and distribution."
        ),
    },
    "experiences": {
        "label": "VECTA Experiences",
        "definition": (
            "Events, talent showcases, international exposure, premium sports experiences, "
            "activations, hospitality and commercially driven sporting environments."
        ),
    },
    "talent": {
        "label": "VECTA Talent",
        "definition": (
            "Representation, talent identification, recruitment, trials, ambassadors, scouting "
            "and professional player pathways."
        ),
    },
    "intelligence": {
        "label": "VECTA Intelligence",
        "definition": (
            "Scouting intelligence, performance data, commercial intelligence, sports technology, "
            "research and decision-support products."
        ),
    },
}


# ------------------------------------------------- opportunity classification (§4)

class OpportunityClassification(str, enum.Enum):
    CONFIRMED = "confirmed_opportunity"
    EARLY_STAGE = "early_stage_opportunity"
    RELATIONSHIP_LED = "relationship_led_opportunity"
    MARKET_SIGNAL = "market_signal"
    INTELLIGENCE_WATCH = "intelligence_watch"
    UNVERIFIED_LEAD = "unverified_lead"


CLASSIFICATION_INFO: dict[str, dict[str, str]] = {
    "confirmed_opportunity": {
        "label": "Confirmed opportunity",
        "definition": (
            "A live, credible opportunity supported by Tier 1 evidence, or by Tier 2 evidence "
            "definitive enough to stand alone."
        ),
        "rule": "Requires at least one Tier 1 evidence record, or a Tier 2 record marked definitive.",
    },
    "early_stage_opportunity": {
        "label": "Early-stage opportunity",
        "definition": (
            "A credible future commercial opening with supporting evidence, but not yet open "
            "for formal pursuit."
        ),
        "rule": "Requires evidence, but the opportunity is not yet open — no live procurement or mandate.",
    },
    "relationship_led_opportunity": {
        "label": "Relationship-led opportunity",
        "definition": (
            "An opportunity whose principal route to market is a direct relationship, "
            "introduction or strategic engagement rather than an open procurement process."
        ),
        "rule": "Route to market is predominantly direct_relationship, partner_led or invitation_only.",
    },
    "market_signal": {
        "label": "Market signal",
        "definition": (
            "Evidence of investment, policy, expansion or strategic intent that may produce "
            "future opportunities but is not itself an opportunity."
        ),
        "rule": "Never eligible for the active pipeline; carries no deadline and no buyer.",
    },
    "intelligence_watch": {
        "label": "Intelligence watch",
        "definition": "A relevant development that should be monitored but is not ready for qualification.",
        "rule": "Never eligible for the active pipeline until reclassified.",
    },
    "unverified_lead": {
        "label": "Unverified lead",
        "definition": (
            "A potentially relevant result where key facts, source or current status have not "
            "yet been verified."
        ),
        "rule": "Default classification when evidence is insufficient to say more.",
    },
}

# Classifications that can never enter the active commercial pipeline (§10/§11).
NON_PIPELINE_CLASSIFICATIONS = {
    OpportunityClassification.MARKET_SIGNAL.value,
    OpportunityClassification.INTELLIGENCE_WATCH.value,
    OpportunityClassification.UNVERIFIED_LEAD.value,
}


# ------------------------------------------------------- commercial type (§5)

class CommercialType(str, enum.Enum):
    PUBLIC_TENDER = "public_tender"
    PRIVATE_RFP = "private_rfp"
    DIRECT_AWARD = "direct_award_possibility"
    STRATEGIC_PARTNERSHIP = "strategic_partnership"
    SPONSORSHIP = "sponsorship"
    REPRESENTATION_MANDATE = "representation_mandate"
    EVENT_DELIVERY = "event_delivery"
    COACH_EDUCATION = "coach_education"
    ACADEMY_DEVELOPMENT = "academy_development"
    PLAYER_DEVELOPMENT = "player_development_programme"
    TALENT_IDENTIFICATION = "talent_identification"
    GOVERNMENT_ADVISORY = "government_advisory"
    FEDERATION_ADVISORY = "federation_advisory"
    MEDIA_PRODUCTION = "media_production"
    CONTENT_DISTRIBUTION = "content_distribution"
    TECHNOLOGY_PARTNERSHIP = "technology_partnership"
    INVESTMENT = "investment_opportunity"
    MARKET_ENTRY = "market_entry_opportunity"
    HOSPITALITY = "hospitality_opportunity"
    OTHER = "other"


COMMERCIAL_TYPE_LABELS: dict[str, str] = {
    "public_tender": "Public tender",
    "private_rfp": "Private RFP",
    "direct_award_possibility": "Direct-award possibility",
    "strategic_partnership": "Strategic partnership",
    "sponsorship": "Sponsorship",
    "representation_mandate": "Representation mandate",
    "event_delivery": "Event delivery",
    "coach_education": "Coach education",
    "academy_development": "Academy development",
    "player_development_programme": "Player-development programme",
    "talent_identification": "Talent identification",
    "government_advisory": "Government advisory",
    "federation_advisory": "Federation advisory",
    "media_production": "Media production",
    "content_distribution": "Content distribution",
    "technology_partnership": "Technology partnership",
    "investment_opportunity": "Investment opportunity",
    "market_entry_opportunity": "Market-entry opportunity",
    "hospitality_opportunity": "Hospitality opportunity",
    "other": "Other",
}


# ------------------------------------------------------- route to market (§6)

class RouteToMarket(str, enum.Enum):
    """Stored as a LIST per opportunity — these requirements coexist. An
    opportunity can simultaneously be open competition, local-entity
    required and consortium required; forcing a single choice would lose
    real information."""

    OPEN_COMPETITION = "open_competition"
    PREQUALIFICATION = "prequalification_required"
    INVITATION_ONLY = "invitation_only"
    DIRECT_RELATIONSHIP = "direct_relationship"
    PARTNER_LED = "partner_led"
    CONSORTIUM_REQUIRED = "consortium_required"
    LOCAL_ENTITY_REQUIRED = "local_entity_required"
    ACCREDITATION_REQUIRED = "accreditation_required"
    UNKNOWN = "unknown"


ROUTE_TO_MARKET_LABELS: dict[str, str] = {
    "open_competition": "Open competition",
    "prequalification_required": "Prequalification required",
    "invitation_only": "Invitation only",
    "direct_relationship": "Direct relationship",
    "partner_led": "Partner-led",
    "consortium_required": "Consortium required",
    "local_entity_required": "Local entity required",
    "accreditation_required": "Accreditation required",
    "unknown": "Unknown",
}


# ---------------------------------------------------------- source tiers (§7)

class SourceTier(str, enum.Enum):
    TIER_1 = "tier_1"
    TIER_2 = "tier_2"
    TIER_3 = "tier_3"
    TIER_4 = "tier_4"


SOURCE_TIER_INFO: dict[str, dict[str, str]] = {
    "tier_1": {
        "label": "Tier 1 — Official source",
        "definition": (
            "Official government, procurement, federation, club, venue or issuing-organisation source."
        ),
    },
    "tier_2": {
        "label": "Tier 2 — Official announcement",
        "definition": "Official press release, official project announcement or formally authorised publication.",
    },
    "tier_3": {
        "label": "Tier 3 — Reputable publication",
        "definition": (
            "Reputable sports-business, financial, legal, procurement or industry publication."
        ),
    },
    "tier_4": {
        "label": "Tier 4 — Requires validation",
        "definition": "Early market signal, informal reference or source requiring independent validation.",
    },
}


class UrlValidationStatus(str, enum.Enum):
    NOT_REVIEWED = "not_reviewed"
    VALID = "valid"
    UNREACHABLE = "unreachable"
    ARCHIVED = "archived"
    INVALID = "invalid"


# --------------------------------------------------------- value status (§9)

class ValueStatus(str, enum.Enum):
    PUBLISHED_CONTRACT = "published_contract_value"
    PUBLISHED_PROGRAMME = "published_wider_programme_value"
    ESTIMATED_RANGE = "estimated_range"
    NOT_DISCLOSED = "value_not_disclosed"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


VALUE_STATUS_INFO: dict[str, dict[str, str]] = {
    "published_contract_value": {
        "label": "Published contract value",
        "definition": "The value of the contract available, as published by the issuing organisation.",
        "is_fact": "true",
    },
    "published_wider_programme_value": {
        "label": "Published wider programme value",
        "definition": (
            "A published figure for a broader programme or strategy. This is NOT the value "
            "available to VECTA and must never be presented as the contract value."
        ),
        "is_fact": "true",
    },
    "estimated_range": {
        "label": "Estimated range (AI)",
        "definition": "An AI estimate expressed as a range, with its methodology stated. Not a fact.",
        "is_fact": "false",
    },
    "value_not_disclosed": {
        "label": "Value not disclosed",
        "definition": "The opportunity is real but no value has been published.",
        "is_fact": "true",
    },
    "insufficient_evidence": {
        "label": "Insufficient evidence",
        "definition": "There is not enough evidence to publish or estimate a value.",
        "is_fact": "true",
    },
}

# Statuses that are AI estimates rather than published facts — the frontend
# must label these distinctly (§15) and never render them as published.
ESTIMATED_VALUE_STATUSES = {ValueStatus.ESTIMATED_RANGE.value}


# --------------------------------------------------- qualification state (§10)

class QualificationState(str, enum.Enum):
    NOT_ASSESSED = "not_assessed"
    VERIFICATION_REQUIRED = "verification_required"
    QUALIFIED = "qualified"
    CONDITIONALLY_QUALIFIED = "conditionally_qualified"
    DISQUALIFIED = "disqualified"


QUALIFICATION_STATE_LABELS: dict[str, str] = {
    "not_assessed": "Not assessed",
    "verification_required": "Verification required",
    "qualified": "Qualified",
    "conditionally_qualified": "Conditionally qualified",
    "disqualified": "Disqualified",
}

# Only these states may appear as active pursuits (§10).
ACTIVE_PIPELINE_STATES = {
    QualificationState.QUALIFIED.value,
    QualificationState.CONDITIONALLY_QUALIFIED.value,
}


class FailureType(str, enum.Enum):
    """Qualification failures are not all equal (§3 correction). A missing
    local entity is a task; a passed deadline is the end of the matter.
    Collapsing both into "Disqualified" would permanently bury recoverable
    opportunities, so failures are typed."""

    ABSOLUTE_DISQUALIFIER = "absolute_disqualifier"
    REMEDIABLE_BLOCKER = "remediable_blocker"
    UNRESOLVED_MANDATORY = "unresolved_mandatory_question"
    NON_MATERIAL_CONCERN = "non_material_concern"


FAILURE_TYPE_INFO: dict[str, dict[str, str]] = {
    "absolute_disqualifier": {
        "label": "Absolute disqualifier",
        "definition": "A permanent bar. The opportunity cannot be pursued and cannot be remediated.",
        "resulting_state": "disqualified",
    },
    "remediable_blocker": {
        "label": "Remediable blocker",
        "definition": (
            "A real obstacle that VECTA could plausibly resolve — securing a local entity, "
            "appointing a partner, forming a consortium, obtaining accreditation."
        ),
        "resulting_state": "conditionally_qualified",
    },
    "unresolved_mandatory_question": {
        "label": "Unresolved mandatory question",
        "definition": "A mandatory check that has not yet been answered either way.",
        "resulting_state": "verification_required",
    },
    "non_material_concern": {
        "label": "Non-material concern",
        "definition": "An open point that does not prevent qualification.",
        "resulting_state": "conditionally_qualified",
    },
}

# Checklist keys whose failure is an ABSOLUTE bar (§3).
ABSOLUTE_DISQUALIFIER_KEYS = {
    "live_status_verified",
    "reliable_source_present",
    "deadline_achievable",
    "basic_eligibility_met",
    "relevant_vecta_vertical",
    "plausible_route_to_market",
    "commercial_risk_acceptable",
    "reputational_risk_acceptable",
}

# Checklist keys whose failure is normally REMEDIABLE — these produce
# Conditionally Qualified, not permanent disqualification (§3).
REMEDIABLE_BLOCKER_KEYS = {
    "delivery_partner_understood",
    "local_entity_understood",
    "credible_delivery_model",
    "evidence_sufficient",
    "buyer_identifiable",
    "commercial_value_meaningful",
    "cost_to_pursue_proportionate",
    "strategically_desirable",
}


class GateAnswer(str, enum.Enum):
    YES = "yes"
    NO = "no"
    UNKNOWN = "unknown"
    NOT_APPLICABLE = "not_applicable"


# Qualification checklist (§10). `mandatory=True` means a "no" answer
# forces Disqualified; a material "unknown" on a mandatory item forces
# Verification Required.
QUALIFICATION_ITEMS: list[dict] = [
    {"key": "live_status_verified", "label": "Live status verified", "mandatory": True},
    {"key": "reliable_source_present", "label": "Reliable source present", "mandatory": True},
    {"key": "deadline_achievable", "label": "Deadline achievable", "mandatory": True},
    {"key": "basic_eligibility_met", "label": "Basic eligibility met", "mandatory": True},
    {"key": "relevant_vecta_vertical", "label": "Relevant VECTA vertical", "mandatory": True},
    {"key": "commercial_value_meaningful", "label": "Commercial value meaningful", "mandatory": False},
    {"key": "buyer_identifiable", "label": "Buyer or decision-maker identifiable", "mandatory": False},
    {"key": "plausible_route_to_market", "label": "Plausible route to market", "mandatory": True},
    {"key": "delivery_partner_understood", "label": "Delivery partner requirement understood", "mandatory": False},
    {"key": "local_entity_understood", "label": "Local entity requirement understood", "mandatory": False},
    {"key": "credible_delivery_model", "label": "Credible delivery model", "mandatory": False},
    {"key": "strategically_desirable", "label": "Strategic desirability", "mandatory": False},
    {"key": "cost_to_pursue_proportionate", "label": "Cost to pursue proportionate", "mandatory": False},
    {"key": "commercial_risk_acceptable", "label": "Commercial risk acceptable", "mandatory": True},
    {"key": "reputational_risk_acceptable", "label": "Reputational risk acceptable", "mandatory": True},
    {"key": "evidence_sufficient", "label": "Evidence sufficient", "mandatory": True},
]

MANDATORY_QUALIFICATION_KEYS = [i["key"] for i in QUALIFICATION_ITEMS if i["mandatory"]]


# ------------------------------------------------------------- confidence

class ConfidenceLevel(str, enum.Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


def vertical_label(value: str | None) -> str:
    if not value:
        return "—"
    return VERTICAL_V2_INFO.get(value, {}).get("label", value)
