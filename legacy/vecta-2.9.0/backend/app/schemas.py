from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

VerticalStr = Literal["media", "talent", "connect", "experiences", "pathways"]
RegionStr = Literal["mena", "uk_ireland", "europe", "africa", "asia_india", "americas", "oceania"]
StageStr = Literal["discovered", "qualified", "engaged", "proposal", "won", "lost"]
OrgTypeStr = Literal["federation", "club", "government", "brand", "venue", "other"]
ScanTypeStr = Literal["scheduled", "on_demand", "saved_search"]
InteractionTypeStr = Literal["note", "message", "meeting", "task"]


# ---------------------------------------------------------------- Organisations
class OrganisationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    org_type: OrgTypeStr
    region: RegionStr | None
    market: str | None
    website: str | None
    linkedin_url: str | None
    opportunity_count: int = 0
    contact_count: int = 0


# ---------------------------------------------------------------- Score breakdown
class ScoreBreakdown(BaseModel):
    vertical_fit: int
    commercial_value: int
    regional_relevance: int
    deliverability: int
    loop_value: int


# ---------------------------------------------------------------- Opportunities
class OpportunityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    title: str
    summary: str
    vertical: VerticalStr | None
    region: RegionStr | None
    market: str | None
    value_estimate: float | None
    currency: str
    deadline: date | None
    source_urls: list
    alignment_score: int
    score_breakdown: dict
    priority: bool
    stage: StageStr
    owner_id: str | None
    organisation_id: str | None
    organisation_name: str | None = None
    outcome_reason: str | None = None
    created_at: datetime
    updated_at: datetime


class OpportunityStageUpdate(BaseModel):
    stage: StageStr
    # Optional — captured when moving to Won/Lost. Free text (e.g.
    # "budget", "competitor", "timing"); ignored for other stage moves.
    outcome_reason: str | None = None


class BulkStageUpdate(BaseModel):
    opportunity_ids: list[str]
    stage: StageStr


class OpportunityOwnerUpdate(BaseModel):
    owner_id: str | None


# ---------------------------------------------------------------- Scans
class ScanRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    type: ScanTypeStr
    vertical_scope: VerticalStr | None
    region_scope: RegionStr | None
    query_text: str | None
    started_at: datetime
    completed_at: datetime | None
    sources_checked: int
    new_items: int
    status: str
    error: str | None


class ScannerStatus(BaseModel):
    enabled: bool
    running: bool
    last_cycle_started_at: datetime | None
    last_cycle_completed_at: datetime | None
    last_vertical: VerticalStr | None
    next_cycle_at: datetime | None
    interval_hours: float


# ---------------------------------------------------------------- Regional search
class RegionalSearchRequest(BaseModel):
    region: RegionStr
    market: str | None = None
    query: str


class SavedSearchCreate(BaseModel):
    name: str
    region: RegionStr
    market: str | None = None
    query_text: str
    # Kept for backward compatibility with existing data only — the loop
    # that used to act on this was removed (it re-checked every 15
    # minutes independent of the Global Scanner's own interval, and was
    # the actual source of frequent, hard-to-explain charges). Setting
    # this now does nothing; saved searches are a "save this filter for
    # one-tap reuse" feature only. The frontend no longer offers a way to
    # set it.
    schedule_hours: float | None = None


class SavedSearchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    region: RegionStr
    market: str | None
    query_text: str
    parsed_filters: dict
    schedule_hours: float | None
    last_run_at: datetime | None
    created_at: datetime


# ---------------------------------------------------------------- Contacts / Relationship Intelligence
class ContactOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    role: str | None
    organisation_id: str | None
    organisation_name: str | None = None
    opportunity_id: str | None
    opportunity_title: str | None = None
    region: RegionStr | None
    linkedin_search_url: str | None
    linkedin_profile_url: str | None
    relevance_score: int
    connection_path: str | None
    source: str
    last_interaction_at: datetime | None
    created_at: datetime


class ContactDiscoveryRequest(BaseModel):
    """Manual influence-graph search — always user-triggered, never
    automatic (see backend/app/scheduler.py for why that matters for
    cost control). Pass opportunity_id to link results to that specific
    opportunity's Linked Contacts; omit it for a standalone search."""
    region: RegionStr | None = None
    vertical: VerticalStr | None = None
    role_focus: str | None = None  # e.g. "commercial directors", "heads of procurement"
    organisation_name: str | None = None
    opportunity_id: str | None = None


class InteractionCreate(BaseModel):
    contact_id: str
    opportunity_id: str | None = None
    type: InteractionTypeStr = "note"
    content: str
    owner_id: str | None = None
    due_at: datetime | None = None


class InteractionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    contact_id: str
    contact_name: str | None = None
    opportunity_id: str | None
    opportunity_title: str | None = None
    type: InteractionTypeStr
    content: str
    owner_id: str | None
    draft: bool
    sent: bool
    due_at: datetime | None = None
    completed: bool = False
    timestamp: datetime


class TaskCompleteUpdate(BaseModel):
    completed: bool = True


class OutreachDraftRequest(BaseModel):
    contact_id: str
    opportunity_id: str | None = None


class InteractionMarkSent(BaseModel):
    sent: bool = True


# ---------------------------------------------------------------- Notifications
class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    kind: str
    title: str
    body: str
    opportunity_id: str | None
    contact_id: str | None
    read: bool
    created_at: datetime


# ---------------------------------------------------------------- Reports / dashboard
class VerticalBreakdown(BaseModel):
    count: int
    value: float
    avg_score: float | None


class RegionBreakdown(BaseModel):
    count: int
    value: float
    avg_score: float | None


class ControlPanelSummary(BaseModel):
    total_opportunities: int
    priority_count: int
    pipeline_value: float
    weighted_pipeline_value: float
    upcoming_deadlines_14d: int
    new_contacts_7d: int
    unread_notifications: int
    by_vertical: dict[str, VerticalBreakdown]
    by_region: dict[str, RegionBreakdown]
    by_stage: dict[str, int]
    scanner: ScannerStatus


class ReportSummary(BaseModel):
    total_opportunities: int
    won: int
    lost: int
    win_rate: float | None
    pipeline_value: float
    won_value: float
    weighted_pipeline_value: float
    lost_reasons: dict[str, int]
    by_vertical: dict[str, VerticalBreakdown]
    by_region: dict[str, RegionBreakdown]
    # Commercial ROI on the scanning spend — see reports.py for how these
    # are derived. estimated_scan_cost_usd is a rough estimate (configurable
    # via ESTIMATED_COST_PER_SCAN_USD), not a real Anthropic billing figure.
    total_scans_run: int
    estimated_scan_cost_usd: float
    cost_per_priority_opportunity_usd: float | None
    pipeline_to_cost_ratio: float | None


class OrganisationDetail(OrganisationOut):
    opportunities: list[OpportunityOut] = []
    contacts: list[ContactOut] = []


class SearchResultItem(BaseModel):
    id: str
    title: str
    subtitle: str
    url: str


class GlobalSearchResult(BaseModel):
    opportunities: list[SearchResultItem]
    contacts: list[SearchResultItem]
    organisations: list[SearchResultItem]


class OpportunityActivityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    opportunity_id: str
    event_type: str
    detail: str
    created_at: datetime


class HeatmapCell(BaseModel):
    count: int
    value: float
    avg_score: float | None


class HeatmapResponse(BaseModel):
    # region -> vertical -> cell
    cells: dict[str, dict[str, HeatmapCell]]
