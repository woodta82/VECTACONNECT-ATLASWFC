const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// Auth (Phase 1 hardening — see backend/app/auth.py): the session lives
// in an HttpOnly cookie set by the backend, which page JavaScript can
// never read — nothing auth-shaped is stored anywhere JS-accessible.
// The only thing held here is the CSRF token from login, in memory only
// (no localStorage), sent as X-CSRF-Token on mutating requests. Memory-
// only also preserves the deliberate "log in every time the page loads"
// behaviour, since a reload wipes it and AuthGate starts unauthenticated.
let csrfToken: string | null = null;
let onUnauthorized: (() => void) | null = null;

export function registerUnauthorizedHandler(handler: (() => void) | null) {
  onUnauthorized = handler;
}

export async function triggerAppLogout() {
  await apiFetch(`${API}/auth/logout`, { method: "POST" }).catch(() => {});
  csrfToken = null;
  onUnauthorized?.();
}

function apiFetch(input: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers);
  const method = (init.method ?? "GET").toUpperCase();
  if (csrfToken && method !== "GET") headers.set("X-CSRF-Token", csrfToken);
  return fetch(input, { ...init, headers, credentials: "include" }).then((res) => {
    if (res.status === 401 && !input.endsWith("/auth/login")) {
      csrfToken = null;
      onUnauthorized?.();
    }
    return res;
  });
}

// ---------------------------------------------------------------- Reference types
export type Vertical = "media" | "talent" | "connect" | "experiences" | "pathways";
export type RegionKey = "mena" | "uk_ireland" | "europe" | "africa" | "asia_india" | "americas" | "oceania";
export type Stage = "discovered" | "qualified" | "engaged" | "proposal" | "won" | "lost";
export type OrgType = "federation" | "club" | "government" | "brand" | "venue" | "other";
export type ScanType = "scheduled" | "on_demand" | "saved_search";
export type InteractionType = "note" | "message" | "meeting" | "task";

export const VERTICAL_LABELS: Record<Vertical, string> = {
  media: "VECTA Media",
  talent: "VECTA Talent",
  connect: "VECTA Connect",
  experiences: "VECTA Experiences",
  pathways: "VECTA Pathways",
};

export const VERTICAL_POSITIONING: Record<Vertical, string> = {
  media: "Visibility infrastructure",
  talent: "Long term representation",
  connect: "Relationship capital",
  experiences: "Environments for alignment",
  pathways: "Future pipeline infrastructure",
};

export const REGION_LABELS: Record<RegionKey, string> = {
  mena: "MENA (anchor)",
  uk_ireland: "UK & Ireland",
  europe: "Europe",
  africa: "Africa",
  asia_india: "Asia & India",
  americas: "Americas",
  oceania: "Oceania",
};

// One distinct colour per vertical/region — used for chart slices and the
// small colour swatches next to each row in the Control Panel breakdowns,
// so a slice in the pie chart and its row in the list are visually linked.
export const VERTICAL_COLORS: Record<Vertical, string> = {
  media: "#2563EB",
  talent: "#7C3AED",
  connect: "#0EA5E9",
  experiences: "#06B6D4",
  pathways: "#A855F7",
};

export const REGION_COLORS: Record<RegionKey, string> = {
  mena: "#2563EB",
  uk_ireland: "#7C3AED",
  europe: "#0EA5E9",
  africa: "#06B6D4",
  asia_india: "#A855F7",
  americas: "#F59E0B",
  oceania: "#EC4899",
};

export const STAGE_LABELS: Record<Stage, string> = {
  discovered: "Discovered",
  qualified: "Qualified",
  engaged: "Engaged",
  proposal: "Proposal",
  won: "Won",
  lost: "Lost",
};

export const STAGE_ORDER: Stage[] = ["discovered", "qualified", "engaged", "proposal", "won", "lost"];

// ---------------------------------------------------------------- Entity types
export type ScoreBreakdown = {
  vertical_fit: number;
  commercial_value: number;
  regional_relevance: number;
  deliverability: number;
  loop_value: number;
};

export type Opportunity = {
  id: string;
  title: string;
  summary: string;
  vertical: Vertical | null;
  region: RegionKey | null;
  market: string | null;
  value_estimate: number | null;
  currency: string;
  deadline: string | null;
  source_urls: string[];
  alignment_score: number;
  score_breakdown: Partial<ScoreBreakdown>;
  priority: boolean;
  stage: Stage;
  owner_id: string | null;
  organisation_id: string | null;
  organisation_name: string | null;
  outcome_reason: string | null;
  created_at: string;
  updated_at: string;
};

export type Organisation = {
  id: string;
  name: string;
  org_type: OrgType;
  region: RegionKey | null;
  market: string | null;
  website: string | null;
  linkedin_url: string | null;
  opportunity_count: number;
  contact_count: number;
};

export type OrganisationDetail = Organisation & {
  opportunities: Opportunity[];
  contacts: Contact[];
};

export type SearchResultItem = { id: string; title: string; subtitle: string; url: string };
export type GlobalSearchResult = {
  opportunities: SearchResultItem[];
  contacts: SearchResultItem[];
  organisations: SearchResultItem[];
};

export type OpportunityActivity = {
  id: string;
  opportunity_id: string;
  event_type: string;
  detail: string;
  created_at: string;
};

export type HeatmapCell = { count: number; value: number; avg_score: number | null };
export type HeatmapResponse = { cells: Record<RegionKey, Record<Vertical, HeatmapCell>> };

export type ScanRun = {
  id: string;
  type: ScanType;
  vertical_scope: Vertical | null;
  region_scope: RegionKey | null;
  query_text: string | null;
  started_at: string;
  completed_at: string | null;
  sources_checked: number;
  new_items: number;
  status: "running" | "complete" | "failed";
  error: string | null;
};

export type ScannerStatus = {
  enabled: boolean;
  running: boolean;
  last_cycle_started_at: string | null;
  last_cycle_completed_at: string | null;
  last_vertical: Vertical | null;
  next_cycle_at: string | null;
  interval_hours: number;
};

export type SavedSearch = {
  id: string;
  name: string;
  region: RegionKey;
  market: string | null;
  query_text: string;
  parsed_filters: Record<string, unknown>;
  schedule_hours: number | null;
  last_run_at: string | null;
  created_at: string;
};

export type Contact = {
  id: string;
  name: string;
  role: string | null;
  organisation_id: string | null;
  organisation_name: string | null;
  opportunity_id: string | null;
  opportunity_title: string | null;
  region: RegionKey | null;
  linkedin_search_url: string | null;
  linkedin_profile_url: string | null;
  relevance_score: number;
  connection_path: string | null;
  source: string;
  last_interaction_at: string | null;
  created_at: string;
};

export type Interaction = {
  id: string;
  contact_id: string;
  contact_name: string | null;
  opportunity_id: string | null;
  opportunity_title: string | null;
  type: InteractionType;
  content: string;
  owner_id: string | null;
  draft: boolean;
  sent: boolean;
  due_at: string | null;
  completed: boolean;
  timestamp: string;
};

export type Notification = {
  id: string;
  kind: string;
  title: string;
  body: string;
  opportunity_id: string | null;
  contact_id: string | null;
  read: boolean;
  created_at: string;
};

export type Breakdown = { count: number; value: number; avg_score: number | null };

export type ControlPanelSummary = {
  total_opportunities: number;
  priority_count: number;
  pipeline_value: number;
  weighted_pipeline_value: number;
  upcoming_deadlines_14d: number;
  new_contacts_7d: number;
  unread_notifications: number;
  by_vertical: Record<Vertical, Breakdown>;
  by_region: Record<RegionKey, Breakdown>;
  by_stage: Record<string, number>;
  scanner: ScannerStatus;
};

export type ReportSummary = {
  total_opportunities: number;
  won: number;
  lost: number;
  win_rate: number | null;
  pipeline_value: number;
  won_value: number;
  weighted_pipeline_value: number;
  lost_reasons: Record<string, number>;
  by_vertical: Record<Vertical, Breakdown>;
  by_region: Record<RegionKey, Breakdown>;
  total_scans_run: number;
  estimated_scan_cost_usd: number;
  cost_per_priority_opportunity_usd: number | null;
  pipeline_to_cost_ratio: number | null;
};

export type RegionInfo = { label: string; markets: string[] };

export type AdminSettings = {
  scan_enabled: boolean;
  scan_interval_hours: number;
  digest_hour_local: number;
  notify_priority_enabled: boolean;
  notify_deadline_enabled: boolean;
  notify_new_contact_enabled: boolean;
  anthropic_key_configured: boolean;
  resend_key_configured: boolean;
};

export type ScanHealth = {
  recent_scans: number;
  failed_scans: number;
  success_rate: number | null;
  recent_failures: ScanRun[];
};

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) throw new Error((await res.text()) || res.statusText);
  return res.json();
}

export const api = {
  // Auth (single shared login — see AuthGate.tsx)
  login: async (username: string, password: string) => {
    const res = await fetch(`${API}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
      credentials: "include", // accept the HttpOnly session cookie
    });
    if (!res.ok) {
      const body = await res.json().catch(() => null);
      throw new Error(body?.detail || "Incorrect username or password");
    }
    const data = await json<{ csrf_token: string }>(res);
    csrfToken = data.csrf_token;
    return data;
  },
  changePassword: async (current_password: string, new_password: string) => {
    const res = await apiFetch(`${API}/auth/change-password`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ current_password, new_password }),
    });
    if (!res.ok) {
      const body = await res.json().catch(() => null);
      throw new Error(body?.detail || "Password change failed");
    }
    return res.json() as Promise<{ ok: boolean; detail: string }>;
  },
  logout: async () => {
    await triggerAppLogout();
  },

  // Control Panel
  controlPanelSummary: () => apiFetch(`${API}/control-panel/summary`).then((r) => json<ControlPanelSummary>(r)),

  // Opportunities
  opportunities: (params?: {
    q?: string;
    stage?: string;
    vertical?: string;
    region?: string;
    priorityOnly?: boolean;
    sort?: "score" | "recent";
    daysBack?: number;
  }) => {
    const q = new URLSearchParams();
    if (params?.q) q.set("q", params.q);
    if (params?.stage) q.set("stage", params.stage);
    if (params?.vertical) q.set("vertical", params.vertical);
    if (params?.region) q.set("region", params.region);
    if (params?.priorityOnly) q.set("priority_only", "true");
    if (params?.sort) q.set("sort", params.sort);
    if (params?.daysBack != null) q.set("days_back", String(params.daysBack));
    const qs = q.toString();
    return apiFetch(`${API}/opportunities${qs ? `?${qs}` : ""}`).then((r) => json<Opportunity[]>(r));
  },
  opportunity: (id: string) => apiFetch(`${API}/opportunities/${id}`).then((r) => json<Opportunity>(r)),
  updateStage: (id: string, stage: Stage, outcome_reason?: string) =>
    apiFetch(`${API}/opportunities/${id}/stage`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ stage, outcome_reason: outcome_reason || null }),
    }).then((r) => json<Opportunity>(r)),
  bulkUpdateStage: (opportunity_ids: string[], stage: Stage) =>
    apiFetch(`${API}/opportunities/bulk/stage`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ opportunity_ids, stage }),
    }).then((r) => json<Opportunity[]>(r)),
  opportunityActivity: (id: string) =>
    apiFetch(`${API}/opportunities/${id}/activity`).then((r) => json<OpportunityActivity[]>(r)),
  similarOpportunities: (id: string) =>
    apiFetch(`${API}/opportunities/${id}/similar`).then((r) => json<Opportunity[]>(r)),
  updateOwner: (id: string, owner_id: string | null) =>
    apiFetch(`${API}/opportunities/${id}/owner`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ owner_id }),
    }).then((r) => json<Opportunity>(r)),

  // Scans / Global Scanner
  scans: () => apiFetch(`${API}/scans`).then((r) => json<ScanRun[]>(r)),
  scannerStatus: () => apiFetch(`${API}/scans/status`).then((r) => json<ScannerStatus>(r)),
  triggerGlobalScan: () => apiFetch(`${API}/scans/trigger`, { method: "POST" }).then((r) => json<{ status: string; scan_run_ids: string[] }>(r)),

  // Regions / Regional Search
  regions: () => apiFetch(`${API}/regions`).then((r) => json<Record<RegionKey, RegionInfo>>(r)),
  regionalSearch: (region: RegionKey, query: string, market?: string) =>
    apiFetch(`${API}/regions/search`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ region, query, market: market || null }),
    }).then((r) => json<Opportunity[]>(r)),
  savedSearches: () => apiFetch(`${API}/regions/saved-searches`).then((r) => json<SavedSearch[]>(r)),
  createSavedSearch: (name: string, region: RegionKey, query_text: string, schedule_hours: number | null, market?: string) =>
    apiFetch(`${API}/regions/saved-searches`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, region, query_text, schedule_hours, market: market || null }),
    }).then((r) => json<SavedSearch>(r)),
  deleteSavedSearch: (id: string) => apiFetch(`${API}/regions/saved-searches/${id}`, { method: "DELETE" }),
  compareRegions: (regionA: RegionKey, regionB: RegionKey) =>
    apiFetch(`${API}/regions/compare?region_a=${regionA}&region_b=${regionB}`).then((r) => json<Record<string, unknown>>(r)),

  // Relationship Intelligence
  contacts: (params?: { q?: string; opportunityId?: string; organisationId?: string; region?: string; minRelevance?: number; sort?: "relevance" | "recent" | "name" }) => {
    const q = new URLSearchParams();
    if (params?.q) q.set("q", params.q);
    if (params?.opportunityId) q.set("opportunity_id", params.opportunityId);
    if (params?.organisationId) q.set("organisation_id", params.organisationId);
    if (params?.region) q.set("region", params.region);
    if (params?.minRelevance != null) q.set("min_relevance", String(params.minRelevance));
    if (params?.sort) q.set("sort", params.sort);
    const qs = q.toString();
    return apiFetch(`${API}/contacts${qs ? `?${qs}` : ""}`).then((r) => json<Contact[]>(r));
  },
  discoverContacts: (body: { region?: RegionKey; vertical?: Vertical; role_focus?: string; organisation_name?: string; opportunity_id?: string }) =>
    apiFetch(`${API}/contacts/discover`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).then((r) => json<Contact[]>(r)),
  contact: (id: string) => apiFetch(`${API}/contacts/${id}`).then((r) => json<Contact>(r)),
  contactInteractions: (contactId: string) =>
    apiFetch(`${API}/contacts/${contactId}/interactions`).then((r) => json<Interaction[]>(r)),
  createInteraction: (body: { contact_id: string; opportunity_id?: string | null; type: InteractionType; content: string; due_at?: string | null }) =>
    apiFetch(`${API}/interactions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).then((r) => json<Interaction>(r)),
  draftOutreach: (contact_id: string, opportunity_id?: string | null) =>
    apiFetch(`${API}/interactions/draft-outreach`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ contact_id, opportunity_id: opportunity_id || null }),
    }).then((r) => json<Interaction>(r)),
  markInteractionSent: (id: string) =>
    apiFetch(`${API}/interactions/${id}/sent`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sent: true }),
    }).then((r) => json<Interaction>(r)),
  tasks: (params?: { overdueOnly?: boolean; includeCompleted?: boolean }) => {
    const q = new URLSearchParams();
    if (params?.overdueOnly) q.set("overdue_only", "true");
    if (params?.includeCompleted) q.set("include_completed", "true");
    const qs = q.toString();
    return apiFetch(`${API}/interactions/tasks${qs ? `?${qs}` : ""}`).then((r) => json<Interaction[]>(r));
  },
  markTaskComplete: (id: string, completed = true) =>
    apiFetch(`${API}/interactions/${id}/complete`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ completed }),
    }).then((r) => json<Interaction>(r)),

  // Reports
  reportSummary: () => apiFetch(`${API}/reports/summary`).then((r) => json<ReportSummary>(r)),
  reportHeatmap: () => apiFetch(`${API}/reports/heatmap`).then((r) => json<HeatmapResponse>(r)),

  // Executive Intelligence (Phase 3.1)
  briefing: (since?: string, priorities = 5) => {
    const qs = new URLSearchParams();
    if (since) qs.set("since", since);
    qs.set("priorities", String(priorities));
    return apiFetch(`${API}/briefing?${qs.toString()}`).then((r) => json<ExecutiveBriefing>(r));
  },
  briefingPriorities: (limit = 10) =>
    apiFetch(`${API}/briefing/priorities?limit=${limit}`).then((r) => json<DecisionCard[]>(r)),
  advisorQuestions: () =>
    apiFetch(`${API}/briefing/advisor/questions`).then((r) =>
      json<{ key: string; question: string; available: boolean }[]>(r)
    ),
  advisorAsk: (key: string) =>
    apiFetch(`${API}/briefing/advisor/${key}`).then((r) => json<AdvisorResponse>(r)),
  whatChanged: (opportunityId: string) =>
    apiFetch(`${API}/briefing/opportunity/${opportunityId}/what-changed`).then((r) =>
      json<WhatChanged>(r)
    ),
  recomputeFocus: () =>
    apiFetch(`${API}/briefing/recompute-focus`, { method: "POST" }).then((r) =>
      json<{ computed: number; actionable: number; suppressed: number }>(r)
    ),

  recordDecision: (
    opportunityId: string,
    body: {
      decision: string;
      response: string;
      recommended_decision: string;
      recommendation_rationale?: string;
      recommendation_confidence?: string;
      note?: string;
      owner_name?: string;
      expected_outcome?: string;
      recommended_at?: string;
    }
  ) =>
    apiFetch(`${API}/briefing/opportunity/${opportunityId}/decide`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).then((r) =>
      json<{
        recorded: boolean;
        entry_id: string;
        decision: string;
        agreed_with_recommendation: boolean;
        turnaround_hours: number | null;
      }>(r)
    ),
  executiveKpis: () => apiFetch(`${API}/briefing/kpis`).then((r) => json<Record<string, unknown>>(r)),

  // Qualification workflow (v2.9)
  qualification: (id: string) =>
    apiFetch(`${API}/opportunities/${id}/qualification`).then((r) =>
      json<{
        qualification: Phase2Qualification;
        next_actions: { type: string; action: string; detail: string; item_key: string | null }[];
        can_enter_pipeline: boolean;
        pipeline_block_reason: string | null;
      }>(r)
    ),
  answerQualification: (
    id: string,
    answers: Record<string, { answer: string; explanation?: string; evidence_id?: string }>
  ) =>
    apiFetch(`${API}/opportunities/${id}/qualification`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ answers }),
    }).then((r) =>
      json<{
        qualification: Phase2Qualification;
        next_actions: { type: string; action: string; detail: string; item_key: string | null }[];
        can_enter_pipeline: boolean;
        pipeline_block_reason: string | null;
      }>(r)
    ),
  overrideQualification: (id: string, new_state: string, reason: string, note?: string) =>
    apiFetch(`${API}/opportunities/${id}/qualification/override`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ new_state, reason, note }),
    }).then((r) => json<{ qualification: Phase2Qualification }>(r)),

  // Phase 2 (v2.9)
  phase2Opportunities: (filters: Phase2Filters = {}) => {
    const qs = new URLSearchParams();
    Object.entries(filters).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== "") qs.set(k, String(v));
    });
    const suffix = qs.toString() ? `?${qs.toString()}` : "";
    return apiFetch(`${API}/opportunities/phase2/list${suffix}`).then((r) => json<Phase2Opportunity[]>(r));
  },
  phase2Opportunity: (id: string) =>
    apiFetch(`${API}/opportunities/${id}/phase2`).then((r) => json<Phase2Opportunity>(r)),

  // Organisations
  organisations: (params?: { region?: string; q?: string }) => {
    const query = new URLSearchParams();
    if (params?.region) query.set("region", params.region);
    if (params?.q) query.set("q", params.q);
    const qs = query.toString();
    return apiFetch(`${API}/organisations${qs ? `?${qs}` : ""}`).then((r) => json<Organisation[]>(r));
  },
  organisation: (id: string) => apiFetch(`${API}/organisations/${id}`).then((r) => json<OrganisationDetail>(r)),

  // Global search
  globalSearch: (q: string) =>
    apiFetch(`${API}/search?q=${encodeURIComponent(q)}`).then((r) => json<GlobalSearchResult>(r)),

  // Admin
  adminSettings: () => apiFetch(`${API}/admin/settings`).then((r) => json<AdminSettings>(r)),
  updateAdminSettings: (body: Partial<AdminSettings>) =>
    apiFetch(`${API}/admin/settings`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).then((r) => json<AdminSettings>(r)),
  scanHealth: () => apiFetch(`${API}/admin/scan-health`).then((r) => json<ScanHealth>(r)),

  // Notifications
  notifications: (unreadOnly = false) =>
    apiFetch(`${API}/notifications${unreadOnly ? "?unread_only=true" : ""}`).then((r) => json<Notification[]>(r)),
  unreadNotificationCount: () =>
    apiFetch(`${API}/notifications/unread-count`).then((r) => json<{ count: number }>(r)),
  markNotificationRead: (id: string) =>
    apiFetch(`${API}/notifications/${id}/read`, { method: "PATCH" }).then((r) => json<Notification>(r)),
  previewDigest: () => apiFetch(`${API}/notifications/digest/preview`).then((r) => json<{ html: string }>(r)),
};

// ---------------------------------------------------------------- Phase 2 (v2.9)
// Types mirror `app/services/opportunity_serializer.py`. Labels and safety
// flags are computed server-side and travel with the values, so no component
// keeps its own copy of the taxonomy — a duplicate mapping here would go
// stale the moment a value is added on the backend.

export type CoverageBand = "assessed" | "provisional" | "insufficient";

export type Phase2Factor = {
  key: string;
  label: string;
  weight: number;
  score: number | null;
  scored: boolean;
  status_label: string;
  rationale: string | null;
};

export type Phase2Score = {
  dimension: string;
  label: string;
  score: number;
  /** null when risk is not established — render display_label instead */
  display_score: number | null;
  display_label: string;
  higher_is_better: boolean;
  coverage_percent: number;
  coverage_band: CoverageBand;
  coverage_label: string;
  risk_established: boolean | null;
  confidence: string | null;
  rationale: string | null;
  ai_score: number | null;
  manual_score: number | null;
  is_overridden: boolean;
  override_reason: string | null;
  overridden_at: string | null;
  model_version: string;
  last_scored_at: string | null;
  factors: Phase2Factor[];
};

export type Phase2Evidence = {
  id: string;
  url: string;
  page_title: string | null;
  publisher: string | null;
  source_tier: string;
  source_tier_label: string;
  evidence_type: string;
  publication_date: string | null;
  no_publication_date_reason: string | null;
  url_validation_status: string;
  url_validation_label: string;
  is_official_source: boolean;
  is_definitive: boolean;
  confidence: string;
  claims_supported: string[];
  is_manual: boolean;
};

export type Phase2AnalysisItem = {
  id: string;
  content: string;
  claim_type: string | null;
  supporting_evidence_id: string | null;
  is_verified: boolean;
  verification_label: string;
  is_completed: boolean;
  source: string;
  source_label: string;
};

export type Phase2Priority = {
  final_score: number;
  uncapped_score: number;
  band: string;
  band_label: string;
  base_score: number;
  inverse_risk: number;
  urgency_adjustment: number;
  coverage_restricted: boolean;
  qualification_restricted: boolean;
  is_restricted: boolean;
  restriction_explanation: string | null;
  weights_used: Record<string, number>;
  model_version: string;
  calculated_at: string | null;
};

export type Phase2QualificationItem = {
  item_key: string;
  item_label: string;
  is_mandatory: boolean;
  answer: string;
  answer_label: string;
  explanation: string | null;
  source: string;
};

export type Phase2Blocker = {
  failure_type: string;
  failure_type_label: string;
  item_key: string | null;
  message: string;
  is_resolved: boolean;
  is_remediable: boolean;
};

export type Phase2Qualification = {
  state: string;
  state_label: string;
  has_absolute_disqualifier?: boolean;
  summary?: string | null;
  evaluated_at?: string | null;
  checklist: Phase2QualificationItem[];
  blockers: Phase2Blocker[];
};

export type Phase2CommercialValue = {
  value_status: string;
  value_status_label: string;
  currency: string;
  published_programme_value: number | null;
  published_contract_value: number | null;
  estimated_contract_min: number | null;
  estimated_contract_max: number | null;
  estimated_vecta_revenue: number | null;
  estimate_methodology: string | null;
  partner_share_assumption: number | null;
  confidence: string | null;
  is_legacy_unverified: boolean;
  /** Server-decided: never infer this in a component */
  is_published_fact: boolean;
  is_estimate: boolean;
  display_warning: string | null;
  last_reviewed_at: string | null;
};

export type Phase2Opportunity = {
  id: string;
  title: string;
  summary: string | null;
  region: string | null;
  market: string | null;
  deadline: string | null;
  stage: string | null;
  classification: string | null;
  classification_label: string | null;
  classification_rationale: string | null;
  primary_vertical: string | null;
  primary_vertical_label: string | null;
  vertical_rationale: string | null;
  contributing_verticals: { vertical: string; label: string; rationale: string | null }[];
  contributing_vertical_count: number;
  primary_commercial_type: string | null;
  primary_commercial_type_label: string | null;
  routes_to_market: { route: string; label: string; notes: string | null; is_satisfied: boolean }[];
  evidence: Phase2Evidence[];
  evidence_status: { key: string; label: string; tier_1_count: number; validated_count: number };
  scores: Record<string, Phase2Score>;
  pursuit_priority: Phase2Priority | null;
  qualification: Phase2Qualification | null;
  commercial_value: Phase2CommercialValue | null;
  requires_human_review: boolean;
  human_review_reason: string | null;
  last_verified_at: string | null;
  verification_confidence: string | null;
  // detail only
  secondary_commercial_types?: { commercial_type: string; label: string; justification: string | null }[];
  verified_facts?: Phase2AnalysisItem[];
  ai_interpretation?: Phase2AnalysisItem[];
  assumptions?: Phase2AnalysisItem[];
  missing_information?: Phase2AnalysisItem[];
  verification_actions?: Phase2AnalysisItem[];
  overrides?: {
    field_path: string;
    original_value: string | null;
    updated_value: string | null;
    reason: string;
    model_version: string | null;
    created_at: string | null;
  }[];
  legacy?: {
    legacy_alignment_score: number | null;
    legacy_score_breakdown: Record<string, unknown>;
    legacy_vertical: string | null;
    legacy_value_estimate: number | null;
    legacy_currency: string | null;
    vertical_mapping_status: string;
    vertical_requires_review: boolean;
    migration_version: string;
    migrated_at: string | null;
    notice: string;
  } | null;
};

export type Phase2Filters = {
  classification?: string;
  primary_vertical?: string;
  qualification_state?: string;
  priority_band?: string;
  requires_human_review?: boolean;
  risk_established?: boolean;
  min_pursuit_priority?: number;
};

// ------------------------------------------------- Phase 3.1 Executive Intelligence
// Mirrors the briefing service. Every label and safety flag is computed
// server-side and travels with its value — no component maintains its own
// copy of the vocabulary.

export type ClaimKind =
  | "verified_fact"
  | "ai_interpretation"
  | "assumption"
  | "prediction"
  | "recommendation";

export type AdvisorClaim = {
  text: string;
  kind: ClaimKind;
  kind_label: string;
  source: string | null;
};

export type AdvisorResponse = {
  question: string;
  answerable: boolean;
  unanswerable_reason: string | null;
  generated_at: string;
  profile_version: number | null;
  ai_calls_used: number;
  /** Which ATLAS intelligence models produced this. Advice with no
      citation is opinion — every response names its basis. */
  intelligence_models: { code: string; name: string; question: string; version: string }[];
  /** Decision Confidence. When should_advise is false the surface must
      say ATLAS does not know enough rather than present a recommendation. */
  confidence: {
    score: number;
    band_label: string;
    should_advise: boolean;
    caveat: string | null;
  } | null;
  sections: {
    "1_recommendation": AdvisorClaim;
    "2_key_reasons": AdvisorClaim[];
    "3_supporting_evidence": AdvisorClaim[];
    "4_risks": AdvisorClaim[];
    "5_assumptions": AdvisorClaim[];
    "6_suggested_actions": AdvisorClaim[];
  };
};

export type DecisionCard = {
  // decision first — field order is the contract
  recommended_decision: { posture: string; label: string; basis: string | null };
  why_this_matters: string | null;
  confidence: "high" | "medium" | "low";
  id: string;
  title: string;
  classification: string | null;
  primary_vertical_label: string | null;
  focus_score: number;
  focus_band: string;
  focus_band_label: string;
  focus_delta: number | null;
  primary_drivers: string[];
  strategic_alignment: number | null;
  commercial_value: { amount: number | null; currency?: string; label: string; is_estimate: boolean };
  win_probability: number | null;
  /** score is null when risk could not be established — render label */
  risk: { score: number | null; label: string; established: boolean };
  relationship_status: {
    level: string;
    label: string;
    detail: string;
    is_inferred?: boolean;
    basis?: string;
    cap_note?: string;
  };
  qualification_state: string;
  qualification_label: string | null;
  opportunity_cost_of_waiting: { severity: string; summary: string };
  required_relationships: {
    role: string;
    label: string;
    status: "held" | "missing";
    contact_name: string | null;
    is_inferred: boolean;
  }[];
  supporting_evidence: {
    total: number;
    tier_1: number;
    validated: number;
    label: string;
    strongest_source: { publisher: string | null; tier: string; url: string; validation: string } | null;
    sufficient_for_decision: boolean;
  };
  recommended_next_action: string;
  owner: string | null;
  target_date: string | null;
  deadline: string | null;
  pursuit_priority: number | null;
  priority_restricted: boolean;
  score_reconciliation: string | null;
};

export type ChangeItem = {
  id: string;
  event_type: string;
  materiality: "high" | "medium" | "low";
  summary: string;
  detail: string | null;
  delta: number | null;
  occurred_at: string | null;
  triggered_by: string;
  opportunity_id: string | null;
  opportunity_title: string | null;
};

export type ExecutiveBriefing = {
  generated_at: string;
  since: string;
  ai_calls_used: number;
  /** Server-side assembly time. Surfaced so a regression past the
      1.5s design budget is visible rather than merely felt. */
  generation_ms: number;
  sections: {
    "1_executive_summary": {
      headline: string;
      is_complete: boolean;
      completion_message: string | null;
      counts: {
        material_changes: number;
        significant_changes: number;
        act_now: number;
        this_week: number;
        deadlines_30_days: number;
        going_stale: number;
        awaiting_qualification: number;
      };
      what_can_wait: { id: string; title: string; reason: string | null }[];
    };
    "2_todays_priorities": DecisionCard[];
    "3_what_changed": ChangeItem[];
    "4_relationship_watchlist": {
      opportunity_id: string;
      opportunity_title: string;
      influence: string;
      current_strength: string;
      contacts_mapped: number;
      last_engagement_days: number | null;
      recommended_engagement: string;
      expected_commercial_benefit: string;
      focus_score: number;
    }[];
    "5_market_intelligence": {
      region: string | null;
      market: string | null;
      new_opportunities: number;
      profile_tier: number | null;
      is_priority: boolean;
      relevance: string;
    }[];
    "6_executive_risks": {
      category: string;
      severity: string;
      summary: string;
      evidence: string;
      mitigation: string;
      owner: string | null;
    }[];
    "7_advisor": { question: string; available: boolean }[];
  };
  profile: {
    version: number | null;
    completeness_percent: number;
    incomplete_sections: string[];
  };
  scanning: {
    last_scan_days_ago: number | null;
    suggest_scan: boolean;
    estimated_cost_usd: number;
  };
};

export type WhatChanged = {
  available: boolean;
  opportunity_id?: string;
  summary: string;
  has_changes: boolean;
  scores: Record<
    string,
    {
      current: number;
      previous: number | null;
      delta: number | null;
      direction: string;
      changed_at: string | null;
      change_reason: string | null;
      suppressed: boolean;
    }
  >;
  executive_focus: {
    current: number;
    previous: number | null;
    delta: number | null;
    band: string;
    direction: string;
  } | null;
  qualification: { current: string; previous: string | null; changed_at: string | null } | null;
  commercial_impact: {
    previous_expected_value: number;
    current_expected_value: number;
    delta: number;
    currency: string;
    direction: "gain" | "loss";
    is_estimate: boolean;
    basis: string;
  } | null;
  previous_recommendation: {
    recommended: string;
    decided: string;
    response: string;
    decided_at: string | null;
    focus_at_decision: number | null;
    win_probability_at_decision: number | null;
    agreed: boolean;
  } | null;
  recent_events: { event_type: string; summary: string; materiality: string; occurred_at: string | null }[];
};
