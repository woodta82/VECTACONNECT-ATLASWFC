import enum
import uuid
from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .timeutils import utcnow

from .database import Base
from .regions import Region, Vertical


def _uuid() -> str:
    return str(uuid.uuid4())


def StrEnum(enum_cls):
    """SQLAlchemy's Enum() stores/matches by the Python enum member's `.name`
    by default (e.g. "MEDIA"), not `.value` (e.g. "media") — but every value
    in this codebase (API query params, request bodies, frontend) uses the
    lowercase `.value` form. Without this, filters like `?vertical=media`
    or constructing rows via plain strings would silently mismatch or raise
    a LookupError at query time. This wrapper makes the column match on
    `.value` instead, so plain lowercase strings work everywhere."""
    return Enum(enum_cls, values_callable=lambda cls: [e.value for e in cls])


class Stage(str, enum.Enum):
    DISCOVERED = "discovered"
    QUALIFIED = "qualified"
    ENGAGED = "engaged"
    PROPOSAL = "proposal"
    WON = "won"
    LOST = "lost"


# Standard CRM-style close probability per stage, used to compute a
# weighted pipeline value (raw value × likelihood) alongside the raw
# total on Reports and the Control Panel. These are starting-point
# estimates, not derived from VECTA's actual historical win rates yet —
# revisit once there's enough Won/Lost history to calibrate against.
STAGE_PROBABILITY: dict[str, float] = {
    Stage.DISCOVERED.value: 0.10,
    Stage.QUALIFIED.value: 0.25,
    Stage.ENGAGED.value: 0.45,
    Stage.PROPOSAL.value: 0.65,
    Stage.WON.value: 1.0,
    Stage.LOST.value: 0.0,
}


class OrgType(str, enum.Enum):
    FEDERATION = "federation"
    CLUB = "club"
    GOVERNMENT = "government"
    BRAND = "brand"
    VENUE = "venue"
    OTHER = "other"


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    OPERATOR = "operator"
    VIEWER = "viewer"


class ScanType(str, enum.Enum):
    SCHEDULED = "scheduled"
    ON_DEMAND = "on_demand"
    SAVED_SEARCH = "saved_search"


class InteractionType(str, enum.Enum):
    NOTE = "note"
    MESSAGE = "message"
    MEETING = "meeting"
    TASK = "task"


class User(Base):
    """RETAINED FOR DATA INTEGRITY ONLY — not part of the application.

    ATLAS is single-login by mandate (see docs/SECURITY.md): the users
    API router and Settings UI were removed in v2.8, and nothing can
    create, list, or authenticate against rows in this table. It remains
    solely because three tables hold owner_id foreign keys to it and
    production data may reference existing rows; dropping it would be a
    destructive migration for zero security gain, since it grants no
    access. The owner/commercial-owner concept is an informational text
    field, not an account."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255))
    email: Mapped[str] = mapped_column(String(255), unique=True)
    role: Mapped[UserRole] = mapped_column(StrEnum(UserRole), default=UserRole.OPERATOR)
    notification_prefs: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Organisation(Base):
    __tablename__ = "organisations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(512))
    org_type: Mapped[OrgType] = mapped_column(StrEnum(OrgType), default=OrgType.OTHER)
    region: Mapped[Region | None] = mapped_column(StrEnum(Region), nullable=True, index=True)
    market: Mapped[str | None] = mapped_column(String(255), nullable=True)
    website: Mapped[str | None] = mapped_column(Text, nullable=True)
    linkedin_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ScanRun(Base):
    __tablename__ = "scan_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    type: Mapped[ScanType] = mapped_column(StrEnum(ScanType), default=ScanType.SCHEDULED)
    vertical_scope: Mapped[Vertical | None] = mapped_column(StrEnum(Vertical), nullable=True)
    region_scope: Mapped[Region | None] = mapped_column(StrEnum(Region), nullable=True)
    query_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    sources_checked: Mapped[int] = mapped_column(Integer, default=0)
    new_items: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(32), default="running")  # running|complete|failed
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class Opportunity(Base):
    __tablename__ = "opportunities"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    scan_run_id: Mapped[str | None] = mapped_column(ForeignKey("scan_runs.id"), nullable=True)
    organisation_id: Mapped[str | None] = mapped_column(ForeignKey("organisations.id"), nullable=True)

    title: Mapped[str] = mapped_column(String(512))
    # NOT NULL by design: an opportunity with no summary is unreadable in
    # a list view. Every creation path supplies one — the scanner falls
    # back to the title if the AI omits it, and the legacy migration
    # supplies a clearly-marked placeholder rather than inventing prose.
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    vertical: Mapped[Vertical | None] = mapped_column(StrEnum(Vertical), nullable=True, index=True)
    region: Mapped[Region | None] = mapped_column(StrEnum(Region), nullable=True, index=True)
    market: Mapped[str | None] = mapped_column(String(255), nullable=True)

    value_estimate: Mapped[float | None] = mapped_column(Float, nullable=True)
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    deadline: Mapped[date | None] = mapped_column(Date, nullable=True)
    source_urls: Mapped[list] = mapped_column(JSON, default=list)

    # VECTA Alignment Score — see ai/alignment_scoring.py. score_breakdown holds
    # the five weighted sub-scores (0-100 each) the AI returned.
    # --- Phase 2 classification (v2.9) ---------------------------------
    # Single-valued fields live here; contributing verticals, secondary
    # commercial types and route requirements are join tables in
    # models_phase2.py because they are many-per-opportunity.
    classification: Mapped[str | None] = mapped_column(String(48), nullable=True, index=True)
    classification_rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    primary_vertical: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    vertical_rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    primary_commercial_type: Mapped[str | None] = mapped_column(String(48), nullable=True, index=True)
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verification_confidence: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    requires_human_review: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    human_review_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- legacy (superseded by the four-dimension model) ---------------
    # Retained and read-only: the Phase 2 engines never consume these, and
    # the migration copies them into legacy_opportunity_data as well so a
    # future cleanup can drop them without losing history.
    alignment_score: Mapped[int] = mapped_column(Integer, default=0)
    score_breakdown: Mapped[dict] = mapped_column(JSON, default=dict)
    priority: Mapped[bool] = mapped_column(Boolean, default=False)  # score >= 70

    stage: Mapped[Stage] = mapped_column(StrEnum(Stage), default=Stage.DISCOVERED)
    # DEPRECATED (v2.9): account relationship to the legacy users table.
    # Retained nullable so existing production rows migrate without loss;
    # nothing writes it any more. Use owner_name below — ATLAS is
    # single-login, so the commercial owner is information, not an account.
    owner_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    owner_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Captured when stage moves to Won or Lost — e.g. "budget", "competitor",
    # "timing", "no response". Free text so it fits any deal without a rigid
    # taxonomy; Reports aggregates it as-is.
    outcome_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Deadline alert tracking so T-14/T-7/T-2 notifications fire once each, not every cycle
    alerted_14: Mapped[bool] = mapped_column(Boolean, default=False)
    alerted_7: Mapped[bool] = mapped_column(Boolean, default=False)
    alerted_2: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class Contact(Base):
    __tablename__ = "contacts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255))
    role: Mapped[str | None] = mapped_column(String(512), nullable=True)
    organisation_id: Mapped[str | None] = mapped_column(ForeignKey("organisations.id"), nullable=True)
    opportunity_id: Mapped[str | None] = mapped_column(ForeignKey("opportunities.id"), nullable=True)
    region: Mapped[Region | None] = mapped_column(StrEnum(Region), nullable=True)

    # Public LinkedIn *search* link, not a scraped profile — see ai/contact_discovery.py
    linkedin_search_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    linkedin_profile_url: Mapped[str | None] = mapped_column(Text, nullable=True)  # only if a human confirms/adds it

    relevance_score: Mapped[int] = mapped_column(Integer, default=50)  # 0-100
    connection_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(32), default="ai_research")  # ai_research|manual

    last_interaction_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Interaction(Base):
    __tablename__ = "interactions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    contact_id: Mapped[str] = mapped_column(ForeignKey("contacts.id"))
    opportunity_id: Mapped[str | None] = mapped_column(ForeignKey("opportunities.id"), nullable=True)
    type: Mapped[InteractionType] = mapped_column(StrEnum(InteractionType), default=InteractionType.NOTE)
    content: Mapped[str] = mapped_column(Text)
    # DEPRECATED (v2.9): account relationship to the legacy users table.
    # Retained nullable so existing production rows migrate without loss;
    # nothing writes it any more. Use owner_name below — ATLAS is
    # single-login, so the commercial owner is information, not an account.
    owner_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    owner_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # For outreach drafts: drafted=True + sent=False until a human marks it sent (human-in-the-loop)
    draft: Mapped[bool] = mapped_column(Boolean, default=False)
    sent: Mapped[bool] = mapped_column(Boolean, default=False)
    # For type=task: when it's due, and whether it's been done. Both null/False
    # for non-task interaction types.
    due_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed: Mapped[bool] = mapped_column(Boolean, default=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class OpportunityActivity(Base):
    """A lightweight, append-only activity trail per opportunity — stage
    changes, outreach drafted/sent, etc. Auto-created by the API, not
    user-editable. Note: this system doesn't have per-user authentication
    yet (see docs/SECURITY.md), so entries record *what* happened and
    *when*, not reliably *who* did it — that's a real limitation, not an
    oversight, and gets resolved once real login exists."""

    __tablename__ = "opportunity_activity"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    opportunity_id: Mapped[str] = mapped_column(ForeignKey("opportunities.id"))
    event_type: Mapped[str] = mapped_column(String(32))  # stage_change|note|system
    detail: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuthCredential(Base):
    """Single-row table holding the shared login's password hash — never
    the password itself. PBKDF2-HMAC-SHA256 with per-hash random salt and
    600k iterations (format: pbkdf2_sha256$iterations$salt_hex$hash_hex).
    Seeded once on first startup from the LOGIN_PASSWORD env var (see
    main.py), then owned by the database from that point on — the env var
    is bootstrap-only and changing it later does nothing; use the
    password-change flow in Settings instead."""

    __tablename__ = "auth_credential"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    password_hash: Mapped[str] = mapped_column(String(255))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class AuthSession(Base):
    """Server-side login sessions. The browser holds only an opaque random
    token in an HttpOnly cookie; this table stores a SHA-256 of that token
    (so a database leak doesn't yield usable sessions), plus the CSRF
    token paired with it and an absolute expiry."""

    __tablename__ = "auth_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    csrf_token: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_used_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SecurityEvent(Base):
    """Append-only security audit log: login success/failure, lockouts,
    password changes, logouts. Deliberately minimal — event type, source
    IP, freeform detail, timestamp — and never stores passwords or
    tokens."""

    __tablename__ = "security_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    event_type: Mapped[str] = mapped_column(String(48))
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SavedSearch(Base):
    __tablename__ = "saved_searches"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255))
    region: Mapped[Region] = mapped_column(StrEnum(Region))
    market: Mapped[str | None] = mapped_column(String(255), nullable=True)
    query_text: Mapped[str] = mapped_column(Text)
    parsed_filters: Mapped[dict] = mapped_column(JSON, default=dict)
    schedule_hours: Mapped[float | None] = mapped_column(Float, nullable=True)  # null = one-off, not re-run
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # DEPRECATED (v2.9): account relationship to the legacy users table.
    # Retained nullable so existing production rows migrate without loss;
    # nothing writes it any more. Use owner_name below — ATLAS is
    # single-login, so the commercial owner is information, not an account.
    owner_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    owner_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    kind: Mapped[str] = mapped_column(String(32))  # priority_opportunity|deadline|new_contact|digest
    title: Mapped[str] = mapped_column(String(512))
    body: Mapped[str] = mapped_column(Text)
    opportunity_id: Mapped[str | None] = mapped_column(ForeignKey("opportunities.id"), nullable=True)
    contact_id: Mapped[str | None] = mapped_column(ForeignKey("contacts.id"), nullable=True)
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# Phase 2 tables (v2.9) live in their own module for readability, but must
# be imported here so Base.metadata is complete for Alembic autogenerate
# and create_all. Imported at the END deliberately: models_phase2 declares
# foreign keys onto tables defined above, so importing earlier would be a
# circular reference.
from . import models_phase2  # noqa: E402,F401

# Phase 3.1 Commercial Profile. Imported here for the same reason as
# models_phase2: Base.metadata must be complete before create_all or
# Alembic autogenerate run.
from . import models_profile  # noqa: E402,F401

# Phase 3.1 Strategic Memory + Executive Focus.
from . import models_memory  # noqa: E402,F401

# Phase 3.1 Decision Journal, KPIs and the learning loop.
from . import models_journal  # noqa: E402,F401

# Sprint 2 Relationship Intelligence.
from . import models_relationship  # noqa: E402,F401
