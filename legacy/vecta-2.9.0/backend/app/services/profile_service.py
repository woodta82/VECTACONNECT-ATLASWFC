"""Commercial Profile service — Phase 3.1.

Owns three responsibilities:

1. **Versioning that never rewrites history.** Editing creates a new
   version and supersedes the old one. Existing scores are marked stale
   rather than mutated, so a past decision remains readable against the
   criteria that produced it.
2. **Supplying scoring inputs.** Weights override
   `DEFAULT_PRIORITY_WEIGHTS`; factor anchors override the generic ones
   in the AI prompt.
3. **Answering profile questions the decision layer needs** — is this
   excluded, is this a priority region, do we have this capability, are
   we at capacity.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..models_phase2 import PursuitPriority, ScoreAssessment
from ..models_profile import (
    CommercialProfile,
    ProfileCapability,
    ProfileChangeLog,
    ProfileExclusion,
    ProfileFactorAnchor,
    ProfilePartner,
    ProfilePriorityAccount,
    ProfilePriorityRegion,
    ProfileRoutePreference,
    ProfileTargetType,
    ProfileWeighting,
)
from ..scoring_v2 import DEFAULT_PRIORITY_WEIGHTS, DIMENSIONS
from ..timeutils import utcnow


class ProfileError(Exception):
    """Raised when a profile operation would produce an invalid state."""

    def __init__(self, message: str, failures: list[str] | None = None) -> None:
        super().__init__(message)
        self.failures = failures or []


# Sections the completeness meter tracks. Named here so the UI and the
# service agree on what "complete" means.
PROFILE_SECTIONS = [
    ("strategic", "Strategic priorities"),
    ("markets", "Priority markets"),
    ("thresholds", "Commercial thresholds"),
    ("capacity", "Delivery capacity"),
    ("capabilities", "Capabilities"),
    ("partners", "Partner network"),
    ("exclusions", "Exclusions"),
    ("weightings", "Scoring weights"),
]


# ------------------------------------------------------------- reading

def get_active_profile(db: Session) -> CommercialProfile | None:
    return db.query(CommercialProfile).filter_by(is_active=True).first()


def get_profile_version(db: Session, version: int) -> CommercialProfile | None:
    return db.query(CommercialProfile).filter_by(version=version).first()


def active_version(db: Session) -> int | None:
    profile = get_active_profile(db)
    return profile.version if profile else None


# --------------------------------------------------- scoring integration

def priority_weights(db: Session) -> dict[str, float]:
    """Weights for `compute_pursuit_priority`.

    Falls back to `DEFAULT_PRIORITY_WEIGHTS` when the profile has none —
    which is the honest behaviour for a profile that has not been filled
    in. Generic-but-documented beats confident-but-arbitrary.
    """
    profile = get_active_profile(db)
    if profile is None:
        return dict(DEFAULT_PRIORITY_WEIGHTS)

    rows = db.query(ProfileWeighting).filter_by(profile_id=profile.id).all()
    if not rows:
        return dict(DEFAULT_PRIORITY_WEIGHTS)

    weights = dict(DEFAULT_PRIORITY_WEIGHTS)
    for row in rows:
        weights[row.dimension] = row.weight
    return weights


def factor_anchors(db: Session) -> dict[str, dict[str, str]]:
    """VECTA-specific 0/50/100 anchors, keyed by factor. Injected into the
    AI prompt, which is generated from the engines — so the prompt and the
    validator cannot drift apart."""
    profile = get_active_profile(db)
    if profile is None:
        return {}
    out: dict[str, dict[str, str]] = {}
    for row in db.query(ProfileFactorAnchor).filter_by(profile_id=profile.id).all():
        anchors = {
            k: v
            for k, v in (("0", row.anchor_0), ("50", row.anchor_50), ("100", row.anchor_100))
            if v
        }
        if anchors:
            out[row.factor_key] = anchors
    return out


def validate_weights(weights: dict[str, float]) -> list[str]:
    """Weights must sum to 1.0 and name real dimensions.

    A profile whose weights sum to 0.8 would silently deflate every
    priority score — the kind of defect that looks like "the model is
    being conservative" rather than an error.
    """
    failures: list[str] = []
    valid = set(DIMENSIONS) | {"inverse_risk"}
    unknown = set(weights) - valid
    if unknown:
        failures.append(f"Unknown scoring dimensions: {sorted(unknown)}")
    total = sum(weights.values())
    if abs(total - 1.0) > 0.001:
        failures.append(f"Weights must sum to 1.0 (currently {total:.3f})")
    negative = [k for k, v in weights.items() if v < 0]
    if negative:
        failures.append(f"Weights cannot be negative: {negative}")
    return failures


# ------------------------------------------------------------ versioning

def create_version(db: Session, fields: dict, reason: str,
                   sections: dict[str, list[dict]] | None = None) -> CommercialProfile:
    """Creates the next profile version and supersedes the current one.

    Never mutates an existing version. Records field-level changes in
    `profile_change_log`, and marks affected scores stale rather than
    rescoring them here — rescoring is a separate, explicit action, so a
    profile edit does not silently trigger a large recompute.
    """
    if not reason or not reason.strip():
        raise ProfileError("A profile change requires a reason.", ["reason is required"])

    current = get_active_profile(db)
    next_version = (current.version + 1) if current else 1

    if sections and "weightings" in sections:
        weights = {w["dimension"]: w["weight"] for w in sections["weightings"]}
        failures = validate_weights(weights)
        if failures:
            raise ProfileError("Invalid scoring weights.", failures)

    new = CommercialProfile(version=next_version, is_active=True, created_reason=reason.strip())
    for key, value in (fields or {}).items():
        if hasattr(new, key) and key not in ("id", "version", "is_active", "created_at"):
            setattr(new, key, value)
    db.add(new)
    db.flush()

    _copy_or_replace_sections(db, current, new, sections or {})

    if current is not None:
        _log_changes(db, current, new, fields or {}, reason)
        current.is_active = False
        current.superseded_at = utcnow()

    db.flush()
    return new


def _copy_or_replace_sections(db: Session, previous: CommercialProfile | None,
                              new: CommercialProfile, sections: dict[str, list[dict]]) -> None:
    """Sections supplied are replaced; sections omitted are carried
    forward from the previous version.

    Carrying forward matters: editing one section must not silently blank
    the others, which is the commonest way versioned-config systems lose
    data.
    """
    section_models = {
        "regions": (ProfilePriorityRegion, ("region", "market", "tier", "rationale")),
        "accounts": (ProfilePriorityAccount,
                     ("organisation_name", "account_type", "tier", "objective", "owner_name")),
        "target_types": (ProfileTargetType, ("commercial_type", "priority_weight")),
        "capabilities": (ProfileCapability,
                         ("capability", "strength", "specialist_count",
                          "is_specialist_scarce", "evidence_note")),
        "partners": (ProfilePartner,
                     ("partner_name", "capability", "regions", "relationship_strength",
                      "provides_local_entity", "is_active")),
        "exclusions": (ProfileExclusion, ("exclusion_type", "value", "reason")),
        "route_preferences": (ProfileRoutePreference, ("route_to_market", "preference")),
        "weightings": (ProfileWeighting, ("dimension", "weight")),
        "factor_anchors": (ProfileFactorAnchor,
                           ("factor_key", "anchor_0", "anchor_50", "anchor_100")),
    }

    for key, (model, columns) in section_models.items():
        if key in sections:
            rows = sections[key]
        elif previous is not None:
            rows = [
                {c: getattr(r, c) for c in columns}
                for r in db.query(model).filter_by(profile_id=previous.id).all()
            ]
        else:
            rows = []
        for row in rows:
            db.add(model(profile_id=new.id, **{c: row.get(c) for c in columns if c in row}))
    db.flush()


def _log_changes(db: Session, previous: CommercialProfile, new: CommercialProfile,
                 fields: dict, reason: str) -> None:
    for key, value in (fields or {}).items():
        old = getattr(previous, key, None)
        if old != value:
            db.add(
                ProfileChangeLog(
                    from_version=previous.version,
                    to_version=new.version,
                    field_path=key,
                    previous_value=str(old) if old is not None else None,
                    new_value=str(value) if value is not None else None,
                    reason=reason.strip(),
                )
            )


def mark_scores_stale(db: Session, reason: str = "profile change") -> int:
    """Flags every score for rescoring WITHOUT changing its value.

    This is the mechanism that keeps history readable: the old score
    remains exactly as computed under the old profile, and is simply
    marked as no longer reflecting current criteria.
    """
    count = db.query(ScoreAssessment).filter(ScoreAssessment.is_stale.is_(False)).update(
        {ScoreAssessment.is_stale: True}, synchronize_session=False
    )
    db.flush()
    return count


def stale_score_count(db: Session) -> int:
    return db.query(ScoreAssessment).filter(ScoreAssessment.is_stale.is_(True)).count()


def stamp_profile_version(db: Session, opportunity_id: str, version: int | None) -> None:
    """Records which profile produced a score/priority. Called by the
    scoring path so every output is attributable."""
    db.query(ScoreAssessment).filter_by(opportunity_id=opportunity_id).update(
        {ScoreAssessment.profile_version: version, ScoreAssessment.is_stale: False},
        synchronize_session=False,
    )
    db.query(PursuitPriority).filter_by(opportunity_id=opportunity_id).update(
        {PursuitPriority.profile_version: version}, synchronize_session=False
    )
    db.flush()


# ---------------------------------------------------------- completeness

def completeness(db: Session) -> dict:
    """Which sections are filled in, and what falls back to defaults.

    The main adoption risk in Phase 3 is a half-filled profile that looks
    authoritative while being arbitrary. Making incompleteness visible —
    and naming the fallback — is the mitigation.
    """
    profile = get_active_profile(db)
    if profile is None:
        return {
            "version": None,
            "percent": 0,
            "sections": [
                {"key": k, "label": l, "complete": False,
                 "fallback": "Generic defaults — no profile exists yet"}
                for k, l in PROFILE_SECTIONS
            ],
        }

    def has(model) -> bool:
        return db.query(model).filter_by(profile_id=profile.id).count() > 0

    status = {
        "strategic": bool(profile.strategic_objectives and profile.growth_priorities),
        "markets": has(ProfilePriorityRegion),
        "thresholds": profile.min_viable_contract_value is not None
        and profile.target_contract_value is not None,
        "capacity": profile.delivery_capacity_fte is not None,
        "capabilities": has(ProfileCapability),
        "partners": has(ProfilePartner),
        "exclusions": has(ProfileExclusion),
        "weightings": has(ProfileWeighting),
    }
    fallbacks = {
        "strategic": "Strategic alignment scored against generic sport-sector assumptions",
        "markets": "All regions treated as equal priority",
        "thresholds": "No minimum viable value — low-value opportunities will not be filtered",
        "capacity": "Capacity conflicts cannot be detected",
        "capabilities": "Capability gaps cannot be identified",
        "partners": "Partner-route recommendations cannot name a partner",
        "exclusions": "No opportunity will be auto-declined on policy grounds",
        "weightings": "Default 35/30/25/10 weighting",
    }

    sections = [
        {
            "key": k,
            "label": label,
            "complete": status[k],
            "fallback": None if status[k] else fallbacks[k],
        }
        for k, label in PROFILE_SECTIONS
    ]
    done = sum(1 for s in sections if s["complete"])
    return {
        "version": profile.version,
        "percent": round(done / len(sections) * 100),
        "complete_sections": done,
        "total_sections": len(sections),
        "sections": sections,
    }


# --------------------------------------------------- decision-layer queries

def is_excluded(db: Session, *, sector: str | None = None, commercial_type: str | None = None,
                region: str | None = None, counterparty: str | None = None) -> tuple[bool, str | None]:
    """Hard boundary check. An exclusion match produces `decline`
    regardless of score — the one rule that overrides everything."""
    profile = get_active_profile(db)
    if profile is None:
        return False, None
    checks = [
        ("sector", sector),
        ("commercial_type", commercial_type),
        ("region", region),
        ("counterparty", counterparty),
    ]
    for exclusion_type, value in checks:
        if not value:
            continue
        row = (
            db.query(ProfileExclusion)
            .filter_by(profile_id=profile.id, exclusion_type=exclusion_type)
            .filter(ProfileExclusion.value.ilike(value))
            .first()
        )
        if row:
            return True, f"Excluded by profile ({exclusion_type} = {row.value}): {row.reason or 'no reason recorded'}"
    return False, None


def region_tier(db: Session, region: str | None, market: str | None = None) -> int | None:
    """1 = highest priority. None means the profile has no view, which is
    different from 'low priority'."""
    profile = get_active_profile(db)
    if profile is None or not region:
        return None
    q = db.query(ProfilePriorityRegion).filter_by(profile_id=profile.id, region=region)
    if market:
        exact = q.filter_by(market=market).first()
        if exact:
            return exact.tier
    row = q.filter(ProfilePriorityRegion.market.is_(None)).first()
    return row.tier if row else None


def meets_value_threshold(db: Session, value: float | None) -> tuple[bool, str | None]:
    profile = get_active_profile(db)
    if profile is None or profile.min_viable_contract_value is None or value is None:
        return True, None
    if value < profile.min_viable_contract_value:
        return False, (
            f"Below minimum viable contract value "
            f"({value:,.0f} vs {profile.min_viable_contract_value:,.0f})"
        )
    return True, None


def capacity_status(db: Session) -> dict:
    profile = get_active_profile(db)
    if profile is None or profile.current_workload_pct is None:
        return {"known": False, "utilisation": None, "strained": False, "label": "Capacity unknown"}
    util = profile.current_workload_pct
    strained = util >= 80
    return {
        "known": True,
        "utilisation": util,
        "strained": strained,
        "label": f"{util:.0f}% utilised" + (" — strained" if strained else ""),
        "capacity_fte": profile.delivery_capacity_fte,
    }


def scarce_capabilities(db: Session) -> list[str]:
    """Capabilities with few specialists. Turns a capacity percentage into
    a scheduling conflict between named pursuits."""
    profile = get_active_profile(db)
    if profile is None:
        return []
    return [
        c.capability
        for c in db.query(ProfileCapability)
        .filter_by(profile_id=profile.id, is_specialist_scarce=True)
        .all()
    ]


def partner_for_local_entity(db: Session, region: str | None) -> ProfilePartner | None:
    """Names a partner when the recommendation is 'secure local partner' —
    a recommendation that cannot name anyone is not actionable."""
    profile = get_active_profile(db)
    if profile is None:
        return None
    q = db.query(ProfilePartner).filter_by(
        profile_id=profile.id, is_active=True, provides_local_entity=True
    )
    if region:
        for p in q.all():
            if p.regions and region.lower() in p.regions.lower():
                return p
    return q.first()
