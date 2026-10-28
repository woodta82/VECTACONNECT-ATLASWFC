"""Evidence model and backend-enforced verification rules (spec §4–§5, §7–§8).

Two rules drive this module, and both are enforced HERE — in the service
layer — rather than in the AI prompt or the frontend, because a prompt can
be ignored and a frontend can be bypassed:

1. A record cannot be saved as a Confirmed Opportunity unless it carries
   real, checkable evidence (§4).
2. Evidence supports SPECIFIC CLAIMS, not the whole record (§5). An
   official source proving a tender exists does not thereby validate an
   AI's guess at its value. Each evidence record therefore declares which
   claims it supports, and a fact is only "verified" if evidence exists
   for that particular claim.
"""
from __future__ import annotations

import enum
from .timeutils import utcnow

from .taxonomy import OpportunityClassification, SourceTier, UrlValidationStatus


class ClaimType(str, enum.Enum):
    """The specific claims a piece of evidence can support (§5)."""

    OPPORTUNITY_EXISTENCE = "opportunity_existence"
    LIVE_STATUS = "live_status"
    ISSUING_ORGANISATION = "issuing_organisation"
    DEADLINE = "deadline"
    PUBLISHED_VALUE = "published_value"
    ELIGIBILITY = "eligibility"
    GEOGRAPHIC_SCOPE = "geographic_scope"
    PROCUREMENT_ROUTE = "procurement_route"
    PROGRAMME_DESCRIPTION = "programme_description"


CLAIM_TYPE_LABELS: dict[str, str] = {
    "opportunity_existence": "Opportunity existence",
    "live_status": "Live status",
    "issuing_organisation": "Issuing organisation",
    "deadline": "Deadline",
    "published_value": "Published value",
    "eligibility": "Eligibility",
    "geographic_scope": "Geographic scope",
    "procurement_route": "Procurement route",
    "programme_description": "Programme description",
}


class EvidenceType(str, enum.Enum):
    TENDER_NOTICE = "tender_notice"
    PROCUREMENT_PORTAL = "procurement_portal"
    PRESS_RELEASE = "press_release"
    OFFICIAL_ANNOUNCEMENT = "official_announcement"
    NEWS_ARTICLE = "news_article"
    ORGANISATION_WEBSITE = "organisation_website"
    POLICY_DOCUMENT = "policy_document"
    FINANCIAL_FILING = "financial_filing"
    OTHER = "other"


# Tiers that can support a Confirmed classification (§4, §7).
CONFIRMING_TIERS = {SourceTier.TIER_1.value, SourceTier.TIER_2.value}
# URL states that count as checked (§4).
ACCEPTED_URL_STATES = {UrlValidationStatus.VALID.value, UrlValidationStatus.ARCHIVED.value}


def new_evidence(
    url: str,
    source_tier: str,
    claims_supported: list[str],
    page_title: str | None = None,
    publisher: str | None = None,
    publication_date: str | None = None,
    no_publication_date_reason: str | None = None,
    evidence_type: str = EvidenceType.OTHER.value,
    is_official_source: bool = False,
    is_definitive: bool = False,
    url_validation_status: str = UrlValidationStatus.NOT_REVIEWED.value,
    confidence: str = "medium",
    notes: str | None = None,
) -> dict:
    """Builds an evidence record. `claims_supported` is required and must
    be non-empty — evidence that supports nothing in particular is not
    evidence, it's a link."""
    if not url or not url.strip():
        raise ValueError("Evidence requires a URL.")
    if source_tier not in {t.value for t in SourceTier}:
        raise ValueError(f"Invalid source tier: {source_tier}")
    valid_claims = {c.value for c in ClaimType}
    bad = [c for c in claims_supported if c not in valid_claims]
    if bad:
        raise ValueError(f"Unknown claim types: {bad}")
    if not claims_supported:
        raise ValueError(
            "Evidence must declare at least one claim it supports — an unattached "
            "source cannot validate anything (spec §5)."
        )
    now = utcnow().isoformat()
    return {
        "url": url.strip(),
        "page_title": page_title,
        "publisher": publisher,
        "source_tier": source_tier,
        "publication_date": publication_date,
        "no_publication_date_reason": no_publication_date_reason,
        "date_accessed": now,
        "evidence_type": evidence_type,
        "claims_supported": sorted(set(claims_supported)),
        "is_official_source": is_official_source,
        "is_definitive": is_definitive,
        "url_validation_status": url_validation_status,
        "last_validated_at": now if url_validation_status in ACCEPTED_URL_STATES else None,
        "confidence": confidence,
        "notes": notes,
    }


def evidence_supports_claim(evidence_records: list[dict], claim: str) -> list[dict]:
    """Returns only the evidence records that actually support `claim`.

    This is the mechanism preventing an official source from silently
    validating unrelated AI interpretation (§5): a Tier 1 tender notice
    proving OPPORTUNITY_EXISTENCE returns nothing when asked about
    PUBLISHED_VALUE unless it explicitly declared that claim.
    """
    return [e for e in (evidence_records or []) if claim in (e.get("claims_supported") or [])]


def is_fact_verified(evidence_records: list[dict], claim: str) -> bool:
    """A fact is verified only if at least one CHECKED evidence record
    supports that specific claim."""
    supporting = evidence_supports_claim(evidence_records, claim)
    return any(e.get("url_validation_status") in ACCEPTED_URL_STATES for e in supporting)


def validate_confirmed_opportunity(
    classification: str,
    evidence_records: list[dict],
    last_verified_at: str | None,
    confidence: str | None,
) -> tuple[bool, list[str]]:
    """Backend gate for Confirmed Opportunity status (§4).

    Returns (allowed, failures). Called by the persistence layer before
    save — a record failing this cannot be stored as Confirmed regardless
    of what the AI proposed or the frontend submitted.
    """
    if classification != OpportunityClassification.CONFIRMED.value:
        return True, []

    failures: list[str] = []
    records = evidence_records or []

    # 1. At least one Tier 1, or a Tier 2 explicitly marked definitive.
    qualifying = [
        e for e in records
        if e.get("source_tier") == SourceTier.TIER_1.value
        or (e.get("source_tier") == SourceTier.TIER_2.value and e.get("is_definitive"))
    ]
    if not qualifying:
        failures.append(
            "Requires at least one Tier 1 source, or a Tier 2 source marked definitive."
        )

    # 2. Evidence specifically supporting live status.
    if not evidence_supports_claim(records, ClaimType.LIVE_STATUS.value):
        failures.append("Requires an evidence record supporting the opportunity's live status.")

    # 3. A validated or manually reviewed URL.
    if not any(e.get("url_validation_status") in ACCEPTED_URL_STATES for e in records):
        failures.append("Requires at least one validated or manually reviewed URL.")

    # 4. Publication date, or a documented reason there isn't one.
    for e in qualifying:
        if not e.get("publication_date") and not e.get("no_publication_date_reason"):
            failures.append(
                f"Evidence '{e.get('url')}' has no publication date and no documented reason for its absence."
            )
            break

    # 5. Last-verification timestamp.
    if not last_verified_at:
        failures.append("Requires a last-verification timestamp.")

    # 6. Confidence assessment.
    if not confidence:
        failures.append("Requires a confidence assessment.")

    return (not failures), failures


def downgrade_classification_if_unsupported(
    classification: str,
    evidence_records: list[dict],
    last_verified_at: str | None,
    confidence: str | None,
) -> tuple[str, str | None]:
    """Non-destructive enforcement: rather than rejecting the record, an
    unsupported Confirmed claim is downgraded to Unverified Lead with the
    reason recorded. Losing the finding entirely would be worse than
    holding it at a lower classification until evidence arrives."""
    allowed, failures = validate_confirmed_opportunity(
        classification, evidence_records, last_verified_at, confidence
    )
    if allowed:
        return classification, None
    return (
        OpportunityClassification.UNVERIFIED_LEAD.value,
        "Downgraded from Confirmed opportunity — evidence requirements not met: "
        + "; ".join(failures),
    )
