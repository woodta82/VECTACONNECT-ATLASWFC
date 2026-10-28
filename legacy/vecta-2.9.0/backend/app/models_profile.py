"""Commercial Profile — Phase 3.1 (rebuild spec: the brain of ATLAS).

Defines how ATLAS evaluates opportunities *for VECTA specifically*. Until
this exists, `DEFAULT_PRIORITY_WEIGHTS` and the generic factor anchors in
`scoring_v2.py` are doing the work — which is to say every score is a
well-structured guess about what VECTA cares about.

VERSIONING — the load-bearing design decision
=============================================
The profile changes what every score *means*. If editing it silently
rewrote existing scores, past decisions would become unreconstructable:
you could not answer "why did we decline that in March?" because the
criteria would have moved underneath the record.

So: **a profile edit never mutates an existing score.** It creates a new
version, supersedes the old one, and marks affected scores stale for
rescoring. Every score, recommendation and decision stores the
`profile_version` it was produced under, and historical rows stay
readable against the profile that produced them.

One active row at a time, mirroring the single-login model. Satellite
tables hold the many-valued sections so they are queryable rather than
buried in JSON.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base
from .timeutils import utcnow


def _uuid() -> str:
    return str(uuid.uuid4())


# --------------------------------------------------------------- profile

class CommercialProfile(Base):
    """One active version at a time. Editing creates version n+1 and
    supersedes n; nothing is destroyed."""

    __tablename__ = "commercial_profile"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    version: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    # Strategic direction
    strategic_objectives: Mapped[str | None] = mapped_column(Text, nullable=True)
    growth_priorities: Mapped[str | None] = mapped_column(Text, nullable=True)
    revenue_objective: Mapped[float | None] = mapped_column(Float, nullable=True)
    long_term_direction: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Commercial thresholds — these drive real decisions (decline below
    # minimum, partner above mobilisation ceiling), so they are columns
    # rather than free text.
    min_viable_contract_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    target_contract_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_mobilisation_exposure: Mapped[float | None] = mapped_column(Float, nullable=True)
    target_gross_margin: Mapped[float | None] = mapped_column(Float, nullable=True)
    min_gross_margin: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Delivery reality — what VECTA can actually take on
    delivery_capacity_fte: Mapped[float | None] = mapped_column(Float, nullable=True)
    current_workload_pct: Mapped[float | None] = mapped_column(Float, nullable=True)

    risk_appetite: Mapped[str | None] = mapped_column(String(24), nullable=True)  # conservative|balanced|aggressive

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    created_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    regions: Mapped[list["ProfilePriorityRegion"]] = relationship(
        back_populates="profile", cascade="all, delete-orphan"
    )
    accounts: Mapped[list["ProfilePriorityAccount"]] = relationship(
        back_populates="profile", cascade="all, delete-orphan"
    )
    target_types: Mapped[list["ProfileTargetType"]] = relationship(
        back_populates="profile", cascade="all, delete-orphan"
    )
    capabilities: Mapped[list["ProfileCapability"]] = relationship(
        back_populates="profile", cascade="all, delete-orphan"
    )
    partners: Mapped[list["ProfilePartner"]] = relationship(
        back_populates="profile", cascade="all, delete-orphan"
    )
    exclusions: Mapped[list["ProfileExclusion"]] = relationship(
        back_populates="profile", cascade="all, delete-orphan"
    )
    weightings: Mapped[list["ProfileWeighting"]] = relationship(
        back_populates="profile", cascade="all, delete-orphan"
    )
    route_preferences: Mapped[list["ProfileRoutePreference"]] = relationship(
        back_populates="profile", cascade="all, delete-orphan"
    )


# ---------------------------------------------------------- satellites

class ProfilePriorityRegion(Base):
    __tablename__ = "profile_priority_region"
    __table_args__ = (UniqueConstraint("profile_id", "region", "market", name="uq_profile_region"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    profile_id: Mapped[str] = mapped_column(
        ForeignKey("commercial_profile.id", ondelete="CASCADE"), index=True
    )
    region: Mapped[str] = mapped_column(String(32), index=True)
    market: Mapped[str | None] = mapped_column(String(128), nullable=True)
    tier: Mapped[int] = mapped_column(Integer, default=2)  # 1 = highest priority
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)

    profile: Mapped["CommercialProfile"] = relationship(back_populates="regions")


class ProfilePriorityAccount(Base):
    __tablename__ = "profile_priority_account"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    profile_id: Mapped[str] = mapped_column(
        ForeignKey("commercial_profile.id", ondelete="CASCADE"), index=True
    )
    organisation_name: Mapped[str] = mapped_column(String(255), index=True)
    account_type: Mapped[str] = mapped_column(String(32))  # government|federation|club|brand|venue
    tier: Mapped[int] = mapped_column(Integer, default=2)
    objective: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    profile: Mapped["CommercialProfile"] = relationship(back_populates="accounts")


class ProfileTargetType(Base):
    __tablename__ = "profile_target_type"
    __table_args__ = (UniqueConstraint("profile_id", "commercial_type", name="uq_profile_target_type"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    profile_id: Mapped[str] = mapped_column(
        ForeignKey("commercial_profile.id", ondelete="CASCADE"), index=True
    )
    commercial_type: Mapped[str] = mapped_column(String(48), index=True)
    priority_weight: Mapped[float] = mapped_column(Float, default=1.0)

    profile: Mapped["CommercialProfile"] = relationship(back_populates="target_types")


class ProfileCapability(Base):
    """What VECTA can actually deliver, and how thinly. `is_specialist_scarce`
    is what turns a capacity number into a scheduling conflict."""

    __tablename__ = "profile_capability"
    __table_args__ = (UniqueConstraint("profile_id", "capability", name="uq_profile_capability"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    profile_id: Mapped[str] = mapped_column(
        ForeignKey("commercial_profile.id", ondelete="CASCADE"), index=True
    )
    capability: Mapped[str] = mapped_column(String(128), index=True)
    strength: Mapped[int] = mapped_column(Integer, default=50)  # 0-100
    specialist_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_specialist_scarce: Mapped[bool] = mapped_column(Boolean, default=False)
    evidence_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    profile: Mapped["CommercialProfile"] = relationship(back_populates="capabilities")


class ProfilePartner(Base):
    __tablename__ = "profile_partner"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    profile_id: Mapped[str] = mapped_column(
        ForeignKey("commercial_profile.id", ondelete="CASCADE"), index=True
    )
    partner_name: Mapped[str] = mapped_column(String(255), index=True)
    capability: Mapped[str | None] = mapped_column(String(255), nullable=True)
    regions: Mapped[str | None] = mapped_column(Text, nullable=True)  # comma-separated
    relationship_strength: Mapped[int] = mapped_column(Integer, default=50)
    provides_local_entity: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    profile: Mapped["CommercialProfile"] = relationship(back_populates="partners")


class ProfileExclusion(Base):
    """Hard boundaries. An exclusion match produces `decline` regardless of
    score — the one rule that overrides everything else."""

    __tablename__ = "profile_exclusion"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    profile_id: Mapped[str] = mapped_column(
        ForeignKey("commercial_profile.id", ondelete="CASCADE"), index=True
    )
    exclusion_type: Mapped[str] = mapped_column(String(32), index=True)
    # sector | commercial_type | region | counterparty
    value: Mapped[str] = mapped_column(String(255), index=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    profile: Mapped["CommercialProfile"] = relationship(back_populates="exclusions")


class ProfileRoutePreference(Base):
    __tablename__ = "profile_route_preference"
    __table_args__ = (UniqueConstraint("profile_id", "route_to_market", name="uq_profile_route"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    profile_id: Mapped[str] = mapped_column(
        ForeignKey("commercial_profile.id", ondelete="CASCADE"), index=True
    )
    route_to_market: Mapped[str] = mapped_column(String(48), index=True)
    preference: Mapped[int] = mapped_column(Integer, default=3)  # 1 = strongly preferred

    profile: Mapped["CommercialProfile"] = relationship(back_populates="route_preferences")


class ProfileWeighting(Base):
    """Overrides `DEFAULT_PRIORITY_WEIGHTS`. Validated to sum to 1.0 before
    activation — a profile whose weights sum to 0.8 would silently deflate
    every priority score."""

    __tablename__ = "profile_weighting"
    __table_args__ = (UniqueConstraint("profile_id", "dimension", name="uq_profile_weighting"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    profile_id: Mapped[str] = mapped_column(
        ForeignKey("commercial_profile.id", ondelete="CASCADE"), index=True
    )
    dimension: Mapped[str] = mapped_column(String(32), index=True)
    # strategic_alignment | commercial_attractiveness | win_probability | inverse_risk
    weight: Mapped[float] = mapped_column(Float)

    profile: Mapped["CommercialProfile"] = relationship(back_populates="weightings")


class ProfileFactorAnchor(Base):
    """VECTA-specific restatement of what 0/50/100 mean for a factor.
    Injected into the AI prompt, which is generated from the engines — so
    the prompt and the validator cannot drift apart."""

    __tablename__ = "profile_factor_anchor"
    __table_args__ = (UniqueConstraint("profile_id", "factor_key", name="uq_profile_anchor"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    profile_id: Mapped[str] = mapped_column(
        ForeignKey("commercial_profile.id", ondelete="CASCADE"), index=True
    )
    factor_key: Mapped[str] = mapped_column(String(64), index=True)
    anchor_0: Mapped[str | None] = mapped_column(Text, nullable=True)
    anchor_50: Mapped[str | None] = mapped_column(Text, nullable=True)
    anchor_100: Mapped[str | None] = mapped_column(Text, nullable=True)


class ProfileChangeLog(Base):
    """Field-level history across versions. `profile_change_log` answers
    'what did we change, when, and why' without diffing two versions by
    hand."""

    __tablename__ = "profile_change_log"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    from_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    to_version: Mapped[int] = mapped_column(Integer, index=True)
    field_path: Mapped[str] = mapped_column(String(128), index=True)
    previous_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
